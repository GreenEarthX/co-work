"""
WAE Approval Queue API
========================
Endpoints for approval workflow management.
Consumed by ApprovalQueuePage (Finance, Executive) and ApprovalBanner (all workspaces).

Identity comes from the signed-in token only (2026-10-25). Until then the
initiator and approver were taken from the x-demo-user header or the request
body, so anyone could approve as anyone; and the pending list returned every
company's requests, whatever company was named. Requests are now read and
written in the caller's tenant (RLS: the project's owner and companies with
access); a decision must come from someone other than the initiator, of the
initiator's company, once.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request
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


class DecideRequest(BaseModel):
    decision: str   # APPROVE | REJECT
    reason_text: Optional[str] = None


# ─── Caller ──────────────────────────────────────────────────────────────────

def _caller(request: Request) -> tuple[str, str, dict]:
    """(user_id, tenant, payload) from the verified token; 401 without one."""
    from app.core.request_tenant import company_from_payload, payload_from_request, user_from_payload

    payload = payload_from_request(request) or {}
    user_id, tenant = user_from_payload(payload), company_from_payload(payload)
    if not user_id or not tenant:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id, tenant, payload


def _company_of(user_id: str) -> Optional[str]:
    from app.core.projects_store import _rows

    rows = _rows("SELECT company_id FROM auth_users WHERE user_id = :u", {"u": user_id})
    return rows[0]["company_id"] if rows else None


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health")
def approvals_health():
    return {"status": "ok", "service": "wae_approvals"}


@router.post("/evaluate")
def evaluate(body: EvaluateRequest, request: Request):
    """
    Evaluate whether an action requires approval.
    Returns IMMEDIATE or PENDING_APPROVAL + request_id.
    """
    user_id, tenant, _ = _caller(request)
    try:
        decision = evaluate_authorization(
            initiator_user_id=user_id,
            action_type=body.action_type,
            resource_id=body.resource_id,
            project_id=body.project_id,
            payload=body.payload,
            amount=body.amount,
            volume=body.volume,
            company_id=tenant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=403, detail="You cannot raise an approval request on this project.")

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
def list_pending(request: Request, project_id: Optional[str] = None):
    """Pending approval requests the caller's company may see."""
    _, tenant, _ = _caller(request)
    items = get_pending_approvals(company_id=tenant, project_id=project_id)
    return {"total": len(items), "items": items}


@router.get("/{request_id}")
def get_approval_request(request_id: str, request: Request):
    _, tenant, _ = _caller(request)
    req = get_request(request_id, company_id=tenant)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return req


@router.post("/{request_id}/decide")
def decide(request_id: str, body: DecideRequest, request: Request):
    """Record an APPROVE or REJECT decision by the signed-in account."""
    approver, tenant, payload = _caller(request)
    try:
        decision_enum = ApprovalDecision(body.decision.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail="Decision must be APPROVE or REJECT")

    req = get_request(request_id, company_id=tenant)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    # A countersignature is the initiator's own company's (GEX staff excepted):
    # a lender seeing the project does not approve the producer's spending.
    if not payload.get("is_platform_admin") and _company_of(approver) != _company_of(req["initiator_user_id"]):
        raise HTTPException(status_code=403, detail={
            "code": "OTHER_COMPANY", "message": "Only the initiator's company decides its approval requests."})

    result = record_decision(
        request_id=request_id,
        approver_user_id=approver,
        decision=decision_enum,
        reason_text=body.reason_text,
    )

    if "error" in result:
        status = 403 if result.get("code") == "SOD_SELF_APPROVAL" else 409 if result.get("code") else 400
        raise HTTPException(status_code=status, detail={"code": result.get("code"), "message": result["error"]})

    notify_approval_decided(
        project_id=req.get("project_id") or "unknown",
        request_id=request_id,
        decision=body.decision,
        approver_user_id=approver,
        new_status=result["new_status"],
    )
    return result


@router.get("/audit-trail/{resource_id}")
def audit_trail(resource_id: str, request: Request):
    """Approval audit trail for a specific resource, as far as the caller may see."""
    _, tenant, _ = _caller(request)
    entries = get_audit_trail(resource_id, company_id=tenant)
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
