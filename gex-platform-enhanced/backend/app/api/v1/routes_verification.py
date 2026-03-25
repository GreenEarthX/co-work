"""
GEX Verification API — R0 (Architectural Reform v6.0)

Endpoints for advancing evidence verification state and querying
per-gate verification summaries.

All transitions are validated by VerificationEngine before persistence.
Every transition is written to verification_log (append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.verification import (
    VerificationEngine,
    VerificationError,
    VerificationState,
    VERIFICATION_COLORS,
    VERIFICATION_LABELS,
    VERIFICATION_WEIGHTS,
)

router = APIRouter(prefix="/verification", tags=["verification"])
engine = VerificationEngine()


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class TransitionRequest(BaseModel):
    resource_type:       str  = Field(..., description="e.g. bankability_evidence, marketplace_offer")
    resource_id:         str  = Field(..., description="UUID of the target resource")
    current_state:       Optional[VerificationState] = Field(None, description="Current state (None for initial upload)")
    target_state:        VerificationState
    actor_user_id:       str  = Field(..., description="GEX user ID performing the transition")
    verifier_firm:       Optional[str] = Field(None, description="Required for CONFIRMED and AUDITED")
    verifier_reference:  Optional[str] = Field(None, description="Required for AUDITED")
    verifier_scope:      Optional[str] = Field(None, description="e.g. 'FEED review', 'Full audit'")
    verifier_exceptions: Optional[str] = Field(None, description="Any qualifications or exceptions noted")


class TransitionResponse(BaseModel):
    log_id:          str
    resource_type:   str
    resource_id:     str
    previous_state:  Optional[str]
    new_state:       str
    new_state_color: str
    new_state_label: str
    verifier_firm:   Optional[str]
    transitioned_at: str


class VerificationStatusResponse(BaseModel):
    resource_type:    str
    resource_id:      str
    current_state:    str
    state_label:      str
    state_color:      str
    weight:           float
    verifier_firm:    Optional[str]
    verifier_date:    Optional[str]
    verifier_reference: Optional[str]
    history:          list[dict]


class GateSummaryEntry(BaseModel):
    gate_id:          str
    UNVERIFIED:       int
    SUBMITTED:        int
    CONFIRMED:        int
    AUDITED:          int
    total:            int
    raw_score:        float
    effective_score:  float


class GateSummaryResponse(BaseModel):
    project_id: str
    gates:      list[GateSummaryEntry]


class AuditLogEntry(BaseModel):
    log_id:          str
    resource_type:   str
    resource_id:     str
    previous_state:  Optional[str]
    new_state:       str
    actor_user_id:   str
    verifier_firm:   Optional[str]
    verifier_reference: Optional[str]
    transitioned_at: str


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/transition",
    response_model=TransitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Advance a resource's verification state",
)
async def transition_verification_state(body: TransitionRequest) -> TransitionResponse:
    """
    Validate and advance a resource's verification state.

    Rules enforced:
    - Only valid transitions are allowed (see verification.py VALID_TRANSITIONS)
    - CONFIRMED requires verifier_firm
    - AUDITED requires verifier_firm + verifier_reference
    - Every transition creates an immutable record in verification_log

    In production: caller must persist the record to DB and update
    the verification_state column on the target resource.
    """
    try:
        record = engine.transition(
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            current_state=body.current_state,
            target_state=body.target_state,
            actor_user_id=body.actor_user_id,
            verifier_firm=body.verifier_firm,
            verifier_reference=body.verifier_reference,
            verifier_scope=body.verifier_scope,
            verifier_exceptions=body.verifier_exceptions,
        )
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "VERIFICATION_TRANSITION_BLOCKED",
                "message": str(exc),
            },
        ) from exc

    log_id = str(uuid.uuid4())

    return TransitionResponse(
        log_id=log_id,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        previous_state=record.previous_state.value if record.previous_state else None,
        new_state=record.new_state.value,
        new_state_color=VERIFICATION_COLORS[record.new_state],
        new_state_label=VERIFICATION_LABELS[record.new_state],
        verifier_firm=record.verifier_firm,
        transitioned_at=record.transitioned_at,
    )


@router.get(
    "/status/{resource_type}/{resource_id}",
    response_model=VerificationStatusResponse,
    summary="Get current verification state + history for a resource",
)
async def get_verification_status(
    resource_type: str,
    resource_id:   str,
) -> VerificationStatusResponse:
    """
    Returns the current verification state and audit history for
    a specific resource (evidence item, offer, tranche, etc.).

    In production: queries bankability_evidence + verification_log.
    Demo mode returns a synthetic SUBMITTED state.
    """
    # Demo fallback — replace with DB query in production
    current = VerificationState.SUBMITTED
    return VerificationStatusResponse(
        resource_type=resource_type,
        resource_id=resource_id,
        current_state=current.value,
        state_label=VERIFICATION_LABELS[current],
        state_color=VERIFICATION_COLORS[current],
        weight=VERIFICATION_WEIGHTS[current],
        verifier_firm=None,
        verifier_date=None,
        verifier_reference=None,
        history=[
            {
                "previous_state": None,
                "new_state": "UNVERIFIED",
                "actor_user_id": "system",
                "transitioned_at": "2026-01-10T09:00:00Z",
            },
            {
                "previous_state": "UNVERIFIED",
                "new_state": "SUBMITTED",
                "actor_user_id": "usr_producer_01",
                "transitioned_at": "2026-02-14T14:30:00Z",
            },
        ],
    )


@router.get(
    "/summary/{project_id}",
    response_model=GateSummaryResponse,
    summary="Per-gate verification summary for a project",
)
async def get_verification_summary(project_id: str) -> GateSummaryResponse:
    """
    Returns per-gate counts of evidence at each verification state,
    plus raw and effective (verification-weighted) gate scores.

    Used by: EvidenceHierarchy.tsx (Credit Committee Chair view)
             BankabilityScorePage.tsx (demoted analytics panel)
             IC Pack export gate check

    In production: joins bankability_evidence × verification_log for project.
    Demo mode returns synthetic data matching demo projects.
    """
    demo_gates = [
        {"gate_id": "G0", "UNVERIFIED": 0, "SUBMITTED": 0, "CONFIRMED": 3, "AUDITED": 1, "raw_score": 100.0},
        {"gate_id": "G1", "UNVERIFIED": 0, "SUBMITTED": 1, "CONFIRMED": 2, "AUDITED": 1, "raw_score": 95.0},
        {"gate_id": "G2", "UNVERIFIED": 0, "SUBMITTED": 0, "CONFIRMED": 2, "AUDITED": 2, "raw_score": 90.0},
        {"gate_id": "G3", "UNVERIFIED": 1, "SUBMITTED": 2, "CONFIRMED": 1, "AUDITED": 0, "raw_score": 80.0},
        {"gate_id": "G4", "UNVERIFIED": 1, "SUBMITTED": 2, "CONFIRMED": 3, "AUDITED": 0, "raw_score": 78.0},
        {"gate_id": "G5", "UNVERIFIED": 4, "SUBMITTED": 1, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 45.0},
        {"gate_id": "G6", "UNVERIFIED": 2, "SUBMITTED": 1, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 40.0},
        {"gate_id": "G7", "UNVERIFIED": 3, "SUBMITTED": 0, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 30.0},
        {"gate_id": "G8", "UNVERIFIED": 0, "SUBMITTED": 0, "CONFIRMED": 5, "AUDITED": 1, "raw_score": 68.0},
        {"gate_id": "G9", "UNVERIFIED": 2, "SUBMITTED": 2, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 20.0},
        {"gate_id": "G10", "UNVERIFIED": 4, "SUBMITTED": 0, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 10.0},
        {"gate_id": "G11", "UNVERIFIED": 2, "SUBMITTED": 0, "CONFIRMED": 0, "AUDITED": 0, "raw_score": 5.0},
    ]

    result = []
    for g in demo_gates:
        states: list[VerificationState] = []
        for state_val in VerificationState:
            states.extend([state_val] * g[state_val.value])

        effective = engine.compute_weighted_gate_score(g["raw_score"], states)
        total = sum(g[s.value] for s in VerificationState)

        result.append(GateSummaryEntry(
            gate_id=g["gate_id"],
            UNVERIFIED=g[VerificationState.UNVERIFIED.value],
            SUBMITTED=g[VerificationState.SUBMITTED.value],
            CONFIRMED=g[VerificationState.CONFIRMED.value],
            AUDITED=g[VerificationState.AUDITED.value],
            total=total,
            raw_score=g["raw_score"],
            effective_score=effective,
        ))

    return GateSummaryResponse(project_id=project_id, gates=result)


@router.get(
    "/log/{project_id}",
    response_model=list[AuditLogEntry],
    summary="Audit log of all verification transitions for a project",
)
async def get_verification_log(project_id: str) -> list[AuditLogEntry]:
    """
    Returns the complete, immutable audit trail of all verification
    state transitions for evidence items on a project.

    In production: SELECT * FROM verification_log
                   WHERE resource_id IN (evidence IDs for project)
                   ORDER BY transitioned_at DESC
    """
    # Demo entries
    return [
        AuditLogEntry(
            log_id="log_001",
            resource_type="bankability_evidence",
            resource_id="ev_g4_offtake",
            previous_state="SUBMITTED",
            new_state="CONFIRMED",
            actor_user_id="usr_ie_mottmacdonald",
            verifier_firm="Mott MacDonald",
            verifier_reference=None,
            transitioned_at="2026-03-10T11:22:00Z",
        ),
        AuditLogEntry(
            log_id="log_002",
            resource_type="bankability_evidence",
            resource_id="ev_g8_model",
            previous_state="CONFIRMED",
            new_state="AUDITED",
            actor_user_id="usr_kpmg_audit",
            verifier_firm="KPMG Project Finance",
            verifier_reference="KPMG-GEX-2026-0042",
            transitioned_at="2026-03-15T09:00:00Z",
        ),
    ]
