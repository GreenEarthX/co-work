"""
GEX Bankability — Workflow State Management API (v2.0)

Endpoints:
  GET  /api/v1/workflow/{object_type}/{object_id}/state
  POST /api/v1/workflow/{object_type}/{object_id}/advance
  GET  /api/v1/workflow/pending-review       — objects awaiting analyst review
  GET  /api/v1/workflow/pending-approval     — objects awaiting CFO approval
"""
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.core.workflow import WorkflowState, advance_state, can_export, GOVERNED_OBJECTS

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────────────────

class AdvanceStateRequest(BaseModel):
    target_state: WorkflowState
    actor_role: str = "analyst"        # analyst | cfo | system
    rejection_reason: Optional[str] = None

class WorkflowStateResponse(BaseModel):
    object_type: str
    object_id: str
    state: WorkflowState
    computed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None
    export_hash: Optional[str] = None
    is_stale: bool = False

class PendingItem(BaseModel):
    object_type: str
    object_id: str
    project_id: str
    project_name: str
    state: WorkflowState
    age_hours: int
    submitted_by: str


# ── Demo state store (in-memory; replace with DB in production) ──────────────

_DEMO_STATES: dict[str, WorkflowState] = {}

def _key(object_type: str, object_id: str) -> str:
    return f"{object_type}:{object_id}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{object_type}/{object_id}/state", response_model=WorkflowStateResponse)
async def get_workflow_state(object_type: str, object_id: str):
    """Return current workflow state for a governed object."""
    if object_type not in GOVERNED_OBJECTS:
        raise HTTPException(
            status_code=400,
            detail=f"'{object_type}' is not a workflow-governed object. "
                   f"Governed objects: {sorted(GOVERNED_OBJECTS)}",
        )
    key = _key(object_type, object_id)
    state = _DEMO_STATES.get(key, WorkflowState.DRAFT)
    return WorkflowStateResponse(
        object_type=object_type,
        object_id=object_id,
        state=state,
        computed_at=datetime.now(timezone.utc).isoformat(),
        is_stale=False,
    )


@router.post("/{object_type}/{object_id}/advance")
async def advance_workflow_state(
    object_type: str,
    object_id: str,
    request: AdvanceStateRequest,
):
    """Advance or reject a workflow state. Returns new state on success."""
    if object_type not in GOVERNED_OBJECTS:
        raise HTTPException(status_code=400, detail=f"'{object_type}' is not workflow-governed.")

    key = _key(object_type, object_id)
    current = _DEMO_STATES.get(key, WorkflowState.DRAFT)

    result = advance_state(
        current_state=current,
        target_state=request.target_state,
        actor_role=request.actor_role,
        object_type=object_type,
        rejection_reason=request.rejection_reason,
    )

    if not result.success:
        raise HTTPException(status_code=409, detail=result.error)

    _DEMO_STATES[key] = result.new_state  # type: ignore[assignment]

    return {
        "object_type": object_type,
        "object_id": object_id,
        "previous_state": result.previous_state,
        "new_state": result.new_state,
        "transitioned_at": result.transitioned_at,
    }


@router.get("/pending-review")
async def get_pending_review():
    """All objects in COMPUTED state awaiting analyst review (sorted by age)."""
    # Demo data — replace with DB query in production
    return {
        "pending": [
            PendingItem(
                object_type="BankabilitySnapshot",
                object_id="snap-le-havre-001",
                project_id="proj_le_havre_eng",
                project_name="Le Havre e-NG",
                state=WorkflowState.COMPUTED,
                age_hours=3,
                submitted_by="system",
            ),
            PendingItem(
                object_type="SensitivityRun",
                object_id="sens-bremen-001",
                project_id="proj_bremen_h2",
                project_name="Bremen Green Hydrogen Plant",
                state=WorkflowState.COMPUTED,
                age_hours=18,
                submitted_by="system",
            ),
            PendingItem(
                object_type="OfftakeAssessment",
                object_id="offtake-helios-001",
                project_id="proj_helios_emethanol",
                project_name="Helios e-Methanol",
                state=WorkflowState.COMPUTED,
                age_hours=31,
                submitted_by="system",
            ),
        ],
        "total": 3,
    }


@router.get("/pending-approval")
async def get_pending_approval():
    """All objects in REVIEWED state awaiting CFO/authorized approver action."""
    return {
        "pending": [
            PendingItem(
                object_type="CapitalStackScenario",
                object_id="capstack-le-havre-001",
                project_id="proj_le_havre_eng",
                project_name="Le Havre e-NG",
                state=WorkflowState.REVIEWED,
                age_hours=6,
                submitted_by="j.dupont@gex.io",
            ),
            PendingItem(
                object_type="ICPack",
                object_id="icpack-le-havre-001",
                project_id="proj_le_havre_eng",
                project_name="Le Havre e-NG",
                state=WorkflowState.REVIEWED,
                age_hours=12,
                submitted_by="j.dupont@gex.io",
            ),
        ],
        "total": 2,
    }
