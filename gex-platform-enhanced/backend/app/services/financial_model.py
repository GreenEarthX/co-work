
# ============================================================================
# OPTION A: MICROSERVICES (Recommended - calls external service)
# ============================================================================

"""
import httpx
import sqlite3
import uuid
import os
from typing import Dict

FINANCE_MODEL_API = "http://localhost:8001"


async def run_financial_model_for_match(match_id: str) -> Dict:
    '''
    Call gex_pf_engine microservice
    
    REQUIRES: gex_pf_engine running on port 8001
    '''
    # Build request
    request = {
        "project_id": match_id,
        "capex_total": 500_000_000,
        "subsidy_pct": 15.0,
        "power_price_index": 100.0,
        "cod_delay_months": 0,
        "certification_regime": "RFNBO",
        "tranches": await get_default_tranches(),
    }
    
    # Call engine
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{FINANCE_MODEL_API}/api/v1/model/stress-test",
            json=request
        )
        response.raise_for_status()
        result = response.json()
    
    # Store in database
    store_financial_model_result(match_id, result)
    
    return result


async def get_default_tranches():
    '''Fetch default funding stack from engine'''
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{FINANCE_MODEL_API}/api/v1/model/default-tranches"
        )
        return response.json()


def store_financial_model_result(match_id: str, result: Dict):
    '''Store result in database'''
    DB_PATH = os.path.join(os.path.dirname(__file__), '../../gex_platform.db')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    result_id = str(uuid.uuid4())
    
    cursor.execute('''
        INSERT INTO financial_model_results (
            id, match_id, bankability,
            dscr_base, dscr_stress,
            irr_base, irr_stress, recommendation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result_id,
        match_id,
        result['bankability'],
        result['base']['dscr_min'],
        result['stress']['dscr_min'],
        result['base']['irr_equity'],
        result['stress']['irr_equity'],
        result['recommendation']
    ))
    
    conn.commit()
    conn.close()
"""

# ============================================================================
# OPTION B: EMBEDDED (Simpler - engine code directly here)
# ============================================================================

# Uncomment below if using OPTION B

import math
import sqlite3
import uuid
import os
from typing import Dict, Literal
from pydantic import BaseModel


class ScenarioInputs(BaseModel):
    """Excel 'Inputs' sheet"""
    scenario: Literal["Base", "Stress"] = "Base"
    capex_index: float = 100
    subsidy_pct: float = 15
    power_price_index: float = 100
    cod_delay_months: int = 0
    elec_sensitivity: float = 0.6
    base_cfads_pct: float = 12
    blended_debt_tenor_years: int = 15
    construction_interest_rate: float = 6


class FundingTranche(BaseModel):
    """Individual debt/equity tranche"""
    source: str
    share_pct: float
    cost_pct: float
    type: Literal["Debt", "Equity", "Concessional"]


class FundingStack(BaseModel):
    """Excel funding stack"""
    tranches: list[FundingTranche]
    
    @property
    def debt_share(self) -> float:
        return sum(t.share_pct for t in self.tranches if t.type == "Debt")
    
    @property
    def blended_debt_rate(self) -> float:
        debt_tranches = [t for t in self.tranches if t.type == "Debt"]
        if not debt_tranches:
            return 0
        total_debt = sum(t.share_pct for t in debt_tranches)
        weighted_cost = sum(t.share_pct * t.cost_pct for t in debt_tranches)
        return weighted_cost / total_debt if total_debt > 0 else 0


class DSCRResult(BaseModel):
    """Excel DSCR & IRR Model output"""
    debt_share_pct: float
    blended_debt_rate: float
    idc_uplift_pct: float
    annuity_factor: float
    annual_debt_service_pct: float
    cfads_pct: float
    dscr: float  # KEY METRIC
    fcf_to_equity_pct: float
    equity_share_pct: float
    equity_irr_proxy: float


class FinancialModelEngine:
    """Excel calculation engine"""
    
    def run_model(self, inputs: ScenarioInputs, stack: FundingStack) -> DSCRResult:
        """Execute Excel calculations"""
        
        # Step 1: IDC Uplift
        idc_uplift_pct = self._calculate_idc(
            inputs.cod_delay_months,
            inputs.construction_interest_rate,
            stack.debt_share
        )
        
        # Step 2: Debt Metrics
        debt_share_pct = stack.debt_share
        blended_debt_rate = stack.blended_debt_rate
        
        # Step 3: Annuity Factor
        annuity_factor = self._calculate_annuity(
            blended_debt_rate / 100,
            inputs.blended_debt_tenor_years
        )
        
        # Step 4: Debt Service
        adjusted_debt = debt_share_pct * (1 + idc_uplift_pct / 100)
        annual_debt_service_pct = adjusted_debt * annuity_factor
        
        # Step 5: CFADS with power sensitivity
        power_drift = inputs.elec_sensitivity * (inputs.power_price_index - 100) / 100
        cfads_pct = inputs.base_cfads_pct * (1 + power_drift)
        
        # Step 6: DSCR (KEY OUTPUT)
        dscr = cfads_pct / annual_debt_service_pct if annual_debt_service_pct > 0 else 0
        
        # Step 7-8: Equity metrics
        fcf_to_equity_pct = cfads_pct - annual_debt_service_pct
        equity_share_pct = 100 - debt_share_pct - inputs.subsidy_pct
        equity_irr_proxy = (fcf_to_equity_pct / equity_share_pct * 100) if equity_share_pct > 0 else 0
        
        return DSCRResult(
            debt_share_pct=debt_share_pct,
            blended_debt_rate=blended_debt_rate,
            idc_uplift_pct=idc_uplift_pct,
            annuity_factor=annuity_factor,
            annual_debt_service_pct=annual_debt_service_pct,
            cfads_pct=cfads_pct,
            dscr=dscr,
            fcf_to_equity_pct=fcf_to_equity_pct,
            equity_share_pct=equity_share_pct,
            equity_irr_proxy=equity_irr_proxy
        )
    
    def _calculate_idc(self, delay_months: int, interest_rate: float, debt_share: float) -> float:
        """IDC = (delay/12) * rate * (debt_share/100) * 0.5"""
        if delay_months == 0:
            return 0
        return (delay_months / 12) * interest_rate * (debt_share / 100) * 0.5
    
    def _calculate_annuity(self, rate: float, periods: int) -> float:
        """Excel annuity: [r(1+r)^n] / [(1+r)^n - 1]"""
        if rate == 0:
            return 1 / periods
        numerator = rate * math.pow(1 + rate, periods)
        denominator = math.pow(1 + rate, periods) - 1
        return numerator / denominator
    
    def run_stress_test(self, inputs: ScenarioInputs, stack: FundingStack) -> Dict:
        """Run Base + Stress scenarios"""
        # Base
        base_result = self.run_model(inputs, stack)
        
        # Stress (Excel stress assumptions)
        stress_inputs = inputs.copy(deep=True)
        stress_inputs.scenario = "Stress"
        stress_inputs.subsidy_pct = 10  # Haircut
        stress_inputs.power_price_index = 120  # 20% shock
        stress_inputs.cod_delay_months = 12  # 1yr delay
        stress_result = self.run_model(stress_inputs, stack)
        
        return {"base": base_result, "stress": stress_result}
    
    def assess_bankability(self, results: Dict) -> str:
        """GREEN/AMBER/RED based on DSCR thresholds"""
        min_dscr = min(results["base"].dscr, results["stress"].dscr)
        
        if min_dscr >= 1.3:
            return "GREEN"
        elif min_dscr >= 1.1:
            return "AMBER"
        else:
            return "RED"


def run_financial_model_for_match(match_id: str) -> Dict:
    """
    Run financial model (EMBEDDED VERSION)
    
    Called by DD state machine postcondition
    """
    engine = FinancialModelEngine()
    
    # Default funding stack (Excel Pre-COD)
    stack = FundingStack(tranches=[
        FundingTranche(source="Senior Debt", share_pct=40, cost_pct=6.5, type="Debt"),
        FundingTranche(source="Junior Debt", share_pct=12, cost_pct=10, type="Debt"),
        FundingTranche(source="Mezzanine", share_pct=3, cost_pct=15, type="Debt"),
        FundingTranche(source="DFIs", share_pct=10, cost_pct=3, type="Debt"),
        FundingTranche(source="Green Bonds", share_pct=6, cost_pct=4, type="Debt"),
        FundingTranche(source="Grants", share_pct=15, cost_pct=0, type="Concessional"),
        FundingTranche(source="Equity", share_pct=14, cost_pct=15, type="Equity"),
    ])
    
    # Default inputs
    inputs = ScenarioInputs()
    
    # Run stress test
    results = engine.run_stress_test(inputs, stack)
    bankability = engine.assess_bankability(results)
    
    # Build result dict
    result = {
        "bankability": bankability,
        "base": results["base"].dict(),
        "stress": results["stress"].dict(),
    }
    
    # Store in database
    store_financial_model_result(match_id, result)
    
    return result


def store_financial_model_result(match_id: str, result: Dict):
    """Store financial model results in database"""
    DB_PATH = os.path.join(os.path.dirname(__file__), '../../gex_platform.db')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    result_id = str(uuid.uuid4())
    
    cursor.execute("""
        INSERT INTO financial_model_results (
            id, match_id, bankability, 
            dscr_base, dscr_stress, 
            irr_base, irr_stress, recommendation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result_id,
        match_id,
        result['bankability'],
        result['base']['dscr'],
        result['stress']['dscr'],
        result['base']['equity_irr_proxy'],
        result['stress']['equity_irr_proxy'],
        _generate_recommendation(result['bankability'], result['stress']['dscr'])
    ))
    
    conn.commit()
    conn.close()
    
    return result_id


def _generate_recommendation(bankability: str, dscr: float) -> str:
    """Generate text recommendation"""
    if bankability == "GREEN":
        return f"Bankable. DSCR {dscr:.2f}x exceeds 1.3x threshold. Proceed to settlement."
    elif bankability == "AMBER":
        return f"Marginal. DSCR {dscr:.2f}x. Negotiate covenants or loop back to matching."
    else:
        return f"Not bankable. DSCR {dscr:.2f}x below 1.1x. Restructure or loop back."


# Singleton
engine = FinancialModelEngine()