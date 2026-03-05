"""
Decision Twin API - Expose certification evaluation endpoints
This is the PUBLIC API for the Decision Twin
"""
from tkinter.messagebox import IGNORE
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

''' -- IGNORE ---
from app.core.decision_twin import (
    DecisionTwin,
    CertificationScheme,
    Molecule
)
'''
router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class REDIII_EvaluationRequest(BaseModel):
    """Request model for RED III evaluation"""
    molecule: str
    ghg_intensity: float
    renewable_electricity_pct: float
    temporal_matching: Optional[str] = "monthly"
    geographical_correlation: Optional[bool] = True
    project_id: Optional[str] = None


class V45_EvaluationRequest(BaseModel):
    """Request model for 45V evaluation"""
    ghg_intensity: float
    electricity_source: str
    electricity_age_months: int
    temporal_matching: Optional[str] = "annual"
    prevailing_wage_compliance: Optional[bool] = False
    project_id: Optional[str] = None


class ComprehensiveEvaluationRequest(BaseModel):
    """Request model for comprehensive evaluation across all schemes"""
    molecule: str
    country: str
    ghg_intensity: float
    renewable_electricity_pct: float
    electricity_source: str
    electricity_age_months: Optional[int] = 12
    temporal_matching: Optional[str] = "monthly"
    geographical_correlation: Optional[bool] = True
    prevailing_wage: Optional[bool] = False
    project_id: Optional[str] = None
    correlation_id: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check for Decision Twin"""
    return {
        "status": "healthy",
        "service": "decision-twin",
        "version": "1.0.0"
    }


@router.post("/evaluate/red-iii")
async def evaluate_red_iii(request: REDIII_EvaluationRequest):
    """
    Evaluate project against RED III (EU Renewable Energy Directive)
    
    Returns detailed eligibility assessment with:
    - Pass/fail status
    - Detailed check results
    - Subsidy value estimate
    - Recommendations for improvement
    """
    try:
        twin = DecisionTwin(
            project_id=request.project_id,
            correlation_id=f"REDIII-{request.project_id or 'eval'}"
        )
        
        result = twin.evaluate_red_iii(
            molecule=request.molecule,
            ghg_intensity=request.ghg_intensity,
            renewable_electricity_pct=request.renewable_electricity_pct,
            temporal_matching=request.temporal_matching,
            geographical_correlation=request.geographical_correlation
        )
        
        return {
            "success": True,
            "evaluation": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/45v")
async def evaluate_45v(request: V45_EvaluationRequest):
    """
    Evaluate project against 45V (US Clean Hydrogen Production Tax Credit)
    
    Returns detailed eligibility assessment with:
    - Tier determination
    - Credit value (USD/kg)
    - Additionality checks
    - Wage requirement impact
    """
    try:
        twin = DecisionTwin(
            project_id=request.project_id,
            correlation_id=f"45V-{request.project_id or 'eval'}"
        )
        
        result = twin.evaluate_45v(
            molecule="H2",  # 45V only applies to H2
            ghg_intensity=request.ghg_intensity,
            electricity_source=request.electricity_source,
            electricity_age_months=request.electricity_age_months,
            temporal_matching=request.temporal_matching,
            region="US",
            prevailing_wage_compliance=request.prevailing_wage_compliance
        )
        
        return {
            "success": True,
            "evaluation": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/comprehensive")
async def evaluate_comprehensive(request: ComprehensiveEvaluationRequest):
    """
    Comprehensive evaluation across all relevant certification schemes
    
    Automatically evaluates:
    - RED III (if EU country)
    - 45V (if US + H2)
    - RFNBO (if applicable)
    - CORSIA (if SAF)
    
    Returns complete picture of certification opportunities
    """
    try:
        twin = DecisionTwin(
            project_id=request.project_id,
            correlation_id=request.correlation_id
        )
        
        project_data = {
            "molecule": request.molecule,
            "country": request.country,
            "ghg_intensity": request.ghg_intensity,
            "renewable_electricity_pct": request.renewable_electricity_pct,
            "electricity_source": request.electricity_source,
            "electricity_age_months": request.electricity_age_months,
            "temporal_matching": request.temporal_matching,
            "geographical_correlation": request.geographical_correlation,
            "prevailing_wage": request.prevailing_wage
        }
        
        result = twin.evaluate_all_schemes(project_data)
        
        return {
            "success": True,
            "comprehensive_evaluation": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-base/schemes")
async def get_certification_schemes():
    """
    Get list of supported certification schemes
    """
    return {
        "schemes": [
            {
                "code": "RED_III",
                "name": "Renewable Energy Directive III",
                "jurisdiction": "European Union",
                "applies_to": ["H2", "NH3", "CH3OH", "SAF", "HVO"],
                "status": "active"
            },
            {
                "code": "45V",
                "name": "Clean Hydrogen Production Tax Credit",
                "jurisdiction": "United States",
                "applies_to": ["H2"],
                "status": "active"
            },
            {
                "code": "RFNBO",
                "name": "Renewable Fuels of Non-Biological Origin",
                "jurisdiction": "European Union",
                "applies_to": ["H2", "NH3", "CH3OH", "SAF"],
                "status": "active"
            },
            {
                "code": "CORSIA",
                "name": "Carbon Offsetting for Aviation",
                "jurisdiction": "International (ICAO)",
                "applies_to": ["SAF"],
                "status": "active"
            }
        ]
    }


@router.get("/knowledge-base/molecules")
async def get_supported_molecules():
    """
    Get list of supported molecules
    """
    return {
        "molecules": [
            {"code": "H2", "name": "Hydrogen", "applications": ["Industry", "Transport", "Ammonia production"]},
            {"code": "NH3", "name": "Ammonia", "applications": ["Fertilizer", "Shipping fuel", "Energy carrier"]},
            {"code": "CH3OH", "name": "Methanol", "applications": ["Chemical feedstock", "Shipping fuel"]},
            {"code": "SAF", "name": "Sustainable Aviation Fuel", "applications": ["Aviation"]},
            {"code": "HVO", "name": "Hydrotreated Vegetable Oil", "applications": ["Transport"]},
            {"code": "RD", "name": "Renewable Diesel", "applications": ["Transport"]}
        ]
    }


@router.post("/explain/{scheme}")
async def explain_certification_scheme(
    scheme: str,
    molecule: Optional[str] = None
):
    """
    Get detailed explanation of a certification scheme
    Human-readable explanation of rules, requirements, and calculations
    """
    from app.core.decision_twin import CertificationKnowledgeBase
    
    kb = CertificationKnowledgeBase()
    
    if scheme.upper() == "RED_III":
        rules = kb.get_red_iii_rules()
    elif scheme.upper() == "45V":
        rules = kb.get_45v_rules()
    elif scheme.upper() == "RFNBO":
        rules = kb.get_rfnbo_rules()
    elif scheme.upper() == "CORSIA":
        rules = kb.get_corsia_rules()
    else:
        raise HTTPException(status_code=404, detail=f"Scheme {scheme} not found")
    
    return {
        "scheme": scheme.upper(),
        "rules": rules,
        "human_readable_summary": _generate_human_summary(rules, molecule)
    }


def _generate_human_summary(rules: Dict, molecule: Optional[str] = None) -> str:
    """Generate human-readable summary of certification requirements"""
    scheme = rules["scheme"]
    
    if scheme == "RED_III":
        return f"""
RED III (Renewable Energy Directive III) - European Union

Key Requirements:
1. GHG Savings: Must achieve >=70% emissions reduction vs fossil comparator
   - For {molecule or 'your molecule'}: Compare against fossil baseline
   
2. Renewable Electricity: >=90% of electricity must be renewable
   - Temporal correlation: Monthly matching (hourly from 2030)
   - Geographical correlation: Same bidding zone
   
3. Sustainability: No harmful land use change, sustainable water practices

Subsidy Value: ~€0.50/kg (varies by member state)

Timeline: Active now, hourly matching required from 2030
"""
    
    elif scheme == "45V":
        return f"""
45V Clean Hydrogen Production Tax Credit - United States

Key Requirements (H2 only):
1. GHG Intensity Tiers:
   - Tier 4 (Best): <0.45 kg CO2e/kg H2 → $3.00/kg credit
   - Tier 3: 0.45-1.5 kg CO2e/kg H2 → $1.00/kg credit
   - Tier 2: 1.5-2.5 kg CO2e/kg H2 → $0.75/kg credit
   - Tier 1: 2.5-4.0 kg CO2e/kg H2 → $0.60/kg credit

2. Additionality: Three pillars
   - New electricity source (<36 months old)
   - Temporal matching (phasing to hourly by 2032)
   - Regional deliverability

3. Prevailing Wage: Davis-Bacon wages required for FULL credit
   - Without compliance: Credit reduced to 20%

Duration: 10 years of production
Timeline: 2023-2032
"""
    
    return "Detailed explanation not available for this scheme."


if __name__ == "__main__":
    print("Decision Twin API loaded")
