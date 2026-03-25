# ════════════════════════════════════════════════════════════
# routes_demand.py — Demand Aggregation API
# Prefix: /api/v1/demand
# ════════════════════════════════════════════════════════════

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

demand_router = APIRouter(prefix="/api/v1/demand", tags=["demand"])


class DemandSignalRequest(BaseModel):
    project_id: str
    buyer_company_id: str
    buyer_name: str
    molecule: str
    volume_tonnes_year: int
    max_price_eur_unit: float
    min_tenor_years: int
    credit_rating: str
    delivery_location: str
    status: str = "EOI"
    source: str = "DIRECT"


@demand_router.get("/pipeline/{project_id}")
async def get_pipeline(project_id: str):
    from app.core.demand_aggregation import get_demand_aggregation
    svc = get_demand_aggregation()
    signals = svc.get_pipeline(project_id)
    return {"project_id": project_id, "signal_count": len(signals),
            "signals": [vars(s) for s in signals]}


@demand_router.get("/coverage/{project_id}")
async def get_coverage(project_id: str, total_production: int = Query(30000)):
    from app.core.demand_aggregation import get_demand_aggregation
    svc = get_demand_aggregation()
    metrics = svc.compute_coverage(project_id, total_production)
    return vars(metrics)


@demand_router.get("/aggregation/{project_id}")
async def suggest_aggregation(project_id: str, total_production: int = Query(30000)):
    from app.core.demand_aggregation import get_demand_aggregation
    svc = get_demand_aggregation()
    plan = svc.suggest_aggregation(project_id, total_production)
    return {
        "project_id": project_id,
        "meets_threshold": plan.meets_threshold,
        "total_coverage_pct": plan.total_aggregated_coverage_pct,
        "recommendation": plan.recommendation,
        "suggestions": [vars(s) for s in plan.suggestions],
    }


@demand_router.post("/signal")
async def add_signal(req: DemandSignalRequest):
    from app.core.demand_aggregation import get_demand_aggregation, DemandSignal
    from datetime import datetime, timezone
    import uuid
    svc = get_demand_aggregation()
    signal = DemandSignal(
        signal_id=str(uuid.uuid4())[:8],
        project_id=req.project_id,
        buyer_company_id=req.buyer_company_id,
        buyer_name=req.buyer_name,
        molecule=req.molecule,
        volume_tonnes_year=req.volume_tonnes_year,
        max_price_eur_unit=req.max_price_eur_unit,
        min_tenor_years=req.min_tenor_years,
        credit_rating=req.credit_rating,
        delivery_location=req.delivery_location,
        status=req.status,
        source=req.source,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    svc.add_signal(signal)
    return {"signal_id": signal.signal_id, "status": "added"}
