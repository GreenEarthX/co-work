# ════════════════════════════════════════════════════════════
# routes_risk_pricing.py — Risk Pricing Database API
# Prefix: /api/v1/risk-pricing
# ════════════════════════════════════════════════════════════

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

risk_pricing_router = APIRouter(prefix="/api/v1/risk-pricing", tags=["risk-pricing"])


@risk_pricing_router.get("/spread")
async def get_spread(
    component_type: str = Query(...),
    maturity: str = Query("PROVEN"),
    jurisdiction: str = Query("FR"),
):
    from app.core.risk_pricing import get_risk_pricing_db
    db = get_risk_pricing_db()
    spread = db.get_spread(component_type, maturity, jurisdiction)
    rfr = db.get_risk_free_rate(jurisdiction)
    reg_premium = db.get_regulatory_risk_premium(jurisdiction)
    if spread is None:
        raise HTTPException(404, f"No pricing data for {component_type}/{maturity}/{jurisdiction}")
    return {
        "component_type": component_type,
        "maturity": maturity,
        "jurisdiction": jurisdiction,
        "risk_free_rate_pct": round(rfr * 100, 2),
        "spread_bps": spread,
        "all_in_cost_pct": round((rfr + spread / 10000) * 100, 2),
        "regulatory_premium_bps": reg_premium,
    }


class CapexLayer(BaseModel):
    name: str
    amount: float
    component_type: str
    maturity: str
    debt_ratio: float
    etv_premium_pct: float = 0.0


@risk_pricing_router.post("/layer-wacc")
async def compute_layer_wacc(
    body: list[CapexLayer],
    jurisdiction: str = Query("FR"),
    traditional_wacc: float = Query(0.090),
):
    """Layer-blended WACC for the capex layers GIVEN. It used to price five
    invented "Breizh SAF" layers for every caller (removed 2026-10-25)."""
    from app.core.risk_pricing import get_risk_pricing_db, ComponentType
    if not body:
        raise HTTPException(status_code=422, detail="Give the project's capex layers.")
    db = get_risk_pricing_db()
    try:
        layers = [{**l.model_dump(), "component_type": ComponentType(l.component_type)} for l in body]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = db.compute_layer_wacc(jurisdiction, layers, traditional_wacc)
    return {
        "jurisdiction": jurisdiction,
        "blended_wacc_pct": result.blended_wacc_pct,
        "traditional_flat_wacc_pct": result.traditional_flat_wacc_pct,
        "wacc_saving_bps": result.wacc_saving_bps,
        "total_etv_premium_pct": result.total_etv_premium_pct,
        "layers": result.layers,
    }