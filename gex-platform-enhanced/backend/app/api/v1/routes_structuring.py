"""
GEX Deal Structuring Workbench — API Routes
File: app/api/v1/routes_structuring.py

Prefix: /api/v1/structuring

The primary API surface for the Deal Structuring Workbench.
Covers: gap analysis, instrument matching, package assembly,
risk allocation, timeline sequencing, and full recommendation.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/api/v1/structuring", tags=["structuring"])


class ProjectContext(BaseModel):
    project_id: str
    jurisdiction: str = "FR"
    molecule: str = "SAF"
    stage: str = "BUILDABLE"
    project_size_eur: int = 285_000_000
    gate_scores: dict = Field(default_factory=lambda: {
        "G0": 95, "G1": 88, "G2": 72, "G3": 90, "G4": 78,
        "G5": 45, "G6": 0, "G7": 55, "G8": 68, "G9": 92,
        "G10": 0, "G11": 0,
    })
    dscr_p50: float = 1.34
    dscr_p90: float = 1.18
    llcr: float = 1.41
    wacc: float = 0.089
    offtake_coverage_pct: float = 0.55
    cert_readiness: int = 88
    epc_status: str = "SHORTLISTING"
    insurance_status: str = "QUOTED"
    grid_status: str = "FIRM_OFFER"


class PackageRequest(BaseModel):
    project_id: str
    selected_instrument_ids: list[str]
    current_wacc: float = 0.089
    current_dscr: float = 1.34
    current_state: str = "BUILDABLE"


@router.get("/{project_id}/gaps")
async def analyze_gaps(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = _get_demo_context(project_id)
    gaps = engine.analyze_gaps(
        project_id=project_id,
        gate_scores=ctx["gate_scores"],
        bankability_state=ctx["stage"],
        dscr_p50=ctx["dscr_p50"], dscr_p90=ctx["dscr_p90"],
        llcr=ctx["llcr"], wacc=ctx["wacc"],
        offtake_coverage_pct=ctx["offtake_coverage_pct"],
        cert_readiness=ctx["cert_readiness"],
        epc_status=ctx["epc_status"],
        insurance_status=ctx["insurance_status"],
        grid_status=ctx["grid_status"],
        jurisdiction=ctx["jurisdiction"],
    )
    return {"project_id": project_id, "gap_count": len(gaps),
            "blocking": sum(1 for g in gaps if g.severity == "BLOCKING"),
            "gaps": [vars(g) for g in gaps]}


@router.get("/{project_id}/instruments")
async def match_instruments(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = _get_demo_context(project_id)
    gaps = engine.analyze_gaps(
        project_id, ctx["gate_scores"], ctx["stage"],
        ctx["dscr_p50"], ctx["dscr_p90"], ctx["llcr"], ctx["wacc"],
        ctx["offtake_coverage_pct"], ctx["cert_readiness"],
        ctx["epc_status"], ctx["insurance_status"], ctx["grid_status"],
        ctx["jurisdiction"],
    )
    matches = engine.match_instruments(
        project_id, gaps, ctx["jurisdiction"], ctx["molecule"],
        ctx["stage"], ctx["project_size_eur"],
    )
    return {"project_id": project_id, "match_count": len(matches),
            "matches": [vars(m) for m in matches]}


@router.post("/{project_id}/package")
async def assemble_package(project_id: str, req: PackageRequest):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = _get_demo_context(project_id)
    gaps = engine.analyze_gaps(
        project_id, ctx["gate_scores"], ctx["stage"],
        ctx["dscr_p50"], ctx["dscr_p90"], ctx["llcr"], ctx["wacc"],
        ctx["offtake_coverage_pct"], ctx["cert_readiness"],
        ctx["epc_status"], ctx["insurance_status"], ctx["grid_status"],
        ctx["jurisdiction"],
    )
    package = engine.assemble_package(
        project_id, req.selected_instrument_ids,
        req.current_wacc, req.current_dscr, req.current_state, gaps,
    )
    return vars(package)


@router.get("/{project_id}/risk-allocation")
async def risk_allocation(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = _get_demo_context(project_id)
    gaps = engine.analyze_gaps(
        project_id, ctx["gate_scores"], ctx["stage"],
        ctx["dscr_p50"], ctx["dscr_p90"], ctx["llcr"], ctx["wacc"],
        ctx["offtake_coverage_pct"], ctx["cert_readiness"],
        ctx["epc_status"], ctx["insurance_status"], ctx["grid_status"],
        ctx["jurisdiction"],
    )
    rec = engine.recommend(
        project_id, ctx["jurisdiction"], ctx["molecule"], ctx["stage"],
        ctx["project_size_eur"], ctx["gate_scores"],
        ctx["dscr_p50"], ctx["dscr_p90"], ctx["llcr"], ctx["wacc"],
        ctx["offtake_coverage_pct"], ctx["cert_readiness"],
        ctx["epc_status"], ctx["insurance_status"], ctx["grid_status"],
    )
    entries = [vars(e) for e in rec.risk_allocation.entries]
    return {
        "project_id": project_id,
        "total_mitigated": rec.risk_allocation.total_mitigated_risks,
        "total_residual_bps": rec.risk_allocation.total_residual_bps,
        "unmitigated_blocking": rec.risk_allocation.unmitigated_blocking_risks,
        "entries": entries,
    }


@router.get("/{project_id}/recommend")
async def full_recommendation(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = _get_demo_context(project_id)
    rec = engine.recommend(
        project_id, ctx["jurisdiction"], ctx["molecule"], ctx["stage"],
        ctx["project_size_eur"], ctx["gate_scores"],
        ctx["dscr_p50"], ctx["dscr_p90"], ctx["llcr"], ctx["wacc"],
        ctx["offtake_coverage_pct"], ctx["cert_readiness"],
        ctx["epc_status"], ctx["insurance_status"], ctx["grid_status"],
    )
    return {
        "project_id": project_id,
        "summary": rec.summary,
        "gap_count": len(rec.gaps),
        "instrument_count": len(rec.package.items),
        "before_metrics": rec.before_metrics,
        "after_metrics": rec.after_metrics,
        "package": vars(rec.package),
        "risk_allocation_summary": {
            "mitigated": rec.risk_allocation.total_mitigated_risks,
            "residual_bps": rec.risk_allocation.total_residual_bps,
            "unmitigated_blocking": rec.risk_allocation.unmitigated_blocking_risks,
        },
        "timeline_items": len(rec.timeline),
        "workflow_state": rec.workflow_state,
    }


# ── Demo context (replace with DB queries in production) ──

# The structuring context of a project lives in PostgreSQL (project_dataset,
# kind structuring_context, alembic 069). DEMO_CONTEXTS and its default — a
# project that does not exist ("Breizh SAF") answering for every other one —
# were removed on 2026-10-25.

def _get_demo_context(project_id: str) -> dict:
    from app.core.projects_store import fetch_dataset

    record = fetch_dataset(project_id, "structuring_context")
    if record is None:
        raise HTTPException(status_code=404, detail={
            "code": "STRUCTURING_CONTEXT_NOT_RECORDED",
            "message": "No structuring context is recorded for this project, so no gaps or options are computed."})
    return record["payload"]