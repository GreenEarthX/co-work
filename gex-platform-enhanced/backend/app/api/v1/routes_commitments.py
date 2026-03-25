"""
Commitment Signature Service (CSS) API
=======================================
Creates and verifies non-repudiable digital commitment records.
Called AFTER WAE approval quorum is reached.

Chain: ABAC → SoD → DRPL → WAE → [approval quorum] → CSS → DB

eIDAS 910/2014: signed records have EU legal standing (Tier 4: QTSP-backed).
Dev: HMAC-SHA256 with per-user derived key.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException
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
    initiator_user_id: str
    initiator_company_id: str
    action_type: str
    project_id: str
    payload: dict
    approval_request_id: Optional[str] = None
    approver_snapshots: Optional[list[dict]] = None


class CountersignRequest(BaseModel):
    counterparty_user_id: str
    counterparty_company_id: str


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
def sign(
    body: SignRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Create a signed commitment record for a binding action.
    Caller must have obtained WAE approval (approval_request_id) before calling.
    Returns commitment_id, payload_hash, record_hash, and initiator signature.
    """
    commitment = sign_commitment(
        initiator_user_id=body.initiator_user_id,
        initiator_company_id=body.initiator_company_id,
        action_type=body.action_type,
        project_id=body.project_id,
        payload=body.payload,
        approval_request_id=body.approval_request_id,
        approver_snapshots=body.approver_snapshots,
    )
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
def countersign_commitment(
    commitment_id: str,
    body: CountersignRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Counterparty acceptance signature for bilateral acts (trades, PPAs, NDAs).
    Transitions status from SIGNED_BY_INITIATOR → COUNTERSIGNED.
    """
    result = countersign(
        commitment_id=commitment_id,
        counterparty_user_id=body.counterparty_user_id,
        counterparty_company_id=body.counterparty_company_id,
    )
    if "error" in result:
        status_code = 404 if "not found" in result["error"].lower() else 409
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result


@router.get("/{commitment_id}/verify")
def verify(
    commitment_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Verify all signatures and record hash for a commitment.
    Returns valid=True if record has not been tampered with.
    Used by CISO audit trail and counterparty due diligence views.
    """
    result = verify_commitment(commitment_id)
    if not result.get("valid") and result.get("error") == "Not found":
        raise HTTPException(status_code=404, detail="Commitment not found")
    return result


@router.get("/project/{project_id}")
def list_for_project(
    project_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """List all commitment records for a project (newest first)."""
    records = get_commitments_for_project(project_id)
    return {"project_id": project_id, "total": len(records), "commitments": records}


@router.get("/{commitment_id}")
def get_commitment(
    commitment_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Retrieve a single commitment record by ID."""
    result = verify_commitment(commitment_id)
    if result.get("error") == "Not found":
        raise HTTPException(status_code=404, detail="Commitment not found")
    return result
