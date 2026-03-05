from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json
import os

router = APIRouter()



# Database path - 3 levels up from app/api/endpoints/ to backend/
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../gex_platform.db')

# ADD THESE LINES:
insurance_db = None
guarantees_db = None
risks_db = None

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

# Stage Gates
class StageGateResponse(BaseModel):
    name: str
    status: str
    completionPct: int
    criticalItems: List[str]
    dueDate: str
    completedDate: Optional[str] = None

@router.get("/stage-gates", response_model=List[StageGateResponse])
async def get_stage_gates():
    """Get all stage gates for finance tracking"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT gate_name, status, completion_pct, critical_items, 
                   due_date, completed_date
            FROM stage_gates
            ORDER BY 
                CASE status
                    WHEN 'complete' THEN 1
                    WHEN 'in-progress' THEN 2
                    WHEN 'at-risk' THEN 3
                    WHEN 'pending' THEN 4
                END
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            critical_items_str = row['critical_items'] or '[]'
            critical_items = json.loads(critical_items_str) if critical_items_str else []
            
            result.append({
                "name": row['gate_name'],
                "status": row['status'],
                "completionPct": row['completion_pct'],
                "criticalItems": critical_items,
                "dueDate": row['due_date'],
                "completedDate": row['completed_date'],
            })
        
        return result
        
    except Exception as e:
        print(f"Error fetching stage gates: {e}")
        # Return sample data if database fails
        return [
            {
                "name": "FEL (Front End Loading)",
                "status": "complete",
                "completionPct": 100,
                "criticalItems": [],
                "dueDate": "2024-03-15",
                "completedDate": "2024-03-10",
            },
            {
                "name": "FEED (Front End Engineering Design)",
                "status": "complete",
                "completionPct": 100,
                "criticalItems": [],
                "dueDate": "2024-09-30",
                "completedDate": "2024-09-25",
            },
            {
                "name": "FID (Final Investment Decision)",
                "status": "at-risk",
                "completionPct": 78,
                "criticalItems": [
                    "EPC contract finalization (7 days overdue)",
                    "Grid connection agreement pending signature",
                    "Final environmental permit approval needed",
                    "Offtake agreements at 72% (target: 75%)",
                ],
                "dueDate": "2026-02-15",
            },
        ]

# Covenants
class CovenantResponse(BaseModel):
    name: str
    current: str
    required: str
    status: str
    trend: str
    lastUpdated: str

@router.get("/covenants", response_model=List[CovenantResponse])


# Insurance
class InsuranceResponse(BaseModel):
    id: str
    type: str
    provider: str
    coverage: str
    premium: str
    startDate: str
    expiryDate: str
    daysUntilExpiry: int
    status: str

@router.get("/insurance", response_model=List[InsuranceResponse])


# Guarantees
class GuaranteeResponse(BaseModel):
    id: str
    type: str
    provider: str
    amount: str
    beneficiary: str
    expiryDate: str
    status: str

@router.get("/guarantees", response_model=List[GuaranteeResponse])


# Contracts (for revenue)
class ContractResponse(BaseModel):
    id: str
    counterparty: str
    molecule: str
    volume_mtpd: float
    price_eur_kg: float
    pricingBasis: str
    startDate: str
    endDate: str
    tenor_years: int
    creditRating: str
    status: str

@router.get("/contracts", response_model=List[ContractResponse])


# Risks
class RiskResponse(BaseModel):
    id: str
    category: str
    description: str
    impact: str
    likelihood: str
    mitigation: str
    owner: str
    status: str

@router.get("/risks", response_model=List[RiskResponse])


# Insurance
class InsuranceResponse(BaseModel):
    id: str
    type: str
    provider: str
    coverage: str
    premium: str
    startDate: str
    expiryDate: str
    daysUntilExpiry: int
    status: str

@router.get("/insurance", response_model=List[InsuranceResponse])
async def get_insurance():
    """Get all insurance policies"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT policy_id_external, policy_type, provider, coverage_amount, 
                   premium_amount, start_date, expiry_date, status,
                   CAST((julianday(expiry_date) - julianday('now')) AS INTEGER) as days_until_expiry
            FROM insurance_policies
            ORDER BY days_until_expiry
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "id": row['policy_id_external'],
            "type": row['policy_type'],
            "provider": row['provider'],
            "coverage": row['coverage_amount'],
            "premium": row['premium_amount'],
            "startDate": row['start_date'],
            "expiryDate": row['expiry_date'],
            "daysUntilExpiry": row['days_until_expiry'],
            "status": row['status'],
        } for row in rows]
        
    except Exception as e:
        print(f"Error fetching insurance: {e}")
        return []

# Guarantees
class GuaranteeResponse(BaseModel):
    id: str
    type: str
    provider: str
    amount: str
    beneficiary: str
    expiryDate: str
    status: str

@router.get("/guarantees", response_model=List[GuaranteeResponse])
async def get_guarantees():
    """Get all guarantees"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT guarantee_id_external, guarantee_type, provider, 
                   amount, beneficiary, expiry_date, status
            FROM guarantees
            WHERE status = 'active'
            ORDER BY expiry_date
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "id": row['guarantee_id_external'],
            "type": row['guarantee_type'],
            "provider": row['provider'],
            "amount": row['amount'],
            "beneficiary": row['beneficiary'],
            "expiryDate": row['expiry_date'],
            "status": row['status'],
        } for row in rows]
        
    except Exception as e:
        print(f"Error fetching guarantees: {e}")
        return []

# Contracts (for revenue)
class ContractResponse(BaseModel):
    id: str
    counterparty: str
    molecule: str
    volume_mtpd: float
    price_eur_kg: float
    pricingBasis: str
    startDate: str
    endDate: str
    tenor_years: int
    creditRating: str
    status: str

@router.get("/contracts", response_model=List[ContractResponse])
async def get_contracts():
    """Get all revenue contracts"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT contract_id_external, counterparty, molecule, 
                   volume_mtpd, price_eur_kg, pricing_basis,
                   start_date, end_date, tenor_years, credit_rating, status
            FROM contracts
            ORDER BY 
                CASE status
                    WHEN 'active' THEN 1
                    WHEN 'negotiating' THEN 2
                    WHEN 'expired' THEN 3
                END,
                volume_mtpd DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "id": row['contract_id_external'],
            "counterparty": row['counterparty'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "pricingBasis": row['pricing_basis'] or '',
            "startDate": row['start_date'],
            "endDate": row['end_date'],
            "tenor_years": row['tenor_years'],
            "creditRating": row['credit_rating'] or '',
            "status": row['status'],
        } for row in rows]
        
    except Exception as e:
        print(f"Error fetching contracts: {e}")
        return []

# Risks
class RiskResponse(BaseModel):
    id: str
    category: str
    description: str
    impact: str
    likelihood: str
    mitigation: str
    owner: str
    status: str

@router.get("/risks", response_model=List[RiskResponse])
async def get_risks():
    """Get all risks from risk register"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT risk_id_external, category, description, 
                   impact, likelihood, mitigation, owner, status
            FROM risks
            WHERE status IN ('active', 'escalated')
            ORDER BY 
                CASE impact
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                CASE likelihood
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "id": row['risk_id_external'],
            "category": row['category'],
            "description": row['description'],
            "impact": row['impact'],
            "likelihood": row['likelihood'],
            "mitigation": row['mitigation'] or '',
            "owner": row['owner'] or '',
            "status": row['status'],
        } for row in rows]
        
    except Exception as e:
        print(f"Error fetching risks: {e}")
        return []
# ============================================================================
# FINANCIAL MODEL ENDPOINTS (NEW)
# ============================================================================

from app.services.financial_model import engine, ScenarioInputs, FundingStack, FundingTranche

class FinancialModelRequest(BaseModel):
    """Request to run financial model"""
    match_id: str
    scenario: str = "Base"
    # Optional overrides
    capex_index: Optional[float] = None
    subsidy_pct: Optional[float] = None

class FinancialModelResponse(BaseModel):
    """Financial model results"""
    match_id: str
    bankability: str
    dscr_base: float
    dscr_stress: float
    irr_base: float
    irr_stress: float
    recommendation: str

@router.post("/financial-model/run", response_model=FinancialModelResponse)
async def run_financial_model(request: FinancialModelRequest):
    """
    Execute financial model for a match
    Called by DD state machine OR manually
    """
    try:
        from app.services.financial_model import run_financial_model_for_match
        
        result = run_financial_model_for_match(request.match_id)
        
        # Generate recommendation
        stress_dscr = result["stress"]["dscr"]
        if result["bankability"] == "GREEN":
            recommendation = f"Bankable. DSCR {stress_dscr:.2f}x exceeds 1.3x threshold. Proceed to settlement."
        elif result["bankability"] == "AMBER":
            recommendation = f"Marginal. DSCR {stress_dscr:.2f}x. Negotiate covenants or loop back to matching."
        else:
            recommendation = f"Not bankable. DSCR {stress_dscr:.2f}x below 1.1x. Restructure or loop back."
        
        return {
            "match_id": request.match_id,
            "bankability": result["bankability"],
            "dscr_base": result["base"]["dscr"],
            "dscr_stress": result["stress"]["dscr"],
            "irr_base": result["base"]["equity_irr_proxy"],
            "irr_stress": result["stress"]["equity_irr_proxy"],
            "recommendation": recommendation,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financial-model/results/{match_id}", response_model=FinancialModelResponse)
async def get_financial_model_results(match_id: str):
    """
    Get stored financial model results for a match
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT bankability, dscr_base, dscr_stress, irr_base, irr_stress, recommendation
            FROM financial_model_results
            WHERE match_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (match_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="No financial model results found")
        
        return {
            "match_id": match_id,
            "bankability": row['bankability'],
            "dscr_base": row['dscr_base'],
            "dscr_stress": row['dscr_stress'],
            "irr_base": row['irr_base'],
            "irr_stress": row['irr_stress'],
            "recommendation": row['recommendation'],
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#Also ENHANCE your existing `/covenants` endpoint to include DSCR from financial model:

# MODIFY EXISTING get_covenants() function
@router.get("/covenants", response_model=List[CovenantResponse])
async def get_covenants():
    """Get all covenant metrics (ENHANCED with financial model DSCR)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Existing covenants from DB
        cursor.execute("""
            SELECT covenant_name, current_value, required_value, 
                   status, trend, last_updated
            FROM covenants
            ORDER BY 
                CASE status
                    WHEN 'breach' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'compliant' THEN 3
                END
        """)
        
        rows = cursor.fetchall()
        result = [{
            "name": row['covenant_name'],
            "current": row['current_value'],
            "required": row['required_value'],
            "status": row['status'],
            "trend": row['trend'] or 'stable',
            "lastUpdated": row['last_updated'],
        } for row in rows]
        
        # ADD: DSCR from latest financial model
        cursor.execute("""
            SELECT dscr_stress as current_dscr, created_at
            FROM financial_model_results
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        fm_row = cursor.fetchone()
        if fm_row:
            dscr_value = fm_row['current_dscr']
            status = "compliant" if dscr_value >= 1.3 else ("warning" if dscr_value >= 1.1 else "breach")
            
            result.insert(0, {  # Insert at top (most important)
                "name": "DSCR (Debt Service Coverage Ratio)",
                "current": f"{dscr_value:.2f}x",
                "required": "≥1.30x",
                "status": status,
                "trend": "stable",
                "lastUpdated": fm_row['created_at'],
            })
        
        conn.close()
        return result
        
    except Exception as e:
        print(f"Error fetching covenants: {e}")
        return []