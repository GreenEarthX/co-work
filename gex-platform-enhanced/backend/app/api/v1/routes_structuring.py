"""
GEX Deal Structuring Workbench — API Routes
File: app/api/v1/routes_structuring.py

Prefix: /api/v1/structuring

Gap analysis, instrument matching, package assembly, risk allocation, timeline
and the full recommendation.

Since 2026-11-17 (handoff v4, tasks 1-4):
  · the state is the gate engine's, from the one readiness authority, with its
    freshness stamp (`readiness`); no response carries a projected state;
  · gaps follow the requirements they concern (G1, G2, G4, G5, G7), and metric
    gaps are decision tests attributed to their policy source;
  · a package's after-figures are ESTIMATES with the method shown, and the next
    state is a conditional outcome, "conditional — not achieved".
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/structuring", tags=["structuring"])


class PackageRequest(BaseModel):
    """The state is the gate engine's and cannot be supplied. WACC and DSCR
    default to the project's recorded inputs, never to a fixed figure."""
    project_id: str
    selected_instrument_ids: list[str]
    current_wacc: Optional[float] = None
    current_dscr: Optional[float] = None


async def _context(project_id: str) -> dict:
    from app.api.v1.routes_bankability_proxy import engine_rules
    from app.core.structuring_context import ContextUnavailable, load_context

    try:
        ctx = await load_context(project_id)
    except ContextUnavailable as exc:
        raise HTTPException(status_code=exc.status, detail={
            "code": exc.code, "message": exc.message, "missing": exc.missing})
    try:
        ctx["rules"] = await engine_rules()
    except HTTPException:
        ctx["rules"] = None
    return ctx


def _policies() -> dict:
    from app.core.decision_policy import DECISION_TESTS, resolve
    return {spec["policy_key"]: resolve(spec["policy_key"]) for spec in DECISION_TESTS.values()}


def _identity(ctx: dict) -> dict:
    from app.core.structuring_context import public
    out = public(ctx)
    out.pop("rules", None)
    return {"context_sources": out["sources"], "readiness": out["readiness"]}


def _gap_view(gaps) -> list[dict]:
    """Per gate: its determination and every requirement still open."""
    by_gate: dict[str, dict] = {}
    for g in gaps:
        if g.gate_id and g.gate_id not in by_gate:
            by_gate[g.gate_id] = {"gate_id": g.gate_id, "gate_name": g.gate_name,
                                  "remaining_requirements": g.gate_remaining_requirements,
                                  "complete": False}
    return list(by_gate.values())


@router.get("/{project_id}/gaps")
async def analyze_gaps(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    ctx = await _context(project_id)
    gaps = get_structuring_engine().analyze_gaps(project_id, ctx, _policies())
    return {"project_id": project_id, **_identity(ctx), "gap_count": len(gaps),
            "blocking": sum(1 for g in gaps if g.severity == "BLOCKING"),
            "not_judged": sum(1 for g in gaps if g.severity == "NOT_JUDGED"),
            "gates": _gap_view(gaps),
            "gaps": [vars(g) for g in gaps]}


@router.get("/{project_id}/instruments")
async def match_instruments(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = await _context(project_id)
    gaps = engine.analyze_gaps(project_id, ctx, _policies())
    matches = engine.match_instruments(project_id, gaps, ctx["jurisdiction"], ctx["molecule"],
                                       ctx["stage"], ctx["project_size_eur"])
    return {"project_id": project_id, **_identity(ctx), "match_count": len(matches),
            "estimate_note": "estimated_dscr_impact is a linear ESTIMATE (0.0008x per bp), not a PF-engine result.",
            "matches": [vars(m) for m in matches]}


@router.post("/{project_id}/package")
async def assemble_package(project_id: str, req: PackageRequest):
    from app.core.structuring_engine import get_structuring_engine
    engine = get_structuring_engine()
    ctx = await _context(project_id)
    gaps = engine.analyze_gaps(project_id, ctx, _policies())
    package = engine.assemble_package(
        project_id, req.selected_instrument_ids,
        req.current_wacc if req.current_wacc is not None else ctx["wacc"],
        req.current_dscr if req.current_dscr is not None else ctx["dscr_p50"],
        ctx, gaps)
    return {**vars(package), **_identity(ctx)}


@router.get("/{project_id}/risk-allocation")
async def risk_allocation(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    ctx = await _context(project_id)
    rec = get_structuring_engine().recommend(project_id, ctx, _policies())
    return {
        "project_id": project_id, **_identity(ctx),
        "total_mitigated": rec.risk_allocation.total_mitigated_risks,
        "total_residual_bps": rec.risk_allocation.total_residual_bps,
        "unmitigated_blocking": rec.risk_allocation.unmitigated_blocking_risks,
        "entries": [vars(e) for e in rec.risk_allocation.entries],
    }


@router.get("/{project_id}/recommend")
async def full_recommendation(project_id: str):
    from app.core.structuring_engine import get_structuring_engine
    ctx = await _context(project_id)
    rec = get_structuring_engine().recommend(project_id, ctx, _policies())
    return {
        "project_id": project_id, **_identity(ctx),
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
