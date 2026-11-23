"""
Project Finance API Routes
Exposes financial modeling, CFADS, waterfall, and covenant monitoring
Event-driven with full audit trail
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pf_engine.api.validation import FiniteModel
from typing import Dict, List, Literal, Optional
from datetime import date

from pf_engine.core.engine import ProjectFinanceEngine
from pf_engine.core.cfads import CFADSCalculator
from pf_engine.core.waterfall import CashFlowWaterfall
from pf_engine.core.returns import compute_returns

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ProjectMetricsRequest(FiniteModel):
    revenue: float
    opex: float
    capex: float
    debt_service: float
    period: str


class CFADSRequest(FiniteModel):
    production_mtpd: float
    offtake_price_eur_kg: float
    subsidies: Optional[Dict[str, float]] = None
    opex_eur_kg: float = 0
    maintenance_capex: float = 0
    period_days: int = 365


class CurrencyStream(FiniteModel):
    """One revenue or opex stream in its own currency, with its contract fx_rate to base."""
    label: str
    amount: float
    currency: str = "EUR"
    fx_rate: float = 1.0


class MultiCurrencyCFADSRequest(FiniteModel):
    revenue_streams: List[CurrencyStream] = []
    opex_streams: List[CurrencyStream] = []
    base_currency: str = "EUR"
    maintenance_capex: float = 0
    working_capital_change: float = 0
    tax_rate: float = 0.21


class DrawdownRequest(FiniteModel):
    milestone: str
    total_capex: float
    spent_to_date: float
    milestone_percentage: float
    senior_debt_total: float


class WaterfallRequest(FiniteModel):
    cfads: float
    senior_debt_service: float
    junior_debt_service: float = 0
    mezzanine_service: float = 0
    dsra_required: float = 0
    maintenance_reserve: float = 0


class LifetimeModelRequest(FiniteModel):
    capacity_mtpd: float
    price_eur_kg: float
    opex_eur_kg: float
    total_capex: float
    senior_debt_amount: float
    interest_rate: float
    tenor_years: int
    operations_start_year: int = 2027


class ReturnsRequest(FiniteModel):
    """Inputs to core/returns.py. FCI is the CAPEX committed at year 0; pre-FID
    spend is listed oldest year first and falls before year 0."""
    fci_eur: float
    operating_years: int
    revenue_y1_eur: float
    opex_y1_eur: float
    tax_rate: float
    depreciation_years: int
    revenue_growth: float = 0.0
    opex_growth: float = 0.0
    maintenance_capex_eur: float = 0.0
    residual_value_eur: float = 0.0
    pre_fid_spend_eur: List[float] = []
    # CAPEX by year from FID (year 0 first). Must total fci_eur and hold no pre-FID
    # spend. Empty gives the labelled screening case (FCI in full at year 0).
    construction_schedule_eur: List[float] = []
    # Months from FID to COD. Default: the end of the last construction year. Not a
    # multiple of 12 gives a pro-rated first and last operating year.
    cod_months_after_fid: Optional[int] = None
    ramp_up: List[float] = []            # output share, first operating years
    opex_variable_share: float = 0.0     # share of OPEX that scales with output
    debt_eur: float = 0.0
    interest_rate: float = 0.0
    debt_tenor_years: int = 0
    grant_eur: float = 0.0
    # Hurdle rate: state cost_of_equity, or give the three build-up terms.
    cost_of_equity: Optional[float] = None
    risk_free_rate: Optional[float] = None
    equity_beta: Optional[float] = None
    equity_risk_premium: Optional[float] = None
    country_risk_premium: float = 0.0
    technology_risk_premium: float = 0.0
    project_risk_premium: float = 0.0
    # Which case this is (handoff v4, task 8). FROM_FID excludes pre-FID spend as
    # sunk and is never a full-project return. The scenario names the case
    # (BASE, DOWNSIDE …); the engine computes, the owner publishes.
    valuation_boundary: Literal["FULL_PROJECT", "FROM_FID"] = "FULL_PROJECT"
    scenario: str = "BASE"
    # Sources the caller states: {"tea_case": {...}, "assumptions": [{name, value,
    # source, verification_status}]}. Echoed in the result's provenance.
    provenance_inputs: Optional[Dict] = None


class CovenantCheckRequest(FiniteModel):
    dscr: float
    dsra_funded: bool
    completion_guarantee: bool
    covenant_requirements: Dict


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "project-finance-engine"}


@router.post("/metrics/calculate")
async def calculate_metrics(
    request: ProjectMetricsRequest,
    project_id: str = "default",
    correlation_id: Optional[str] = None
):
    """
    Calculate project financial metrics
    Returns CFADS, DSCR, and covenant compliance
    """
    try:
        engine = ProjectFinanceEngine(project_id, correlation_id)
        
        result = engine.calculate_project_metrics(
            revenue=request.revenue,
            opex=request.opex,
            capex=request.capex,
            debt_service=request.debt_service,
            period=request.period
        )
        
        return {
            "success": True,
            "project_id": project_id,
            "correlation_id": engine.correlation_id,
            "metrics": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cfads/calculate")
async def calculate_cfads(request: CFADSRequest):
    """
    Calculate Cash Flow Available for Debt Service
    Specialized for green fuel projects with subsidy tracking
    """
    try:
        result = CFADSCalculator.calculate(
            production_volume_mtpd=request.production_mtpd,
            offtake_price_eur_kg=request.offtake_price_eur_kg,
            subsidies=request.subsidies or {},
            opex_eur_kg=request.opex_eur_kg,
            maintenance_capex=request.maintenance_capex,
            period_days=request.period_days
        )
        
        return {
            "success": True,
            "cfads": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cfads/calculate-multi-currency")
async def calculate_cfads_multi_currency(request: MultiCurrencyCFADSRequest):
    """Multi-currency CFADS — each revenue/opex stream carries its own currency and its
    (contract-specified upstream) fx_rate to the base currency. Returns per-stream FX
    detail and the natural-hedge ratio."""
    try:
        result = CFADSCalculator.calculate_multi_currency(
            revenue_streams=[s.model_dump() for s in request.revenue_streams],
            opex_streams=[s.model_dump() for s in request.opex_streams],
            base_currency=request.base_currency,
            maintenance_capex=request.maintenance_capex,
            working_capital_change=request.working_capital_change,
            tax_rate=request.tax_rate,
        )
        return {"success": True, "cfads": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drawdown/calculate")
async def calculate_drawdown(
    request: DrawdownRequest,
    project_id: str = "default",
    correlation_id: Optional[str] = None
):
    """
    Calculate debt drawdown for construction milestone
    Critical for construction-finance coupling!
    """
    try:
        engine = ProjectFinanceEngine(project_id, correlation_id)
        
        result = engine.calculate_drawdown(
            milestone=request.milestone,
            total_capex=request.total_capex,
            spent_to_date=request.spent_to_date,
            milestone_percentage=request.milestone_percentage,
            senior_debt_total=request.senior_debt_total
        )
        
        return {
            "success": True,
            "project_id": project_id,
            "correlation_id": engine.correlation_id,
            "drawdown": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/waterfall/execute")
async def execute_waterfall(request: WaterfallRequest):
    """
    Execute cash flow waterfall
    Distributes CFADS across reserves, debt tranches, and equity
    """
    try:
        result = CashFlowWaterfall.create_typical_structure(
            cfads=request.cfads,
            senior_debt_service=request.senior_debt_service,
            junior_debt_service=request.junior_debt_service,
            mezzanine_service=request.mezzanine_service,
            dsra_required=request.dsra_required,
            maintenance_reserve=request.maintenance_reserve
        )
        
        return {
            "success": True,
            "waterfall": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/lifetime")
async def model_lifetime(
    request: LifetimeModelRequest,
    project_id: str = "default",
    correlation_id: Optional[str] = None
):
    """
    Model full project lifetime cash flows
    Returns year-by-year CFADS, debt service, DSCR
    """
    try:
        engine = ProjectFinanceEngine(project_id, correlation_id)
        
        result = engine.model_project_lifetime(
            capacity_mtpd=request.capacity_mtpd,
            price_eur_kg=request.price_eur_kg,
            opex_eur_kg=request.opex_eur_kg,
            total_capex=request.total_capex,
            senior_debt_amount=request.senior_debt_amount,
            interest_rate=request.interest_rate,
            tenor_years=request.tenor_years,
            operations_start_year=request.operations_start_year
        )
        
        return {
            "success": True,
            "project_id": project_id,
            "correlation_id": engine.correlation_id,
            "lifetime_model": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/returns/calculate")
async def calculate_returns(request: ReturnsRequest, project_id: str = "default"):
    """
    Unlevered and levered IRR, NPV, payback, ROI, ROE and the hurdle rate test.
    With a construction schedule the result is the scheduled case and carries
    the screening case (FCI at year 0) beside it.
    Definitions and limitations travel with the result.
    """
    try:
        result = compute_returns(**request.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"success": True, "project_id": project_id, "returns": result}


@router.post("/covenants/check")
async def check_covenants(
    request: CovenantCheckRequest,
    project_id: str = "default",
    correlation_id: Optional[str] = None
):
    """
    Check financial covenant compliance
    Critical for lender confidence!
    """
    try:
        engine = ProjectFinanceEngine(project_id, correlation_id)
        
        # Build metrics dict
        metrics = {
            "dscr": request.dscr
        }
        
        # Check covenants
        result = engine.check_covenants(
            metrics=metrics,
            covenant_requirements=request.covenant_requirements
        )
        
        return {
            "success": True,
            "project_id": project_id,
            "correlation_id": engine.correlation_id,
            "covenant_check": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INTEGRATION ENDPOINTS (for linking to trading platform)
# ============================================================================

@router.post("/integrate/calculate-from-capacity")
async def calculate_from_capacity(
    capacity_id: str,
    correlation_id: str,
    offtake_contracts: List[Dict],
    subsidies: Dict[str, float],
    opex_eur_kg: float
):
    """
    Calculate CFADS from capacity + offtake contracts
    Integrates with trading platform data!
    """
    try:
        # This would query the trading platform for capacity details
        # For now, we'll use the provided data
        
        result = CFADSCalculator.calculate_with_offtake_contracts(
            contracts=offtake_contracts,
            production_mtpd=100.0,  # Would come from capacity
            subsidies=subsidies,
            opex_eur_kg=opex_eur_kg
        )
        
        return {
            "success": True,
            "capacity_id": capacity_id,
            "correlation_id": correlation_id,
            "cfads": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/summary")
async def get_project_summary(project_id: str):
    """
    Get comprehensive project financial summary
    Would integrate with trading platform + construction tracking
    """
    # This is a placeholder - would integrate with actual project data
    return {
        "project_id": project_id,
        "status": "under_construction",
        "financial_summary": {
            "total_capex": 100_000_000,
            "spent_to_date": 60_000_000,
            "percent_complete": 60,
            "current_milestone": "TR5",
            "financing": {
                "senior_debt": 60_000_000,
                "junior_debt": 15_000_000,
                "equity": 25_000_000,
                "drawn_to_date": 55_000_000
            },
            "covenants": {
                "all_compliant": True,
                "dsra_funded": True,
                "dscr_projected": 1.45
            }
        }
    }


# ============================================================================
# EXAMPLE/DEMO ENDPOINTS
# ============================================================================

@router.get("/examples/green-h2-project")
async def example_green_h2():
    """
    Example calculation for a typical green H2 project
    50 MTPD capacity, €200M CAPEX, 60/20/20 debt/junior/equity
    """
    try:
        # Calculate CFADS
        cfads_result = CFADSCalculator.calculate(
            production_volume_mtpd=50.0,
            offtake_price_eur_kg=6.0,
            subsidies={'45V': 3.0, 'RED_III': 0.5},
            opex_eur_kg=2.0,
            maintenance_capex=1_000_000
        )
        
        # Model lifetime
        engine = ProjectFinanceEngine("example-h2-1")
        lifetime_result = engine.model_project_lifetime(
            capacity_mtpd=50.0,
            price_eur_kg=6.0,
            opex_eur_kg=2.0,
            total_capex=200_000_000,
            senior_debt_amount=120_000_000,
            interest_rate=0.07,
            tenor_years=15
        )
        
        # Execute waterfall
        waterfall_result = CashFlowWaterfall.create_typical_structure(
            cfads=cfads_result['cfads'],
            senior_debt_service=lifetime_result['summary']['total_debt_service'] / 15,
            dsra_required=lifetime_result['summary']['total_debt_service'] / 15 / 2
        )
        
        return {
            "project_type": "Green H2 - 50 MTPD",
            "capex": "€200M",
            "financing": "60% senior debt, 20% junior, 20% equity",
            "cfads_annual": cfads_result,
            "lifetime_projection": lifetime_result['summary'],
            "waterfall": waterfall_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("Project Finance API Routes loaded")
