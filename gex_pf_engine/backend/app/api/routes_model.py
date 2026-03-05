"""
Project Finance API Routes
Exposes financial modeling, CFADS, waterfall, and covenant monitoring
Event-driven with full audit trail
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import date

from app.core.engine import ProjectFinanceEngine
from app.core.cfads import CFADSCalculator
from app.core.waterfall import CashFlowWaterfall

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ProjectMetricsRequest(BaseModel):
    revenue: float
    opex: float
    capex: float
    debt_service: float
    period: str


class CFADSRequest(BaseModel):
    production_mtpd: float
    offtake_price_eur_kg: float
    subsidies: Optional[Dict[str, float]] = None
    opex_eur_kg: float = 0
    maintenance_capex: float = 0
    period_days: int = 365


class DrawdownRequest(BaseModel):
    milestone: str
    total_capex: float
    spent_to_date: float
    milestone_percentage: float
    senior_debt_total: float


class WaterfallRequest(BaseModel):
    cfads: float
    senior_debt_service: float
    junior_debt_service: float = 0
    mezzanine_service: float = 0
    dsra_required: float = 0
    maintenance_reserve: float = 0


class LifetimeModelRequest(BaseModel):
    capacity_mtpd: float
    price_eur_kg: float
    opex_eur_kg: float
    total_capex: float
    senior_debt_amount: float
    interest_rate: float
    tenor_years: int
    operations_start_year: int = 2027


class CovenantCheckRequest(BaseModel):
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
