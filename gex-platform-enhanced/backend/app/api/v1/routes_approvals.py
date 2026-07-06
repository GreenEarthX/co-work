"""
WAE Approval Queue API
========================
Endpoints for approval workflow management.
Consumed by ApprovalQueuePage (Finance, Executive) and ApprovalBanner (all workspaces).
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.wae import (
    evaluate_authorization, record_decision, get_pending_approvals,
    get_request, get_audit_trail, init_wae_db,
    ApprovalDecision, AuthorizationOutcome, APPROVAL_POLICIES,
)
from app.core.sod import get_conflict_pairs, init_sod_db
from app.services.approval_notifier import notify_approval_requested, notify_approval_decided

router = APIRouter()

# Ensure tables
try:
    init_wae_db()
    init_sod_db()
except Exception:
    pass


# ─── Models ──────────────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    action_type: str
    resource_id: Optional[str] = None
    project_id: Optional[str] = None
    payload: dict = {}
    amount: Optional[float] = None
    volume: Optional[float] = None
    initiator_user_id: Optional[str] = None  # fallback if x-demo-user header absent


class DecideRequest(BaseModel):
    decision: str   # APPROVE | REJECT
    reason_text: Optional[str] = None
    approver_user_id: Optional[str] = None  # fallback if x-demo-user header absent


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health")
def approvals_health():
    return {"status": "ok", "service": "wae_approvals"}


@router.post("/evaluate")
def evaluate(
    body: EvaluateRequest,
    x_demo_user: Optional[str] = Header(default=None),
):
    """
    Evaluate whether an action requires approval.
    Returns IMMEDIATE or PENDING_APPROVAL + request_id.
    """
    user_id = x_demo_user or body.initiator_user_id or "unknown_user"
    decision = evaluate_authorization(
        initiator_user_id=user_id,
        action_type=body.action_type,
        resource_id=body.resource_id,
        project_id=body.project_id,
        payload=body.payload,
        amount=body.amount,
        volume=body.volume,
    )

    if decision.outcome == AuthorizationOutcome.PENDING_APPROVAL:
        notify_approval_requested(
            project_id=body.project_id or "unknown",
            request_id=decision.request_id or "",
            action_type=body.action_type,
            initiator_user_id=user_id,
            required_roles=decision.required_roles,
        )
        return {
            "outcome": decision.outcome.value,
            "request_id": decision.request_id,
            "required_roles": decision.required_roles,
            "min_approvers": decision.min_approvers,
            "message": f"Action requires approval from {decision.min_approvers} of: {', '.join(decision.required_roles)}",
        }

    return {
        "outcome": decision.outcome.value,
        "reason": decision.reason,
    }


@router.get("/pending")
def list_pending(
    project_id: Optional[str] = None,
    company_id: Optional[str] = None,
    x_demo_company: Optional[str] = Header(default=None),
):
    """All pending approval requests. Filtered by project and/or company."""
    resolved_company = x_demo_company or company_id
    items = get_pending_approvals(
        company_id=resolved_company,
        project_id=project_id,
    )
    return {"total": len(items), "items": items}


@router.get("/{request_id}")
def get_approval_request(
    request_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return req


@router.post("/{request_id}/decide")
def decide(
    request_id: str,
    body: DecideRequest,
    x_demo_user: Optional[str] = Header(default=None),
    x_demo_company: Optional[str] = Header(default=None),
):
    """Record an APPROVE or REJECT decision."""
    try:
        decision_enum = ApprovalDecision(body.decision.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail="Decision must be APPROVE or REJECT")

    approver = x_demo_user or body.approver_user_id or "unknown_approver"
    result = record_decision(
        request_id=request_id,
        approver_user_id=approver,
        decision=decision_enum,
        reason_text=body.reason_text,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Notify Matrix room
    req = get_request(request_id)
    if req:
        notify_approval_decided(
            project_id=req.get("project_id") or "unknown",
            request_id=request_id,
            decision=body.decision,
            approver_user_id=approver,
            new_status=result["new_status"],
        )

    return result


@router.get("/audit-trail/{resource_id}")
def audit_trail(
    resource_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Approval audit trail for a specific resource."""
    entries = get_audit_trail(resource_id)
    return {"resource_id": resource_id, "total": len(entries), "entries": entries}


@router.get("/policies/list")
def list_policies():
    """Returns configured approval policies."""
    return {"policies": APPROVAL_POLICIES}


@router.get("/sod/pairs")
def list_sod_pairs():
    """Returns active SoD conflict pairs."""
    pairs = get_conflict_pairs(active_only=True)
    if not pairs:
        # Return built-in
        from app.core.sod import SOD_CONFLICT_PAIRS
        pairs = [
            {
                "id": p["id"],
                "action_a": p["action_a"],
                "action_b": p["action_b"],
                "resource_scope": p["resource_scope"].value if hasattr(p["resource_scope"], "value") else p["resource_scope"],
                "description": p["description"],
                "active": True,
            }
            for p in SOD_CONFLICT_PAIRS
        ]
    return {"total": len(pairs), "pairs": pairs}
