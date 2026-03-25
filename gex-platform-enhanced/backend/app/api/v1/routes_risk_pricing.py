# ════════════════════════════════════════════════════════════
# routes_risk_pricing.py — Risk Pricing Database API
# Prefix: /api/v1/risk-pricing
# ════════════════════════════════════════════════════════════

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


@risk_pricing_router.post("/layer-wacc")
async def compute_layer_wacc(
    jurisdiction: str = Query("FR"),
    traditional_wacc: float = Query(0.090),
):
    from app.core.risk_pricing import get_risk_pricing_db, ComponentType
    db = get_risk_pricing_db()
    # Breizh SAF default layers
    layers = [
        {"name": "L1: Site & Entitlements", "amount": 42_000_000,
         "component_type": ComponentType.SITE_ENTITLEMENTS, "maturity": "PROVEN", "debt_ratio": 0.25, "etv_premium_pct": 0.0},
        {"name": "L2: Electrolyser + BoP", "amount": 103_000_000,
         "component_type": ComponentType.PEM_ELECTROLYSER, "maturity": "FIRST_OF_KIND", "debt_ratio": 0.60, "etv_premium_pct": 0.042},
        {"name": "L3: Fischer-Tropsch", "amount": 82_000_000,
         "component_type": ComponentType.FT_REACTOR, "maturity": "FIRST_OF_KIND", "debt_ratio": 0.55, "etv_premium_pct": 0.018},
        {"name": "L4: Infrastructure", "amount": 30_000_000,
         "component_type": ComponentType.PORT_INFRASTRUCTURE, "maturity": "PROVEN", "debt_ratio": 0.70, "etv_premium_pct": 0.0},
        {"name": "L5: GEX Platform", "amount": 3_500_000,
         "component_type": ComponentType.DCS_SCADA, "maturity": "PROVEN", "debt_ratio": 0.20, "etv_premium_pct": 0.12},
    ]
    result = db.compute_layer_wacc(jurisdiction, layers, traditional_wacc)
    return {
        "jurisdiction": jurisdiction,
        "blended_wacc_pct": result.blended_wacc_pct,
        "traditional_flat_wacc_pct": result.traditional_flat_wacc_pct,
        "wacc_saving_bps": result.wacc_saving_bps,
        "total_etv_premium_pct": result.total_etv_premium_pct,
        "layers": result.layers,
    }