# ════════════════════════════════════════════════════════════
# routes_instruments.py — Instrument Registry API
# Prefix: /api/v1/instruments
# ════════════════════════════════════════════════════════════

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

instruments_router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


@instruments_router.get("/")
async def list_instruments(
    jurisdiction: Optional[str] = None,
    molecule: Optional[str] = None,
    instrument_type: Optional[str] = None,
):
    from app.core.instrument_registry import get_instrument_registry, InstrumentType
    registry = get_instrument_registry()
    types = [InstrumentType(instrument_type)] if instrument_type else None
    results = registry.search(
        jurisdiction=jurisdiction, molecule=molecule,
        instrument_types=types,
    )
    return {"count": len(results), "instruments": [vars(i) for i in results]}


@instruments_router.get("/eligible/{project_id}")
async def eligible_instruments(project_id: str):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    ctx = _get_demo_context(project_id)
    results = registry.get_eligible_for_project(
        ctx["jurisdiction"], ctx["molecule"], ctx["stage"], ctx["project_size_eur"],
    )
    return {"project_id": project_id, "eligible_count": len(results),
            "instruments": [{"id": i.id, "name": i.name, "type": i.type.value,
                            "provider": i.provider, "rate_reduction_bps": i.effective_rate_reduction_bps,
                            "cost_bps": i.cost_bps, "coverage": i.max_coverage_pct,
                            "risks_addressed": [r.value for r in i.risks_addressed]}
                           for i in results]}


@instruments_router.post("/stack-check")
async def stack_check(instrument_ids: list[str]):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    result = registry.check_stackability(instrument_ids)
    return vars(result)


@instruments_router.get("/{instrument_id}")
async def get_instrument(instrument_id: str):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    inst = registry.get(instrument_id)
    if not inst:
        raise HTTPException(404, f"Instrument not found: {instrument_id}")
    return vars(inst)