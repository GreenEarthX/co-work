"""
JWT auth routes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.auth import (
    build_jwks,
    decode_access_token,
    get_login_history,
    get_user_payload_from_token,
    issue_login_response,
    record_login_event,
    role_payload_from_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: str
    refresh_token: str
    email: str
    role: dict
    user: dict


@router.get("/health")
async def auth_health():
    return {"status": "ok", "service": "jwt_auth"}


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    from app.core.auth import AccountNotActive

    try:
        response = issue_login_response(body.email.strip().lower(), body.password, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    except AccountNotActive as exc:
        # 403, not 401: the credentials were correct. Telling the applicant
        # their account is awaiting vetting is deliberate — they should chase
        # GEX, not their password. This is only reachable AFTER a correct
        # password, so it leaks nothing about which addresses are registered.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_not_active",
                "account_state": exc.state,
                "reason": "This account is not yet active. A GEX representative "
                          "must complete onboarding — a telephone verification "
                          "and the signed software usage agreement — before "
                          "access is granted.",
            },
        ) from exc
    if not response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return LoginResponse(**response)


@router.get("/me")
async def me(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        decode_access_token(token)
        user = get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return {
        "email": user["email"],
        "role": role_payload_from_user(user),
        "user": user,
    }


@router.get("/login-history")
async def login_history(authorization: str | None = Header(default=None)):
    """Return last 10 login events for the authenticated user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decode_access_token(token)
        user = get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    history = get_login_history(user["user_id"])
    return {"history": history}


def _require_postgres() -> None:
    """Account self-service (password, telephone) is PostgreSQL only (JML,
    2026-11-03): 503 POSTGRES_REQUIRED rather than a write to the SQLite file."""
    from app.core.db_backend import eventstore_is_postgres, is_postgres, require_postgres

    require_postgres(is_postgres(), "Account self-service", "AUTH_DB_BACKEND")
    require_postgres(eventstore_is_postgres(), "Account self-service", "EVENTSTORE_DB_BACKEND")


def _bearer_user(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decode_access_token(token)
        return get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _temporary_password_in_force(user_id: str) -> bool:
    """A GEX-chosen temporary password (account.temporary_password_set) that its
    owner has not yet replaced (account.password_changed). Read from the ledger."""
    from app.core.event_store import get_events

    last = None
    for e in get_events(aggregate_type="account", aggregate_id=user_id, limit=None):
        if e.get("event_type") in ("account.temporary_password_set", "account.password_changed"):
            last = e["event_type"]
    return last == "account.temporary_password_set"


@router.get("/password-status")
async def password_status(authorization: str | None = Header(default=None)):
    """The rule before the person types, and whether a temporary password is still in force."""
    _require_postgres()
    from app.core.password_policy import describe_policy

    user = _bearer_user(authorization)
    return {"temporary": _temporary_password_in_force(user["user_id"]),
            "policy": describe_policy(is_platform_admin=bool(user.get("is_platform_admin")))}


class TelephoneRequest(BaseModel):
    telephone: str


_TELEPHONE = re.compile(r"^\+?[0-9 ()./-]{6,40}$")


@router.get("/telephone")
async def get_telephone(authorization: str | None = Header(default=None)):
    """The signed-in account's current telephone number (alembic 081), or null."""
    _require_postgres()
    from app.core.auth import auth_db_connection

    user = _bearer_user(authorization)
    conn = auth_db_connection()
    try:
        row = conn.execute("SELECT telephone FROM auth_users WHERE user_id = ?", (user["user_id"],)).fetchone()
    finally:
        conn.close()
    return {"telephone": row["telephone"] if row else None}


@router.put("/telephone")
async def set_telephone(body: TelephoneRequest, authorization: str | None = Header(default=None)):
    """
    The owner changes their own number (JML, 2026-11-03). Only their own: the
    account is the token's. A verification call already recorded stays recorded.
    The ledger event carries no numbers (append-only; the number is correctable
    personal data) — the column holds the current one.
    """
    _require_postgres()
    from app.core.auth import auth_db_connection
    from app.core.event_store import append_event

    user = _bearer_user(authorization)
    number = " ".join(body.telephone.split())
    if not _TELEPHONE.match(number) or sum(c.isdigit() for c in number) < 6:
        raise HTTPException(status_code=422, detail="Enter a telephone number: digits, spaces, and an optional leading +.")
    conn = auth_db_connection()
    try:
        row = conn.execute("SELECT telephone FROM auth_users WHERE user_id = ?", (user["user_id"],)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        if row["telephone"] == number:
            return {"telephone": number, "changed": False}
        conn.execute("UPDATE auth_users SET telephone = ?, updated_at = ? WHERE user_id = ?",
                     (number, datetime.now(timezone.utc).isoformat(), user["user_id"]))
        conn.commit()
    finally:
        conn.close()
    try:
        append_event(event_type="account.telephone_changed", aggregate_type="account",
                     aggregate_id=user["user_id"], data={"by_owner": True, "had_number": row["telephone"] is not None},
                     user_id=user["user_id"], correlation_id=f"ACCT-{user['user_id'][:8]}")
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("gex.auth").exception("telephone changed for %s; ledger event not written", user["user_id"])
    return {"telephone": number, "changed": True}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
):
    """
    The owner changes their own password (JML, 2026-11-03).

    Needs the current password, refuses the same one again and anything the
    policy refuses (422, with its reason). Every other session is signed out
    (refresh tokens revoked) and this one gets a fresh refresh token. The
    change is written to the ledger as account.password_changed, which also
    ends a temporary password chosen by GEX.
    """
    from app.core.auth import AccountNotActive, authenticate_user, update_password
    from app.core.config import settings
    from app.core.event_store import append_event
    from app.core.password_policy import PasswordPolicyError
    from app.core.refresh_tokens import issue_refresh_token, revoke_all_for_user

    _require_postgres()
    user = _bearer_user(authorization)
    try:
        if not authenticate_user(user["email"], request.current_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    except AccountNotActive as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not active.") from exc
    if request.new_password == request.current_password:
        raise HTTPException(status_code=422, detail="The new password must differ from the current one.")
    try:
        update_password(user["email"], request.new_password)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    revoke_all_for_user(user["user_id"])
    refresh_token, _ = issue_refresh_token(user["user_id"], expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    try:
        append_event(event_type="account.password_changed", aggregate_type="account",
                     aggregate_id=user["user_id"], data={"by_owner": True},
                     user_id=user["user_id"], correlation_id=f"ACCT-{user['user_id'][:8]}")
    except Exception:  # noqa: BLE001
        # The password IS changed. Without the event a temporary password still
        # reads as in force, so the screen keeps asking: that fails safe.
        import logging
        logging.getLogger("gex.auth").exception("password changed for %s; ledger event not written", user["user_id"])
    return {"status": "ok", "message": "Password changed. Your other sessions were signed out.",
            "refresh_token": refresh_token}


@router.get("/jwks")
async def jwks():
    """JWK Set — public key(s) used to verify RS256 access tokens."""
    return build_jwks()


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    """Rotate a refresh token and issue a new access token + refresh token pair."""
    from app.core.refresh_tokens import revoke_all_for_user, rotate_refresh_token
    from app.core.auth import AccountNotActive, create_access_token, load_user_for_refresh
    from app.core.config import settings

    result = rotate_refresh_token(body.refresh_token, expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    new_refresh_token, _, user_id = result

    # The account, from the auth slice's own store, under the sign-in vetting rule
    # (auth.load_user_for_refresh). A refusal also revokes every refresh token the
    # account holds: the one just rotated must not outlive the refusal.
    try:
        user_payload = load_user_for_refresh(user_id)
    except AccountNotActive as exc:
        revoke_all_for_user(user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error": "account_not_active", "account_state": exc.state,
            "reason": "This account is not active, so its session cannot be renewed."}) from exc
    if not user_payload:
        revoke_all_for_user(user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Roles and assigned audits are read now, so a refreshed session carries any
    # reviewer appointment or revocation made since sign-in.
    access_token, expires_at = create_access_token(user_payload)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "refresh_token": new_refresh_token,
    }


@router.post("/logout")
async def logout(authorization: str | None = Header(default=None)):
    """Revoke all refresh tokens for the authenticated user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        user = get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    from app.core.refresh_tokens import revoke_all_for_user
    revoke_all_for_user(user["user_id"])
    return {"status": "ok", "message": "Logged out"}


@router.get("/oidc-discovery")
async def oidc_discovery():
    """OIDC-compatible discovery document (.well-known/openid-configuration)."""
    base_url = "http://localhost:8000"
    return {
        "issuer": f"{base_url}/api/v1/auth",
        "authorization_endpoint": f"{base_url}/api/v1/auth/login",
        "token_endpoint": f"{base_url}/api/v1/auth/login",
        "userinfo_endpoint": f"{base_url}/api/v1/auth/me",
        "jwks_uri": f"{base_url}/api/v1/auth/jwks",
        "scopes_supported": ["openid", "profile", "email", "gex:trade", "gex:finance", "gex:admin"],
        "response_types_supported": ["code", "token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "claims_supported": [
            "sub", "email", "name", "company_id", "company_type",
            "business_function", "service_type", "clearance_level",
            "capabilities", "kyc_status", "jurisdiction",
        ],
    }
