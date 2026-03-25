"""
Project Quality Rating — stateless scoring endpoint.

Uses the GEX Project Quality Rating Engine (pure Python, no ORM).
No DB persistence in this version: POST computes and returns; GET /current
and GET /history return 501 until SQLite persistence is wired.

URL prefix (registered in main.py): /api/v1/project-ratings
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from app.core.gex_project_rating_engine import (
    ProjectInputs,
    GateStatus,
    QuantitativeInputs,
    calculate_project_rating,
)

router = APIRouter()


# ─── Request models ───────────────────────────────────────────────────────────

class GateStatusIn(BaseModel):
    land_and_permits_ok:  bool
    technology_wrap_ok:   bool
    regulatory_path_ok:   bool
    funding_path_ok:      bool
    revenue_path_ok:      bool
    traceability_ok:      bool


class ProjectInputsIn(BaseModel):
    project_id:                      Optional[str] = None
    project_name:                    str = Field(..., min_length=1)
    phase:                           str = Field(..., min_length=1)
    business_market:                 float = Field(..., ge=1.0, le=5.0)
    construction_technology:         float = Field(..., ge=1.0, le=5.0)
    legal_structural_counterparty:   float = Field(..., ge=1.0, le=5.0)
    sustainability_certification:    float = Field(..., ge=1.0, le=5.0)
    jurisdiction_notch:              int = Field(0, ge=-2, le=1)
    sponsor_support_notch:           int = Field(0, ge=-1, le=1)
    structure_notch:                 int = Field(0, ge=-2, le=1)
    market_exposure_notch:           int = Field(0, ge=-2, le=0)
    data_confidence_notch:           int = Field(0, ge=-1, le=1)
    payment_default:                 bool = False
    distressed_exchange:             bool = False
    outlook_bias:                    int = Field(0, ge=-1, le=1)


class QuantitativeInputsIn(BaseModel):
    downside_min_dscr:               float = Field(..., ge=0.0)
    base_case_dscr:                  float = Field(..., ge=0.0)
    llcr:                            float = Field(..., ge=0.0)
    contracted_revenue_pct:          float = Field(..., ge=0.0, le=100.0)
    merchant_exposure_pct:           float = Field(..., ge=0.0, le=100.0)
    equity_committed_pct_of_capex:   float = Field(..., ge=0.0, le=100.0)
    subsidy_dependence_pct_of_ebitda: float = Field(..., ge=0.0, le=100.0)
    schedule_buffer_months:          float = Field(..., ge=0.0)
    dsra_months:                     float = Field(..., ge=0.0)
    certification_confidence_pct:    float = Field(..., ge=0.0, le=100.0)


class ProjectRatingCreateRequest(BaseModel):
    project:            ProjectInputsIn
    gates:              GateStatusIn
    quantitative:       QuantitativeInputsIn
    peer_scores_desc:   Optional[List[float]] = None
    methodology_name:   str = "GEX Project Quality Rating"
    methodology_version: str = "v1.0"
    reviewer_type:      str = "internal"
    review_state:       str = "draft_screening"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def score_project_rating(payload: ProjectRatingCreateRequest):
    """
    Compute a GEX Project Quality Rating.
    Stateless: result is returned but not persisted (SQLite persistence planned).
    """
    try:
        project = ProjectInputs(
            project_name=payload.project.project_name,
            phase=payload.project.phase,
            business_market=payload.project.business_market,
            construction_technology=payload.project.construction_technology,
            financial_resilience=3.0,   # overwritten by quantitative scoring
            legal_structural_counterparty=payload.project.legal_structural_counterparty,
            sustainability_certification=payload.project.sustainability_certification,
            jurisdiction_notch=payload.project.jurisdiction_notch,
            sponsor_support_notch=payload.project.sponsor_support_notch,
            structure_notch=payload.project.structure_notch,
            market_exposure_notch=payload.project.market_exposure_notch,
            data_confidence_notch=payload.project.data_confidence_notch,
            payment_default=payload.project.payment_default,
            distressed_exchange=payload.project.distressed_exchange,
            outlook_bias=payload.project.outlook_bias,
        )
        gates = GateStatus(
            land_and_permits_ok=payload.gates.land_and_permits_ok,
            technology_wrap_ok=payload.gates.technology_wrap_ok,
            regulatory_path_ok=payload.gates.regulatory_path_ok,
            funding_path_ok=payload.gates.funding_path_ok,
            revenue_path_ok=payload.gates.revenue_path_ok,
            traceability_ok=payload.gates.traceability_ok,
        )
        quantitative = QuantitativeInputs(
            downside_min_dscr=payload.quantitative.downside_min_dscr,
            base_case_dscr=payload.quantitative.base_case_dscr,
            llcr=payload.quantitative.llcr,
            contracted_revenue_pct=payload.quantitative.contracted_revenue_pct,
            merchant_exposure_pct=payload.quantitative.merchant_exposure_pct,
            equity_committed_pct_of_capex=payload.quantitative.equity_committed_pct_of_capex,
            subsidy_dependence_pct_of_ebitda=payload.quantitative.subsidy_dependence_pct_of_ebitda,
            schedule_buffer_months=payload.quantitative.schedule_buffer_months,
            dsra_months=payload.quantitative.dsra_months,
            certification_confidence_pct=payload.quantitative.certification_confidence_pct,
        )

        result = calculate_project_rating(
            project=project,
            gates=gates,
            quantitative=quantitative,
            methodology_name=payload.methodology_name,
            methodology_version=payload.methodology_version,
            reviewer_type=payload.reviewer_type,
            review_state=payload.review_state,
            peer_scores_desc=payload.peer_scores_desc,
        )

        # Attach project_id echo if provided
        if payload.project.project_id:
            result["project_id"] = payload.project.project_id

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/current")
async def get_current_rating(project_id: str):
    """Fetch current rating for a project. Requires SQLite persistence (not yet wired)."""
    raise HTTPException(
        status_code=501,
        detail="Persistent storage for ratings not yet wired. Use POST to compute.",
    )


@router.get("/projects/{project_id}/history")
async def get_rating_history(project_id: str):
    """Fetch rating history for a project. Requires SQLite persistence (not yet wired)."""
    raise HTTPException(
        status_code=501,
        detail="Persistent storage for ratings not yet wired. Use POST to compute.",
    )


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "project-ratings", "mode": "stateless"}
