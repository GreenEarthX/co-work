"""
Adversarial Review API
======================
Platform-local review surfaces for adversarial agents.

This module does not call gex_pf_engine and is safe to add alongside the
existing proxy/microservice boundary.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.adversarial_reviews import (
    FinalStance,
    FindingClassification,
    FindingKind,
    FindingSeverity,
    HandoffStatus,
    ReviewStatus,
    add_finding,
    add_handoff,
    create_review,
    get_project_summary,
    get_review,
    init_adversarial_reviews_db,
    list_prompt_presets,
    list_reviews,
    update_review_status,
)

router = APIRouter(prefix="/adversarial-reviews", tags=["adversarial-reviews"])

try:
    init_adversarial_reviews_db()
except Exception:
    pass


class FindingCreate(BaseModel):
    kind: FindingKind
    classification: FindingClassification = FindingClassification.MISSING
    severity: FindingSeverity = FindingSeverity.MEDIUM
    title: str
    detail: str
    owner_role: Optional[str] = None
    blocking: bool = True
    evidence_refs: list[str] = Field(default_factory=list)
    created_by: str


class HandoffCreate(BaseModel):
    from_role: Optional[str] = None
    to_role: str
    plain_language: str
    status: HandoffStatus = HandoffStatus.OPEN
    due_at: Optional[str] = None
    created_by: str


class ReviewCreate(BaseModel):
    project_id: str
    actor_type: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_route: Optional[str] = None
    screen_title: Optional[str] = None
    prompt_preset_id: Optional[str] = None
    prompt_card_id: Optional[str] = None
    agent_id: Optional[str] = None
    employee_name: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    sophistication: Optional[int] = None
    summary: Optional[str] = None
    what_it_seems_to_do: Optional[str] = None
    what_it_gets_wrong: Optional[str] = None
    what_is_missing: Optional[str] = None
    what_feels_dangerous: Optional[str] = None
    cooperation_risk: Optional[str] = None
    trust_increase_needed: Optional[str] = None
    clean_handoff_note: Optional[str] = None
    final_stance: FinalStance
    trust_delta: int = 0
    created_by: str
    findings: list[FindingCreate] = Field(default_factory=list)
    handoffs: list[HandoffCreate] = Field(default_factory=list)


class ReviewStatusUpdate(BaseModel):
    status: ReviewStatus
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None


class PromptPresetOut(BaseModel):
    id: str
    prompt_card_id: str
    agent_id: str
    employee_name: str
    actor_type: str
    category: str
    subtype: str
    sophistication: int
    tone: str
    trust_trigger: str
    cooperation_priority: str
    description: str


class FindingOut(BaseModel):
    id: str
    review_id: str
    kind: str
    classification: str
    severity: str
    title: str
    detail: str
    owner_role: Optional[str] = None
    blocking: bool
    evidence_refs: list[str]
    created_by: str
    created_at: str


class HandoffOut(BaseModel):
    id: str
    review_id: str
    from_role: Optional[str] = None
    to_role: str
    plain_language: str
    status: str
    due_at: Optional[str] = None
    created_by: str
    created_at: str


class ReviewOut(BaseModel):
    id: str
    project_id: str
    actor_type: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_route: Optional[str] = None
    screen_title: Optional[str] = None
    prompt_preset_id: Optional[str] = None
    prompt_card_id: Optional[str] = None
    agent_id: Optional[str] = None
    employee_name: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    sophistication: Optional[int] = None
    summary: Optional[str] = None
    what_it_seems_to_do: Optional[str] = None
    what_it_gets_wrong: Optional[str] = None
    what_is_missing: Optional[str] = None
    what_feels_dangerous: Optional[str] = None
    cooperation_risk: Optional[str] = None
    trust_increase_needed: Optional[str] = None
    clean_handoff_note: Optional[str] = None
    final_stance: str
    trust_delta: int
    status: str
    created_by: str
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    correlation_id: str
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    blocking_findings: int
    critical_findings: int
    findings: list[FindingOut]
    handoffs: list[HandoffOut]


class ReviewSummaryOut(BaseModel):
    project_id: str
    actor_type: Optional[str] = None
    total_reviews: int
    open_reviews: int
    escalated_reviews: int
    resolved_reviews: int
    blocking_findings: int
    critical_findings: int
    net_trust_delta: int
    owner_roles: list[str]
    stance_counts: dict[str, int]
    recent_reviews: list[dict]
    recommended_presets: list[PromptPresetOut]


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "adversarial_reviews",
        "engine_scope": "platform_only",
        "gex_pf_engine_dependency": "none",
    }


@router.get("/prompt-presets", response_model=list[PromptPresetOut])
def prompt_presets(actor_type: Optional[str] = None):
    return list_prompt_presets(actor_type)


@router.get("/project/{project_id}/summary", response_model=ReviewSummaryOut)
def project_summary(project_id: str, actor_type: Optional[str] = None):
    return get_project_summary(project_id=project_id, actor_type=actor_type)


@router.get("/project/{project_id}", response_model=list[ReviewOut])
def project_reviews(
    project_id: str,
    actor_type: Optional[str] = None,
    status_filter: Optional[ReviewStatus] = None,
):
    return list_reviews(
        project_id=project_id,
        actor_type=actor_type,
        status=status_filter.value if status_filter else None,
    )


@router.post("/", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create(body: ReviewCreate):
    review = create_review(
        project_id=body.project_id,
        actor_type=body.actor_type,
        target_type=body.target_type,
        target_id=body.target_id,
        target_route=body.target_route,
        screen_title=body.screen_title,
        prompt_preset_id=body.prompt_preset_id,
        prompt_card_id=body.prompt_card_id,
        agent_id=body.agent_id,
        employee_name=body.employee_name,
        category=body.category,
        subtype=body.subtype,
        sophistication=body.sophistication,
        summary=body.summary,
        what_it_seems_to_do=body.what_it_seems_to_do,
        what_it_gets_wrong=body.what_it_gets_wrong,
        what_is_missing=body.what_is_missing,
        what_feels_dangerous=body.what_feels_dangerous,
        cooperation_risk=body.cooperation_risk,
        trust_increase_needed=body.trust_increase_needed,
        clean_handoff_note=body.clean_handoff_note,
        final_stance=body.final_stance.value,
        trust_delta=body.trust_delta,
        created_by=body.created_by,
        initial_findings=[finding.model_dump() for finding in body.findings],
        initial_handoffs=[handoff.model_dump() for handoff in body.handoffs],
    )
    return review


@router.get("/{review_id}", response_model=ReviewOut)
def by_id(review_id: str):
    review = get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Adversarial review not found")
    return review


@router.post("/{review_id}/findings", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
def create_finding(review_id: str, body: FindingCreate):
    try:
        return add_finding(
            review_id=review_id,
            kind=body.kind.value,
            classification=body.classification.value,
            severity=body.severity.value,
            title=body.title,
            detail=body.detail,
            owner_role=body.owner_role,
            blocking=body.blocking,
            evidence_refs=body.evidence_refs,
            created_by=body.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{review_id}/handoffs", response_model=HandoffOut, status_code=status.HTTP_201_CREATED)
def create_handoff(review_id: str, body: HandoffCreate):
    try:
        return add_handoff(
            review_id=review_id,
            from_role=body.from_role,
            to_role=body.to_role,
            plain_language=body.plain_language,
            status=body.status.value,
            due_at=body.due_at,
            created_by=body.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{review_id}/status", response_model=ReviewOut)
def change_status(review_id: str, body: ReviewStatusUpdate):
    try:
        return update_review_status(
            review_id=review_id,
            status=body.status.value,
            resolution_note=body.resolution_note,
            resolved_by=body.resolved_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
