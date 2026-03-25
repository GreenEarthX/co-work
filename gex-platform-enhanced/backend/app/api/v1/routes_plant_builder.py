"""
GEX Plant Builder API Routes
/api/v1/plant-builder

Endpoints:
  GET  /catalog                — browse equipment catalog
  GET  /catalog/{id}           — equipment detail
  POST /configure              — submit plant config → CAPEX/OPEX/cert result
  POST /levelised-cost         — quick LCOH/LCOSAF from configuration
  POST /cert-distance          — certification gap analysis
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.core.plant_builder import (
    get_plant_builder,
    PlantConfiguration,
    EQUIPMENT_CATALOG,
)

logger = logging.getLogger("gex.routes.plant_builder")
router = APIRouter()


# ════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ════════════════════════════════════════════════════════════════

class EquipmentLineRequest(BaseModel):
    equipment_id: str
    quantity: int = Field(default=1, ge=1, le=100)


class PlantConfigRequest(BaseModel):
    project_id: str = "GEX-PROJECT-001"
    molecule: str = "H2"
    location_jurisdiction: str = "FR"
    equipment: list[EquipmentLineRequest]
    power_price_eur_mwh: float = Field(default=45.0, ge=0, le=500)
    water_price_eur_m3: float = Field(default=2.50, ge=0, le=50)
    labour_count: int = Field(default=45, ge=1, le=2000)
    labour_cost_eur_year: float = Field(default=65_000, ge=10_000, le=500_000)
    insurance_pct_capex: float = Field(default=0.005, ge=0, le=0.05)
    contingency_pct: float = Field(default=0.10, ge=0, le=0.50)
    target_market_price_eur_t: float = Field(default=5000.0, ge=0)
    wacc_pct: float = Field(default=0.09, ge=0.01, le=0.30)
    project_life_years: int = Field(default=20, ge=5, le=50)


class LevelisedCostRequest(BaseModel):
    """Lightweight request for quick LCOH/LCOSAF estimate."""
    molecule: str = "H2"
    location_jurisdiction: str = "FR"
    equipment: list[EquipmentLineRequest]
    power_price_eur_mwh: float = 45.0
    water_price_eur_m3: float = 2.50
    labour_count: int = 45
    labour_cost_eur_year: float = 65_000
    contingency_pct: float = 0.10
    wacc_pct: float = 0.09
    project_life_years: int = 20


class CertDistanceRequest(BaseModel):
    molecule: str = "H2"
    location_jurisdiction: str = "FR"
    equipment: list[EquipmentLineRequest]


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _equipment_to_dict(req_list: list[EquipmentLineRequest]) -> list[dict]:
    return [{"equipment_id": e.equipment_id, "quantity": e.quantity} for e in req_list]


def _serialize_item(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "unit_price_eur": item.unit_price_eur,
        "installation_multiplier": item.installation_multiplier,
        "annual_om_pct": item.annual_om_pct,
        "annual_power_mwh": item.annual_power_mwh,
        "annual_water_m3": item.annual_water_m3,
        "useful_life_years": item.useful_life_years,
        "residual_value_pct": item.residual_value_pct,
        "capex_layer": item.capex_layer,
        "molecule_output": item.molecule_output,
        "capacity_tonnes_year": item.capacity_tonnes_year,
        "cert_enables": item.cert_enables,
        "cert_blocks": item.cert_blocks,
        "cert_requirements": item.cert_requirements,
        "technology_maturity": item.technology_maturity,
        "oem": item.oem,
        "description": item.description,
        # Computed convenience
        "installed_cost_eur": int(item.unit_price_eur * item.installation_multiplier),
        "annual_om_eur": int(item.unit_price_eur * item.installation_multiplier * item.annual_om_pct),
    }


def _serialize_result(result) -> dict:
    return {
        "capex": {
            "total_equipment_eur": result.total_equipment_eur,
            "total_installed_eur": result.total_installed_eur,
            "contingency_eur": result.contingency_eur,
            "total_capex_eur": result.total_capex_eur,
            "per_layer": result.capex_per_layer,
            "by_category": result.capex_by_category,
        },
        "opex": {
            "annual_om_eur": result.annual_om_eur,
            "annual_power_eur": result.annual_power_eur,
            "annual_water_eur": result.annual_water_eur,
            "annual_labour_eur": result.annual_labour_eur,
            "annual_insurance_eur": result.annual_insurance_eur,
            "total_annual_opex_eur": result.total_annual_opex_eur,
        },
        "output": {
            "annual_output_tonnes": result.annual_output_tonnes,
            "annualised_capex_eur": result.annualised_capex_eur,
            "levelised_cost_eur_t": result.levelised_cost_eur_t,
            "market_price_eur_t": result.market_price_eur_t,
            "competitive_gap_eur_t": result.competitive_gap_eur_t,
            "subsidy_needed_eur_t": result.subsidy_needed_eur_t,
            "subsidy_needed_total_eur_yr": result.subsidy_needed_total_eur_yr,
        },
        "certification": {
            "readiness": result.cert_readiness,
            "blockers": result.cert_blockers,
            "premium_eur_t": result.cert_premium_eur_t,
            "effective_price_with_certs": result.effective_price_with_certs,
        },
        "equipment_lines": result.equipment_lines,
    }


# ════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════

@router.get("/catalog")
async def get_catalog(
    molecule: Optional[str] = Query(default=None, description="Filter by molecule output: H2, SAF, NH3, E_METHANOL"),
    category: Optional[str] = Query(default=None, description="Filter by category: ELECTROLYSER, REACTOR, BOP, STORAGE, INFRASTRUCTURE, UTILITIES, CONTROLS, SAFETY"),
):
    """Browse equipment catalog. Filter by molecule output or equipment category."""
    builder = get_plant_builder()
    items = builder.get_catalog(molecule=molecule, category=category)

    # Group by category for structured response
    categories: dict = {}
    for item in items:
        cat = item.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(_serialize_item(item))

    return {
        "total": len(items),
        "filters": {"molecule": molecule, "category": category},
        "by_category": categories,
        "items": [_serialize_item(i) for i in items],
    }


@router.get("/catalog/categories")
async def list_categories():
    """List all equipment categories with item counts."""
    builder = get_plant_builder()
    all_items = builder.get_catalog()
    counts: dict = {}
    for item in all_items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return {
        "categories": [{"category": k, "count": v} for k, v in sorted(counts.items())]
    }


@router.get("/catalog/{item_id}")
async def get_catalog_item(item_id: str):
    """Get full detail for a specific equipment item."""
    builder = get_plant_builder()
    item = builder.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Equipment '{item_id}' not found in catalog")
    return _serialize_item(item)


@router.post("/configure")
async def configure_plant(req: PlantConfigRequest):
    """
    Submit a plant configuration and receive full CAPEX/OPEX/levelised cost/cert result.

    Reference: Breizh SAF Complex — GEX-BRZ-SAF-001, €285M CAPEX.
    """
    builder = get_plant_builder()

    config = PlantConfiguration(
        project_id=req.project_id,
        molecule=req.molecule,
        location_jurisdiction=req.location_jurisdiction,
        equipment=_equipment_to_dict(req.equipment),
        power_price_eur_mwh=req.power_price_eur_mwh,
        water_price_eur_m3=req.water_price_eur_m3,
        labour_count=req.labour_count,
        labour_cost_eur_year=req.labour_cost_eur_year,
        insurance_pct_capex=req.insurance_pct_capex,
        contingency_pct=req.contingency_pct,
        target_market_price_eur_t=req.target_market_price_eur_t,
        wacc_pct=req.wacc_pct,
        project_life_years=req.project_life_years,
    )

    result = builder.build(config)
    serialized = _serialize_result(result)

    return {
        "project_id": req.project_id,
        "molecule": req.molecule,
        "jurisdiction": req.location_jurisdiction,
        **serialized,
    }


@router.post("/levelised-cost")
async def quick_levelised_cost(req: LevelisedCostRequest):
    """
    Quick LCOH/LCOSAF/LCOA calculation from a plant configuration.
    Returns levelised cost, competitive gap, and subsidy needed without full cert analysis.
    """
    builder = get_plant_builder()

    # Default market reference prices per molecule
    default_market_prices = {
        "H2": 5_000,        # €5/kg = €5,000/t
        "NH3": 700,         # €700/t
        "SAF": 1_500,       # €1,500/t
        "E_METHANOL": 800,  # €800/t
        "E_NG": 1_200,
    }
    market_price = default_market_prices.get(req.molecule, 1_000)

    config = PlantConfiguration(
        project_id="quick-lcoe",
        molecule=req.molecule,
        location_jurisdiction=req.location_jurisdiction,
        equipment=_equipment_to_dict(req.equipment),
        power_price_eur_mwh=req.power_price_eur_mwh,
        water_price_eur_m3=req.water_price_eur_m3,
        labour_count=req.labour_count,
        labour_cost_eur_year=req.labour_cost_eur_year,
        insurance_pct_capex=0.005,
        contingency_pct=req.contingency_pct,
        target_market_price_eur_t=market_price,
        wacc_pct=req.wacc_pct,
        project_life_years=req.project_life_years,
    )

    result = builder.build(config)

    return {
        "molecule": req.molecule,
        "jurisdiction": req.location_jurisdiction,
        "levelised_cost_eur_t": result.levelised_cost_eur_t,
        "market_reference_eur_t": market_price,
        "competitive_gap_eur_t": result.competitive_gap_eur_t,
        "subsidy_needed_eur_t": result.subsidy_needed_eur_t,
        "subsidy_needed_total_eur_yr": result.subsidy_needed_total_eur_yr,
        "annual_output_tonnes": result.annual_output_tonnes,
        "total_capex_eur": result.total_capex_eur,
        "total_annual_opex_eur": result.total_annual_opex_eur,
        "annualised_capex_eur": result.annualised_capex_eur,
        "capex_breakdown": {
            "equipment": result.total_equipment_eur,
            "installation": result.total_installed_eur - result.total_equipment_eur,
            "contingency": result.contingency_eur,
            "total": result.total_capex_eur,
        },
        "opex_breakdown": {
            "om": result.annual_om_eur,
            "power": result.annual_power_eur,
            "water": result.annual_water_eur,
            "labour": result.annual_labour_eur,
            "insurance": result.annual_insurance_eur,
            "total": result.total_annual_opex_eur,
        },
    }


@router.post("/cert-distance")
async def certification_gap_analysis(req: CertDistanceRequest):
    """
    Certification distance analysis for a configured plant.
    Returns per-regime readiness score, blockers, and premium uplift achievable.
    """
    builder = get_plant_builder()

    config = PlantConfiguration(
        project_id="cert-analysis",
        molecule=req.molecule,
        location_jurisdiction=req.location_jurisdiction,
        equipment=_equipment_to_dict(req.equipment),
        power_price_eur_mwh=45.0,
        water_price_eur_m3=2.5,
        labour_count=1,
        labour_cost_eur_year=65_000,
        insurance_pct_capex=0.005,
        contingency_pct=0.10,
        target_market_price_eur_t=1_000,
    )

    result = builder.build(config)
    cert = result.cert_readiness
    premiums = result.cert_premium_eur_t
    blockers = result.cert_blockers

    # Per-regime gap report
    regimes = []
    for regime, score in cert.items():
        gap_items = []
        if score < 100:
            gap_items.append(f"Score {score}/100 — add equipment that enables missing criteria")
        blocker_msgs = [b for b in blockers if regime in b]
        regimes.append({
            "regime": regime,
            "readiness_pct": score,
            "status": "READY" if score >= 80 else ("PARTIAL" if score >= 40 else "BLOCKED"),
            "premium_eur_t": premiums.get(regime, 0),
            "blockers": blocker_msgs,
            "gaps": gap_items,
            "is_achievable": score >= 80,
        })

    total_achievable_premium = sum(premiums.values())

    return {
        "molecule": req.molecule,
        "jurisdiction": req.location_jurisdiction,
        "regimes": regimes,
        "total_achievable_premium_eur_t": total_achievable_premium,
        "blockers": blockers,
        "recommendation": (
            "Add ENERGY_MANAGEMENT and CERT_AUDIT_SYSTEM for RFNBO temporal correlation"
            if cert.get("RFNBO", 0) < 80 else
            "Plant configuration is RFNBO-ready"
        ),
    }


@router.get("/breizh-reference")
async def get_breizh_reference():
    """
    Return the Breizh SAF Complex reference configuration (GEX-BRZ-SAF-001).
    €285M CAPEX — Lorient, France.
    """
    return {
        "project_id": "GEX-BRZ-SAF-001",
        "name": "Breizh SAF Complex",
        "location": "Lorient, France",
        "molecule": "SAF",
        "jurisdiction": "FR",
        "target_capex_eur": 285_000_000,
        "target_capacity_kt_yr": 50,
        "reference_configuration": [
            {"equipment_id": "PEM_ELEC_120MW", "quantity": 2},
            {"equipment_id": "WATER_TREATMENT_2000M3", "quantity": 1},
            {"equipment_id": "CO2_CAPTURE_50KT", "quantity": 2},
            {"equipment_id": "FT_REACTOR_50KT", "quantity": 1},
            {"equipment_id": "FT_UPGRADING", "quantity": 1},
            {"equipment_id": "SAF_STORAGE_5KT", "quantity": 3},
            {"equipment_id": "GRID_CONN_300MW", "quantity": 1},
            {"equipment_id": "POWER_ELECTRONICS", "quantity": 2},
            {"equipment_id": "BESS_20MWH", "quantity": 2},
            {"equipment_id": "DCS_SCADA_MAIN", "quantity": 1},
            {"equipment_id": "METERING_CERTIFIED", "quantity": 1},
            {"equipment_id": "ENERGY_MANAGEMENT", "quantity": 1},
            {"equipment_id": "CERT_AUDIT_SYSTEM", "quantity": 1},
            {"equipment_id": "SITE_PREP", "quantity": 1},
            {"equipment_id": "BUILDINGS_CONTROL", "quantity": 1},
            {"equipment_id": "FIRE_PROTECTION", "quantity": 1},
            {"equipment_id": "FLARING_SYSTEM", "quantity": 1},
            {"equipment_id": "COOLING_TOWER", "quantity": 2},
        ],
        "operating_parameters": {
            "power_price_eur_mwh": 42.0,
            "water_price_eur_m3": 2.20,
            "labour_count": 52,
            "labour_cost_eur_year": 68_000,
            "insurance_pct_capex": 0.005,
            "contingency_pct": 0.12,
            "target_market_price_eur_t": 1_500,
            "wacc_pct": 0.085,
            "project_life_years": 25,
        },
    }
