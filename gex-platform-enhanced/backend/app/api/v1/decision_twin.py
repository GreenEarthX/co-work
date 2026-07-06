"""
Decision Twin API - Expose certification evaluation endpoints
This is the PUBLIC API for the Decision Twin
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.core.decision_twin import DecisionTwin, CertificationKnowledgeBase
from app.core.fuel_catalog import offered_molecule_payload

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


class SovereignCertRequest(BaseModel):
    """Request model for sovereign certification pathway evaluation (G2)"""
    molecule: str
    country: str
    ghg_intensity: float
    renewable_electricity_pct: float
    dfi_provider: Optional[str] = None       # IFC, EIB, KfW, etc.
    concessional_share: Optional[float] = None  # 0-1, share of concessional in debt
    esg_score: Optional[float] = None        # 0-100
    project_id: Optional[str] = None
    correlation_id: Optional[str] = None


class SovereignESGRequest(BaseModel):
    """Request model for SOVEREIGN_ESG certification pathway evaluation"""
    molecule: str
    country: str
    ghg_intensity: float
    renewable_electricity_pct: float
    host_country_ndc_target: Optional[float] = 0.0
    carbon_attribution_split: Optional[Dict] = None  # {host_share, buyer_share}
    debt_for_nature_instrument_id: Optional[str] = None
    sovereign_credit_rating: Optional[str] = None
    project_id: Optional[str] = None
    correlation_id: Optional[str] = None


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
    # Sovereign / DFI extensions
    dfi_provider: Optional[str] = None
    concessional_share: Optional[float] = None
    esg_score: Optional[float] = None
    host_country_ndc_target: Optional[float] = None
    carbon_attribution_split: Optional[Dict] = None
    debt_for_nature_instrument_id: Optional[str] = None
    sovereign_credit_rating: Optional[str] = None


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
            "prevailing_wage": request.prevailing_wage,
            "dfi_provider": request.dfi_provider,
            "host_country_ndc_target": request.host_country_ndc_target,
            "carbon_attribution_split": request.carbon_attribution_split,
            "debt_for_nature_instrument_id": request.debt_for_nature_instrument_id,
            "sovereign_credit_rating": request.sovereign_credit_rating,
        }
        
        result = twin.evaluate_all_schemes(project_data)
        
        return {
            "success": True,
            "comprehensive_evaluation": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/sovereign-esg")
async def evaluate_sovereign_esg(request: SovereignESGRequest):
    """
    Evaluate SOVEREIGN_ESG certification pathway.

    Distinct from commercial certification — used for projects with
    sovereign-backed instruments (debt-for-nature swaps, NDC-linked
    carbon attribution, sovereign green bonds).

    Checks: NDC alignment, carbon attribution split, debt-for-nature
    linkage, sovereign credit assessment, GHG threshold.
    """
    try:
        twin = DecisionTwin(
            project_id=request.project_id,
            correlation_id=request.correlation_id or f"SOV-ESG-{request.project_id or 'eval'}",
        )
        result = twin.evaluate_sovereign_esg(
            molecule=request.molecule,
            country=request.country,
            ghg_intensity=request.ghg_intensity,
            renewable_electricity_pct=request.renewable_electricity_pct,
            host_country_ndc_target=request.host_country_ndc_target or 0.0,
            carbon_attribution_split=request.carbon_attribution_split,
            debt_for_nature_instrument_id=request.debt_for_nature_instrument_id,
            sovereign_credit_rating=request.sovereign_credit_rating,
        )
        return {"success": True, "evaluation": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/sovereign-certification")
async def evaluate_sovereign_certification(request: SovereignCertRequest):
    """
    Evaluate sovereign certification pathway (G2) for DFI-backed projects.

    Checks:
    - Eligible sovereign cert schemes based on country + molecule
    - DFI additionality requirements
    - ESG compliance threshold for concessional access
    - Concessional share limits (IFC max 25%, GCF max 50%)

    Returns eligibility map + recommendations.
    """
    try:
        results = []
        country = request.country.upper()
        molecule = request.molecule.upper()

        # EU countries eligible for RED III / RFNBO
        eu_countries = {
            "DE", "FR", "NL", "ES", "IT", "PT", "AT", "BE", "DK", "FI",
            "SE", "IE", "PL", "CZ", "GR", "RO", "BG", "HR", "SK", "SI",
            "HU", "LT", "LV", "EE", "CY", "MT", "LU",
        }

        # RED III
        if country in eu_countries:
            red_iii_eligible = (
                request.ghg_intensity <= 3.38  # 70% reduction vs 11.28 fossil
                and request.renewable_electricity_pct >= 90
            )
            results.append({
                "scheme": "RED_III",
                "eligible": red_iii_eligible,
                "ghg_check": request.ghg_intensity <= 3.38,
                "renewable_check": request.renewable_electricity_pct >= 90,
                "subsidy_estimate_eur_kg": 0.50 if red_iii_eligible else 0,
            })

        # RFNBO (EU, non-bio origin fuels)
        if country in eu_countries and molecule in ("H2", "NH3", "CH3OH", "SAF"):
            rfnbo_eligible = (
                request.ghg_intensity <= 3.38
                and request.renewable_electricity_pct >= 90
            )
            results.append({
                "scheme": "RFNBO",
                "eligible": rfnbo_eligible,
                "molecule_eligible": True,
                "ghg_check": request.ghg_intensity <= 3.38,
            })

        # 45V (US only, H2 only)
        if country == "US" and molecule == "H2":
            tier = None
            credit = 0
            if request.ghg_intensity < 0.45:
                tier, credit = 4, 3.00
            elif request.ghg_intensity < 1.5:
                tier, credit = 3, 1.00
            elif request.ghg_intensity < 2.5:
                tier, credit = 2, 0.75
            elif request.ghg_intensity < 4.0:
                tier, credit = 1, 0.60

            results.append({
                "scheme": "45V",
                "eligible": tier is not None,
                "tier": tier,
                "credit_usd_kg": credit,
            })

        # CORSIA (international, SAF only)
        if molecule == "SAF":
            corsia_eligible = request.ghg_intensity <= 3.0
            results.append({
                "scheme": "CORSIA",
                "eligible": corsia_eligible,
                "ghg_check": request.ghg_intensity <= 3.0,
            })

        # DFI additionality assessment
        dfi_assessment = None
        if request.dfi_provider:
            concessional_limits = {
                "IFC": 0.25, "EIB": 0.35, "EBRD": 0.30,
                "KfW": 0.30, "GCF": 0.50, "CIF": 0.40,
            }
            max_share = concessional_limits.get(request.dfi_provider, 0.25)
            share_ok = (request.concessional_share or 0) <= max_share
            esg_ok = (request.esg_score or 0) >= 60  # DFI minimum ESG threshold

            dfi_assessment = {
                "dfi_provider": request.dfi_provider,
                "max_concessional_share": max_share,
                "concessional_share_compliant": share_ok,
                "esg_threshold_met": esg_ok,
                "esg_minimum": 60,
                "additionality_eligible": share_ok and esg_ok,
                "catalytic_target": "5:1 commercial:concessional (IFC benchmark)",
            }

        return {
            "success": True,
            "sovereign_evaluation": {
                "country": country,
                "molecule": molecule,
                "certification_pathways": results,
                "dfi_assessment": dfi_assessment,
                "eligible_scheme_count": sum(1 for r in results if r["eligible"]),
                "total_subsidy_estimate": sum(
                    r.get("subsidy_estimate_eur_kg", 0) + r.get("credit_usd_kg", 0)
                    for r in results if r["eligible"]
                ),
            },
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
            },
            {
                "code": "SOVEREIGN_ESG",
                "name": "Sovereign ESG Pathway",
                "jurisdiction": "Global (DFI-backed)",
                "applies_to": ["H2", "NH3", "CH3OH", "SAF", "HVO"],
                "status": "active",
                "notes": "For projects with sovereign-backed instruments, debt-for-nature swaps, NDC-linked attribution"
            },
            {
                "code": "CERTIFHY",
                "name": "CertifHy Hydrogen Guarantee of Origin",
                "jurisdiction": "European Union",
                "applies_to": ["H2"],
                "status": "active"
            }
        ]
    }


@router.get("/knowledge-base/molecules")
async def get_supported_molecules():
    """
    Get list of supported molecules
    """
    return {"molecules": offered_molecule_payload()}


@router.post("/explain/{scheme}")
async def explain_certification_scheme(
    scheme: str,
    molecule: Optional[str] = None
):
    """
    Get detailed explanation of a certification scheme
    Human-readable explanation of rules, requirements, and calculations
    """
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
