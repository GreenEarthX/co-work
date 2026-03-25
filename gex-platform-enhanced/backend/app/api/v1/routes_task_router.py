"""
GEX Task Router API — R6 (Architectural Reform v6.0)

Serves guided flows for workspace landing pages.
Each workspace replaces its dashboard with a TaskRouter component
that calls this endpoint to get the actor-specific flow.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.task_router import ActorType, FlowStep, ActorFlow, task_router_engine, StepStatus

router = APIRouter(prefix="/task-flow", tags=["task-router"])


# ─── Response schemas ─────────────────────────────────────────────────────────

class FlowStepOut(BaseModel):
    number:         int
    title:          str
    description:    str
    page:           str
    status:         str
    status_detail:  str
    blocked_by:     list[str]


class ActorFlowOut(BaseModel):
    actor_type:           str
    project_id:           str
    objective:            str
    overall_status:       str
    steps:                list[FlowStepOut]
    fatal_killers_active: int
    next_action:          str
    next_action_page:     str


def _serialize_flow(flow: ActorFlow) -> ActorFlowOut:
    return ActorFlowOut(
        actor_type=flow.actor_type.value,
        project_id=flow.project_id,
        objective=flow.objective,
        overall_status=flow.overall_status,
        fatal_killers_active=flow.fatal_killers_active,
        next_action=flow.next_action,
        next_action_page=flow.next_action_page,
        steps=[
            FlowStepOut(
                number=s.number,
                title=s.title,
                description=s.description,
                page=s.page,
                status=s.status.value,
                status_detail=s.status_detail,
                blocked_by=s.blocked_by,
            )
            for s in flow.steps
        ],
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/{actor_type}/{project_id}",
    response_model=ActorFlowOut,
    summary="Get the guided flow for this actor on this project",
)
async def get_flow(actor_type: str, project_id: str) -> ActorFlowOut:
    """
    Returns the step-by-step guided flow for the calling actor.
    Replaces the workspace dashboard as the landing view.

    actor_type: COMMERCIAL_BANKER | OFFTAKER | CREDIT_COMMITTEE_CHAIR | PRODUCER

    In production: project_data is fetched from DB + engine.
    Demo mode uses representative data.
    """
    try:
        at = ActorType(actor_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown actor_type: {actor_type}. Valid values: {[a.value for a in ActorType]}",
        )

    # Demo project data — replace with DB query in production
    demo_data: dict = {
        "active_fatal_killers":         2,
        "g8_is_audit_grade":            False,
        "snapshot_viewed_within_7_days": False,
        "evidence_confirmed_pct":       42.0,
        "capital_stack_committed":      False,
        "requirement_defined":          False,
        "qualified_offers_count":       3,
        "shortlist_count":              0,
        "evidence_audited_count":       6,
        "evidence_total_count":         47,
        "plant_configured":             True,
        "next_gate_missing_items":      4,
    }

    flow = task_router_engine.get_flow(at, project_id, demo_data)
    return _serialize_flow(flow)


@router.post(
    "/{actor_type}/{project_id}/step/{step_number}/complete",
    response_model=FlowStepOut,
    summary="Mark a flow step as complete",
)
async def complete_step(
    actor_type:  str,
    project_id:  str,
    step_number: int,
) -> FlowStepOut:
    """
    Mark a step as DONE. Updates the actor's flow progress.
    In production: persists step completion to user_flow_state table.
    """
    try:
        at = ActorType(actor_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown actor_type: {actor_type}",
        )

    demo_data: dict = {
        "active_fatal_killers": 2,
        "g8_is_audit_grade": False,
        "snapshot_viewed_within_7_days": True,
        "evidence_confirmed_pct": 42.0,
        "capital_stack_committed": False,
    }

    step = task_router_engine.complete_step(at, project_id, step_number, demo_data)
    return FlowStepOut(
        number=step.number,
        title=step.title,
        description=step.description,
        page=step.page,
        status=step.status.value,
        status_detail=step.status_detail,
        blocked_by=step.blocked_by,
    )
