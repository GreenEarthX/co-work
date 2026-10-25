"""
Commitment Signature Service (CSS) API
=======================================
Creates and verifies non-repudiable digital commitment records.
Called AFTER WAE approval quorum is reached.

Chain: ABAC → SoD → DRPL → WAE → [approval quorum] → CSS → DB

eIDAS 910/2014: signed records have EU legal standing (Tier 4: QTSP-backed).
Dev: HMAC-SHA256 with per-user derived key.

The signer is the signed-in account (2026-10-25). Until then the initiator and
the counterparty — user AND company — came from the request body, so anyone
could produce a "non-repudiable" signature in anyone's name, and any caller
could read any project's records. Now: identities from the token; records read
and written in the caller's tenant (RLS); approvers taken from the named WAE
request's recorded decisions, never from the body.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.css import (
    sign_commitment, countersign, verify_commitment,
    get_commitments_for_project, init_css_db,
)

router = APIRouter()

try:
    init_css_db()
except Exception:
    pass


# ─── Models ──────────────────────────────────────────────────────────────────

class SignRequest(BaseModel):
    action_type: str
    project_id: str
    payload: dict
    approval_request_id: Optional[str] = None


def _caller(request: Request) -> tuple[str, str, str]:
    """(user_id, company_id, tenant) from the verified token; 401 without one."""
    from app.core.request_tenant import company_from_payload, payload_from_request, user_from_payload

    payload = payload_from_request(request) or {}
    user_id, tenant, company = user_from_payload(payload), company_from_payload(payload), payload.get("company_id")
    if not user_id or not tenant or not company:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id, company, tenant


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health")
def css_health():
    return {
        "status": "ok",
        "service": "commitment_signature",
        "algorithm": "HMAC-SHA256 (dev)",
        "tier4_note": "eIDAS QTSP / HSM integration enabled in Tier 4",
    }


@router.post("/sign")
def sign(body: SignRequest, request: Request):
    """
    Create a signed commitment record for a binding action, as the signed-in
    account. A named approval request must be APPROVED, on the same project and
    action; its recorded decisions become the approvers.
    """
    from app.core.wae import get_request

    user_id, company, tenant = _caller(request)
    approvers: list[dict] = []
    if body.approval_request_id:
        req = get_request(body.approval_request_id, company_id=tenant)
        if not req:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if req["status"] != "APPROVED" or req["project_id"] != body.project_id or req["action_type"] != body.action_type:
            raise HTTPException(status_code=409, detail={
                "code": "APPROVAL_DOES_NOT_COVER", "message": "The approval request is not APPROVED for this action and project."})
        approvers = [{"user_id": d["approver_user_id"], "decision": d["decision"], "decided_at": str(d.get("decided_at"))}
                     for d in req["decisions"] if d["decision"] == "APPROVE"]
    try:
        commitment = sign_commitment(
            initiator_user_id=user_id,
            initiator_company_id=company,
            action_type=body.action_type,
            project_id=body.project_id,
            payload=body.payload,
            approval_request_id=body.approval_request_id,
            approver_snapshots=approvers,
            company_id=tenant,
        )
    except Exception:
        raise HTTPException(status_code=403, detail="You cannot sign a commitment on this project.")
    return {
        "commitment_id": commitment.commitment_id,
        "action_type": commitment.action_type,
        "project_id": commitment.project_id,
        "initiator_user_id": commitment.initiator_user_id,
        "initiator_company_id": commitment.initiator_company_id,
        "initiator_timestamp": commitment.initiator_timestamp,
        "initiator_signature": commitment.initiator_signature,
        "payload_hash": commitment.payload_hash,
        "record_hash": commitment.record_hash,
        "approvers": commitment.approvers,
        "status": commitment.status,
    }


@router.post("/{commitment_id}/countersign")
def countersign_commitment(commitment_id: str, request: Request):
    """
    Counterparty acceptance signature for bilateral acts (trades, PPAs, NDAs),
    by the signed-in account, of a company other than the initiator's.
    """
    user_id, company, tenant = _caller(request)
    rec = verify_commitment(commitment_id, company_id=tenant)
    if rec.get("error") == "Not found":
        raise HTTPException(status_code=404, detail="Commitment not found")
    if rec["initiator_company_id"] == company:
        raise HTTPException(status_code=403, detail={
            "code": "SAME_COMPANY", "message": "A countersignature comes from the other party."})
    result = countersign(
        commitment_id=commitment_id,
        counterparty_user_id=user_id,
        counterparty_company_id=company,
    )
    if "error" in result:
        status_code = 404 if "not found" in result["error"].lower() else 409
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result


@router.get("/{commitment_id}/verify")
def verify(commitment_id: str, request: Request):
    """
    Verify all signatures and record hash for a commitment the caller may see.
    Returns valid=True if record has not been tampered with.
    """
    _, _, tenant = _caller(request)
    result = verify_commitment(commitment_id, company_id=tenant)
    if not result.get("valid") and result.get("error") == "Not found":
        raise HTTPException(status_code=404, detail="Commitment not found")
    return result


@router.get("/project/{project_id}")
def list_for_project(project_id: str, request: Request):
    """The project's commitment records the caller may see (newest first)."""
    _, _, tenant = _caller(request)
    records = get_commitments_for_project(project_id, company_id=tenant)
    return {"project_id": project_id, "total": len(records), "commitments": records}


@router.get("/{commitment_id}")
def get_commitment(commitment_id: str, request: Request):
    """Retrieve a single commitment record by ID, if the caller may see it."""
    _, _, tenant = _caller(request)
    result = verify_commitment(commitment_id, company_id=tenant)
    if result.get("error") == "Not found":
        raise HTTPException(status_code=404, detail="Commitment not found")
    return result
