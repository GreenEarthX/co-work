"""
GEX Deal-Killer API — R1/R10 (Architectural Reform v6.0)

Serves deal-killer evaluation results for a project.
Used by DealKillerBanner.tsx (all workspaces) and IC Pack export gating.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.deal_killers import (
    DealKillerEngine,
    KillerSeverity,
    KillerStatus,
    DEAL_KILLERS_BY_ID,
)
from app.core.project_truth import build_deal_killer_project_data
from app.core.workflow import can_export_ic_pack, WorkflowState

router = APIRouter(prefix="/deal-killers", tags=["deal-killers"])
engine = DealKillerEngine()


# ─── Response schemas ─────────────────────────────────────────────────────────

class ActiveKillerOut(BaseModel):
    id:             str
    gate:           str
    severity:       str
    plain_language: str
    action:         str
    page:           str


class DealKillerStatusOut(BaseModel):
    project_id:           str
    committee_status:     str       # READY | NOT_READY | CONDITIONAL
    conditions:           list[str]
    blockers:             list[str]
    active_killers:       list[ActiveKillerOut]
    fatal_count:          int
    critical_count:       int


class ICPackExportCheckOut(BaseModel):
    allowed:      bool
    blockers:     list[str]
    resolution:   list[str]
    error_code:   str | None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}",
    response_model=DealKillerStatusOut,
    summary="Get active deal-killers for a project",
)
async def get_deal_killers(project_id: str) -> DealKillerStatusOut:
    """
    Evaluates all 8 deal-killers against current project state.
    Returns active killers with plain-language descriptions and resolution links.

    Used by:
    - DealKillerBanner.tsx (all workspaces)
    - TaskRouter flow step 2 (status_detail)
    - BankabilityScorePage.tsx (committee readiness)
    - IC Pack export gate check
    """
    project_data = build_deal_killer_project_data(project_id)
    active = engine.get_active_killers(project_data)
    readiness = engine.committee_ready(project_data)

    fatal_active    = [k for k in active if k.severity == KillerSeverity.FATAL]
    critical_active = [k for k in active if k.severity == KillerSeverity.CRITICAL]

    return DealKillerStatusOut(
        project_id=project_id,
        committee_status=readiness["status"],
        conditions=readiness["conditions"],
        blockers=readiness["blockers"],
        active_killers=[
            ActiveKillerOut(
                id=k.id,
                gate=k.gate,
                severity=k.severity.value,
                plain_language=k.plain_language,
                action=k.resolution_action,
                page=k.resolution_page,
            )
            for k in active
        ],
        fatal_count=len(fatal_active),
        critical_count=len(critical_active),
    )


@router.get(
    "/{project_id}/ic-pack-export-check",
    response_model=ICPackExportCheckOut,
    summary="R10: Check whether IC Pack export is permitted",
)
async def check_ic_pack_export(
    project_id:              str,
    workflow_state:          str  = "APPROVED",
    reviewer_user_id:        str | None = None,
    g8_is_audit_grade:       bool = False,
    unverified_section_count: int = 0,
) -> ICPackExportCheckOut:
    """
    R10: IC Pack export gate check.

    Returns allowed=True only when:
    1. workflow_state = APPROVED
    2. reviewer_user_id is set
    3. No FATAL deal-killers ACTIVE
    4. G8 financial model is AUDIT_GRADE
    5. unverified_section_count = 0

    Used by ICPackBuilder.tsx export button to show/block the export action.
    """
    project_data  = build_deal_killer_project_data(project_id)
    has_fatal     = engine.has_fatal(project_data)

    try:
        ws = WorkflowState(workflow_state.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid workflow_state: {workflow_state}",
        )

    allowed, blockers, resolutions = can_export_ic_pack(
        workflow_state=ws,
        reviewer_user_id=reviewer_user_id,
        has_fatal_deal_killers=has_fatal,
        g8_is_audit_grade=g8_is_audit_grade,
        unverified_section_count=unverified_section_count,
    )

    return ICPackExportCheckOut(
        allowed=allowed,
        blockers=blockers,
        resolution=resolutions,
        error_code="IC_PACK_EXPORT_BLOCKED" if not allowed else None,
    )
