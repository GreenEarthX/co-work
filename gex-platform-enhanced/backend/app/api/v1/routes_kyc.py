"""
KYC / KYB endpoints — the record the client submits and GEX vets.
==================================================================
Replaces `frontend/src/features/kyc/kycState.ts`, which held all of this in
`localStorage`. The response shape of `GET /state` deliberately mirrors that
module's `KycState`, so the frontend swap is a change of persistence and not a
rewrite of two pages.

WHO CAN SEE WHAT
----------------
Migration 051's policies do the real enforcement; these routes state the same
rule one layer up so a caller gets a 403 rather than a silently empty result:

  · a user reads and writes their OWN kyc_profile — not a colleague's
  · the KYB record is the legal entity's, so it is company-scoped
  · GEX staff (is_platform_admin) may read any profile, because vetting is
    what KYC is FOR — the deliberate opposite of the canvas, which staff
    cannot read at all

PROVENANCE
----------
`provenance` is accepted on write (SEED / EXTERNAL_PRIOR / CLIENT_ASSERTED) so
a prospect's record can be pre-filled from OSINT, a publication or the geomap
and still say so. VERIFIED is NOT writable here: it is set only by
`POST /kyc/verify/{user_id}`, which requires GEX staff and records who and
when. Editing a profile clears any verification, because a record that changed
after it was checked has not been checked.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core import kyc_store
from app.core.auth import has_platform_admin_access

router = APIRouter()


def _payload(request: Request) -> dict[str, Any]:
    """The authenticated identity, or 401. Defence in depth: `main.py` already
    applies `require_authenticated` app-wide."""
    payload = getattr(request.state, "auth_user_payload", None) or getattr(
        request.state, "user_payload", None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required")
    return payload


def _identity(request: Request) -> tuple[str, str]:
    payload = _payload(request)
    user_id = payload.get("user_id")
    company_id = payload.get("company_id")
    if not user_id or not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token carries no user_id/company_id — cannot scope a KYC record")
    return user_id, company_id


class ProfileIn(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)
    kyc_role: Optional[str] = None
    completed: bool = False
    provenance: str = "CLIENT_ASSERTED"
    source_ref: Optional[str] = None


class KybIn(BaseModel):
    legal_name: str
    registration_number: str
    country: str
    registered_address: str
    responsible_name: str
    responsible_email: str
    vat_id: Optional[str] = None
    beneficial_owners: Optional[str] = None
    responsible_job_title: Optional[str] = None
    status: str = "completed"
    provenance: str = "CLIENT_ASSERTED"
    source_ref: Optional[str] = None


class InvitationIn(BaseModel):
    email: str
    company_name: str
    company_domain: Optional[str] = None


@router.get("/state")
def kyc_state(request: Request) -> dict[str, Any]:
    """Everything the KYC/KYB screens need, in one call.

    Shaped like the old localStorage `KycState` so the frontend can swap its
    persistence without rewriting the pages: kycCompleted, kycRole, kycProfile,
    company, kybStatus, kybData — plus the provenance the browser never had.
    """
    user_id, company_id = _identity(request)
    profile = kyc_store.get_profile(user_id)
    kyb = kyc_store.get_kyb(company_id)
    return {
        "kycCompleted": bool(profile and profile.get("completed")),
        "kycRole": (profile or {}).get("kyc_role"),
        "kycProfile": (profile or {}).get("profile"),
        "company": company_id,
        "kybStatus": (kyb or {}).get("status", "none"),
        "kybData": kyb,
        "provenance": {
            "kyc": (profile or {}).get("provenance"),
            "kyb": (kyb or {}).get("provenance"),
        },
        "verified": {
            "kyc_by": (profile or {}).get("verified_by"),
            "kyc_at": (profile or {}).get("verified_at"),
        },
    }


@router.put("/profile")
def put_profile(body: ProfileIn, request: Request) -> dict[str, Any]:
    user_id, company_id = _identity(request)
    try:
        return kyc_store.upsert_profile(
            user_id, company_id, profile=body.profile, kyc_role=body.kyc_role,
            completed=body.completed, provenance=body.provenance,
            source_ref=body.source_ref)
    except kyc_store.KycError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/kyb")
def get_kyb(request: Request) -> dict[str, Any] | None:
    _, company_id = _identity(request)
    return kyc_store.get_kyb(company_id)


@router.put("/kyb")
def put_kyb(body: KybIn, request: Request) -> dict[str, Any]:
    _, company_id = _identity(request)
    try:
        return kyc_store.upsert_kyb(company_id, **body.model_dump())
    except kyc_store.KycError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/kyb/invitations")
def list_invitations(request: Request) -> list[dict[str, Any]]:
    _, company_id = _identity(request)
    return kyc_store.list_invitations(company_id)


@router.post("/kyb/invitations", status_code=201)
def create_invitation(body: InvitationIn, request: Request) -> dict[str, Any]:
    payload = _payload(request)
    user_id, company_id = _identity(request)
    try:
        return kyc_store.create_invitation(
            company_id, email=body.email, company_name=body.company_name,
            company_domain=body.company_domain, invited_by=user_id,
            invited_by_name=payload.get("user_name"))
    except kyc_store.KycError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/kyb/invitations/accept")
def accept_invitation(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Take up an invitation. The row stays, stamped with when it was accepted."""
    _, company_id = _identity(request)
    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=422, detail="email is required")
    return {"accepted": kyc_store.accept_invitation(company_id, email)}


@router.post("/verify/{subject_user_id}")
def verify_profile(subject_user_id: str, request: Request) -> dict[str, Any]:
    """Record that GEX checked a submission. Staff only, and never your own.

    Separation of duties is the same rule `account_lifecycle` applies to
    activation: the person who claims is not the person who verifies.
    """
    payload = _payload(request)
    if not has_platform_admin_access(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verifying a KYC submission is a GEX staff action")
    try:
        return kyc_store.verify(subject_user_id, verified_by=payload["user_id"])
    except kyc_store.KycError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import-local")
def import_local(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """One-time import of whatever a browser still holds in `gex_kyc_state`.

    The frontend calls this once per browser, then deletes its local copy. The
    import is written as **CLIENT_ASSERTED**, not VERIFIED: the user did type
    it, so it is their assertion — but nobody has checked it, and the browser
    could never have told us otherwise.
    """
    user_id, company_id = _identity(request)
    profile = body.get("kycProfile") or {}
    kyb = body.get("kybData") or None
    imported = {"profile": False, "kyb": False}

    if profile:
        kyc_store.upsert_profile(
            user_id, company_id, profile=profile,
            kyc_role=body.get("kycRole"), completed=bool(body.get("kycCompleted")),
            provenance="CLIENT_ASSERTED", source_ref="imported from browser localStorage")
        imported["profile"] = True

    if kyb and kyb.get("legalName") and kyb.get("registrationNumber"):
        kyc_store.upsert_kyb(
            company_id,
            legal_name=kyb["legalName"], registration_number=kyb["registrationNumber"],
            country=kyb.get("country") or "", registered_address=kyb.get("registeredAddress") or "",
            responsible_name=kyb.get("responsibleName") or "",
            responsible_email=kyb.get("responsibleEmail") or "",
            vat_id=kyb.get("vatId"), beneficial_owners=kyb.get("beneficialOwners"),
            responsible_job_title=kyb.get("responsibleJobTitle"),
            status=body.get("kybStatus") or "completed",
            provenance="CLIENT_ASSERTED", source_ref="imported from browser localStorage")
        imported["kyb"] = True

    return {"imported": imported}
