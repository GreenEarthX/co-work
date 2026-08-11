"""
Account vetting — registration and GEX-employee onboarding.
===========================================================
Implements the policy in core/account_lifecycle.py:

    registration → PENDING → (GEX employee vets) → ACTIVE

Self-service can only ever produce PENDING. Everything that advances an
account requires an authenticated GEX platform administrator, and every step
is written to the event ledger with the employee's identity — because "who
vouched for this organisation" is exactly the question an auditor asks.

Route map
---------
  POST /api/v1/account/register                       PUBLIC  → PENDING
  GET  /api/v1/account/status                         self-service status
  GET  /api/v1/account/vetting-queue                  GEX staff
  POST /api/v1/account/{user_id}/claim                GEX staff → IN_VETTING
  POST /api/v1/account/{user_id}/telephone-verification GEX staff (records call)
  POST /api/v1/account/{user_id}/usage-agreement      GEX staff (records signature)
  POST /api/v1/account/{user_id}/activate             GEX staff → ACTIVE
  POST /api/v1/account/{user_id}/reject               GEX staff → REJECTED
  POST /api/v1/account/{user_id}/suspend              GEX staff → SUSPENDED
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.core.account_lifecycle import (
    AccountLifecycleError,
    AccountState,
    assert_activation_evidence,
    assert_activator_is_gex_staff,
    assert_separation_of_duties,
    assert_transition_allowed,
)
from app.core.event_store import append_event

logger = logging.getLogger("gex.account_vetting")
router = APIRouter()


def _conn() -> sqlite3.Connection:
    """`auth_users` is owned by app.core.auth — use its accessor, never our own
    connection. (Also keeps this module off the raw-sqlite3 ratchet.)"""
    from app.core.auth import auth_db_connection

    return auth_db_connection()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def _require_gex_staff(request: Request) -> dict:
    actor = _actor(request)
    try:
        assert_activator_is_gex_staff(actor)
    except AccountLifecycleError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return actor


def _load(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM auth_users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return row


def _state_of(row: sqlite3.Row) -> AccountState:
    raw = row["account_state"] if "account_state" in row.keys() else None
    try:
        return AccountState(raw)
    except ValueError:
        return AccountState.PENDING  # fail closed


def _audit(user_id: str, event: str, actor: dict, data: dict) -> None:
    append_event(
        event_type=f"account.{event}",
        aggregate_type="account",
        aggregate_id=user_id,
        data={**data, "actor_email": actor.get("email")},
        user_id=str(actor.get("user_id") or actor.get("sub") or "system"),
        correlation_id=f"ACCT-{user_id[:8]}",
    )


def _transition(conn: sqlite3.Connection, row: sqlite3.Row, target: AccountState) -> None:
    try:
        assert_transition_allowed(_state_of(row), target)
    except AccountLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ── Registration (PUBLIC) ───────────────────────────────────────────────────

_REGISTRATION_NEXT_STEP = (
    "A GEX representative will telephone you to verify your identity and "
    "organisation, and to exchange the software usage agreement. Your account "
    "cannot be used until that is complete."
)


class RegistrationRequest(BaseModel):
    # Plain str + a minimal shape check, matching LoginRequest. pydantic's
    # EmailStr would pull in email-validator, a new runtime dependency for a
    # field a GEX employee confirms by telephone anyway.
    email: str
    password: str = Field(min_length=12)
    user_name: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=2, max_length=200)
    company_type: str
    business_function: str
    telephone: str = Field(min_length=6, max_length=40)
    service_type: Optional[str] = None
    jurisdiction: str = "EU"

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        v = v.strip().lower()
        local, _, domain = v.partition("@")
        if not local or not domain or "." not in domain or " " in v:
            raise ValueError("a valid email address is required")
        return v


class RegistrationResponse(BaseModel):
    # Optional: a duplicate-address attempt returns this SAME shape with
    # user_id/account_state omitted, so the response cannot be used to
    # enumerate which addresses are already registered.
    user_id: Optional[str] = None
    email: str
    account_state: Optional[str] = None
    next_step: str


@router.post("/register", response_model=RegistrationResponse, status_code=201)
async def register(body: RegistrationRequest) -> RegistrationResponse:
    """
    Create a PENDING account. Grants nothing.

    Everything in this body is SELF-ASSERTED and is treated as an application,
    not as fact — company_type and business_function especially. A GEX employee
    confirms them on the verification call; until then they are only claims.
    """
    from app.core.auth import init_auth_db, pwd_context

    init_auth_db()
    email = body.email.strip().lower()
    conn = _conn()
    try:
        if conn.execute("SELECT 1 FROM auth_users WHERE email = ?", (email,)).fetchone():
            # Indistinguishable from success — registration must not reveal
            # whether an address is already registered. Nothing is created.
            logger.info("registration attempt for existing address %s", email)
            return RegistrationResponse(email=email, next_step=_REGISTRATION_NEXT_STEP)

        user_id = f"usr_{uuid4().hex[:16]}"
        now = _now()
        conn.execute(
            """
            INSERT INTO auth_users (
                user_id, email, password_hash, company_id, company_name,
                company_type, service_type, business_function, user_name,
                jurisdiction, clearance_level, kyc_status, is_platform_admin,
                is_active, account_state, registered_at, vetting_note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id, email, pwd_context.hash(body.password),
                # company_id is provisional — a GEX employee binds the account to
                # the real organisation during vetting.
                f"pending_{uuid4().hex[:8]}", body.company_name.strip(),
                body.company_type, body.service_type, body.business_function,
                body.user_name.strip(), body.jurisdiction,
                "STANDARD",
                # NOT 'VERIFIED'. The column's historic default was the bug.
                "UNVERIFIED",
                0,
                # is_active is the legacy flag; account_state is authoritative.
                0,
                AccountState.PENDING.value, now,
                f"Self-registered {now}. Telephone supplied: {body.telephone.strip()}. "
                "All company details are self-asserted and unconfirmed.",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _audit(user_id, "registered", {"user_id": user_id, "email": email},
           {"account_state": AccountState.PENDING.value, "self_asserted": True})
    logger.info("account registered PENDING: %s", email)

    return RegistrationResponse(
        user_id=user_id, email=email, account_state=AccountState.PENDING.value,
        next_step=_REGISTRATION_NEXT_STEP,
    )


# ── Self-service status ─────────────────────────────────────────────────────

@router.get("/status")
async def my_status(request: Request) -> dict[str, Any]:
    actor = _actor(request)
    conn = _conn()
    try:
        row = _load(conn, str(actor.get("user_id") or actor.get("sub")))
        return {
            "account_state": _state_of(row).value,
            "telephone_verified": bool(row["phone_verified_at"]),
            "agreement_signed": bool(row["agreement_signed_at"]),
            "registered_at": row["registered_at"],
        }
    finally:
        conn.close()


# ── GEX staff: the vetting queue ────────────────────────────────────────────

@router.get("/vetting-queue")
async def vetting_queue(request: Request) -> dict[str, Any]:
    _require_gex_staff(request)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT user_id, email, user_name, company_name, company_type, "
            "business_function, account_state, registered_at, phone_verified_at, "
            "phone_verified_by, agreement_signed_at, agreement_ref, vetting_note "
            "FROM auth_users WHERE account_state IN (?,?) ORDER BY registered_at",
            (AccountState.PENDING.value, AccountState.IN_VETTING.value),
        ).fetchall()
        return {
            "count": len(rows),
            "applications": [
                {**dict(r),
                 "outstanding": [
                     reason for col, reason in {
                         "phone_verified_at": "telephone verification",
                         "agreement_signed_at": "signed usage agreement",
                     }.items() if not r[col]
                 ]}
                for r in rows
            ],
        }
    finally:
        conn.close()


class ClaimRequest(BaseModel):
    note: str = ""


@router.post("/{user_id}/claim")
async def claim_application(user_id: str, body: ClaimRequest, request: Request) -> dict:
    """A GEX employee takes ownership of an application: PENDING → IN_VETTING."""
    actor = _require_gex_staff(request)
    conn = _conn()
    try:
        row = _load(conn, user_id)
        _transition(conn, row, AccountState.IN_VETTING)
        conn.execute(
            "UPDATE auth_users SET account_state = ?, updated_at = ? WHERE user_id = ?",
            (AccountState.IN_VETTING.value, _now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    _audit(user_id, "vetting_claimed", actor, {"note": body.note})
    return {"user_id": user_id, "account_state": AccountState.IN_VETTING.value}


# ── GEX staff: record the two pieces of human vetting ───────────────────────

class TelephoneVerificationRequest(BaseModel):
    telephone_called: str = Field(min_length=6, max_length=40)
    spoke_with: str = Field(min_length=2, max_length=120)
    identity_confirmed: bool
    organisation_confirmed: bool
    notes: str = Field(default="", max_length=2000)


@router.post("/{user_id}/telephone-verification")
async def record_telephone_verification(
    user_id: str, body: TelephoneVerificationRequest, request: Request,
) -> dict:
    """
    Record the verification CALL. This is the step no applicant can perform:
    it asserts that a named GEX employee spoke to a named human and confirmed
    both the person and the organisation.
    """
    actor = _require_gex_staff(request)
    if not (body.identity_confirmed and body.organisation_confirmed):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "verification_not_confirmed",
                "reason": "A telephone verification is only recorded when BOTH the "
                          "individual's identity and the organisation are confirmed. "
                          "Reject the application instead.",
            },
        )

    actor_id = str(actor.get("user_id") or actor.get("sub"))
    now = _now()
    conn = _conn()
    try:
        row = _load(conn, user_id)
        if _state_of(row) not in (AccountState.PENDING, AccountState.IN_VETTING):
            raise HTTPException(
                status_code=409,
                detail=f"Account is {_state_of(row).value}; verification applies "
                       "to applications under vetting only.",
            )
        conn.execute(
            "UPDATE auth_users SET phone_verified_at = ?, phone_verified_by = ?, "
            "account_state = ?, updated_at = ? WHERE user_id = ?",
            (now, actor_id, AccountState.IN_VETTING.value, now, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    _audit(user_id, "telephone_verified", actor, {
        "telephone_called": body.telephone_called, "spoke_with": body.spoke_with,
        "identity_confirmed": True, "organisation_confirmed": True, "notes": body.notes,
    })
    return {"user_id": user_id, "phone_verified_at": now, "phone_verified_by": actor_id}


class UsageAgreementRequest(BaseModel):
    agreement_ref: str = Field(min_length=3, max_length=200)
    agreement_version: str = Field(min_length=1, max_length=40)
    signed_by: str = Field(min_length=2, max_length=120)
    signed_on: str = Field(description="ISO date the counterparty signed")


@router.post("/{user_id}/usage-agreement")
async def record_usage_agreement(
    user_id: str, body: UsageAgreementRequest, request: Request,
) -> dict:
    """Record the exchanged/signed software usage agreement."""
    actor = _require_gex_staff(request)
    now = _now()
    conn = _conn()
    try:
        row = _load(conn, user_id)
        if _state_of(row) not in (AccountState.PENDING, AccountState.IN_VETTING):
            raise HTTPException(
                status_code=409,
                detail=f"Account is {_state_of(row).value}; the agreement is "
                       "recorded during vetting.",
            )
        conn.execute(
            "UPDATE auth_users SET agreement_signed_at = ?, agreement_ref = ?, "
            "account_state = ?, updated_at = ? WHERE user_id = ?",
            (body.signed_on, body.agreement_ref, AccountState.IN_VETTING.value, now, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    _audit(user_id, "usage_agreement_signed", actor, {
        "agreement_ref": body.agreement_ref, "agreement_version": body.agreement_version,
        "signed_by": body.signed_by, "signed_on": body.signed_on,
    })
    return {"user_id": user_id, "agreement_ref": body.agreement_ref,
            "agreement_signed_at": body.signed_on}


# ── GEX staff: the decision ─────────────────────────────────────────────────

class ActivationRequest(BaseModel):
    company_id: str = Field(min_length=2, max_length=100,
                            description="The REAL organisation this account belongs to")
    clearance_level: str = "STANDARD"
    note: str = ""


@router.post("/{user_id}/activate")
async def activate(user_id: str, body: ActivationRequest, request: Request) -> dict:
    """
    Grant access. The only step that makes an account usable.

    Refuses unless BOTH pieces of vetting are already on the record, and unless
    the activator is a different GEX employee from the one who made the call.
    """
    actor = _require_gex_staff(request)
    actor_id = str(actor.get("user_id") or actor.get("sub"))
    now = _now()
    conn = _conn()
    try:
        row = _load(conn, user_id)
        record = dict(row)
        _transition(conn, row, AccountState.ACTIVE)
        try:
            assert_activation_evidence(record)
            assert_separation_of_duties(record, actor_id)
        except AccountLifecycleError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        conn.execute(
            "UPDATE auth_users SET account_state = ?, is_active = 1, company_id = ?, "
            "clearance_level = ?, kyc_status = 'VERIFIED', activated_at = ?, "
            "activated_by = ?, updated_at = ? WHERE user_id = ?",
            (AccountState.ACTIVE.value, body.company_id, body.clearance_level,
             now, actor_id, now, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    _audit(user_id, "activated", actor, {
        "company_id": body.company_id, "clearance_level": body.clearance_level,
        "note": body.note,
        "telephone_verified_by": record.get("phone_verified_by"),
        "agreement_ref": record.get("agreement_ref"),
    })
    logger.info("account ACTIVATED %s by %s", user_id, actor_id)
    return {"user_id": user_id, "account_state": AccountState.ACTIVE.value,
            "activated_by": actor_id, "activated_at": now}


class DecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@router.post("/{user_id}/reject")
async def reject(user_id: str, body: DecisionRequest, request: Request) -> dict:
    actor = _require_gex_staff(request)
    conn = _conn()
    try:
        row = _load(conn, user_id)
        _transition(conn, row, AccountState.REJECTED)
        conn.execute(
            "UPDATE auth_users SET account_state = ?, is_active = 0, "
            "vetting_note = ?, updated_at = ? WHERE user_id = ?",
            (AccountState.REJECTED.value, body.reason, _now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    _audit(user_id, "rejected", actor, {"reason": body.reason})
    return {"user_id": user_id, "account_state": AccountState.REJECTED.value}


@router.post("/{user_id}/suspend")
async def suspend(user_id: str, body: DecisionRequest, request: Request) -> dict:
    actor = _require_gex_staff(request)
    conn = _conn()
    try:
        row = _load(conn, user_id)
        _transition(conn, row, AccountState.SUSPENDED)
        conn.execute(
            "UPDATE auth_users SET account_state = ?, is_active = 0, "
            "vetting_note = ?, updated_at = ? WHERE user_id = ?",
            (AccountState.SUSPENDED.value, body.reason, _now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    _audit(user_id, "suspended", actor, {"reason": body.reason})
    return {"user_id": user_id, "account_state": AccountState.SUSPENDED.value}
