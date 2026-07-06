"""
JWT auth routes.
"""

from __future__ import annotations

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
    response = issue_login_response(body.email.strip().lower(), body.password, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
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


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
):
    """Change password for the authenticated user. Returns new JWT."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decode_access_token(token)
        user = get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # Verify current password
    from app.core.auth import authenticate_user, update_password
    if not authenticate_user(user["email"], request.current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    update_password(user["email"], request.new_password)
    return {"status": "ok", "message": "Password updated successfully"}


@router.get("/jwks")
async def jwks():
    """JWK Set — public key(s) used to verify RS256 access tokens."""
    return build_jwks()


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    """Rotate a refresh token and issue a new access token + refresh token pair."""
    from app.core.refresh_tokens import rotate_refresh_token
    from app.core.auth import get_user_payload_by_email, create_access_token
    from app.core.config import settings

    result = rotate_refresh_token(body.refresh_token, expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    new_refresh_token, _, user_id = result

    # Reload full user payload by user_id (look up by user_id slug)
    from app.core.auth import _load_user_by_email, _user_record_to_payload
    conn = __import__("sqlite3").connect(
        settings.SQLITE_DB_PATH
    )
    conn.row_factory = __import__("sqlite3").Row
    user_row = conn.execute("SELECT * FROM auth_users WHERE user_id = ? AND is_active = 1", (user_id,)).fetchone()
    conn.close()

    if not user_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user_payload = _user_record_to_payload(user_row)
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
