"""
Onboarding Wizard - Orchestration API
Integrates Decision Twin + Finance Engine to provide immediate value
Guides producers through project viability assessment
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime
import httpx
import json
from app.core.decision_twin import DecisionTwin

router = APIRouter()

# Configuration
FINANCE_ENGINE_URL = "http://localhost:8001/api/v1/model"  # Finance microservice


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class Step1ProjectBasics(BaseModel):
    """Step 1: Basic project information"""
    molecule: str  # H2, NH3, CH3OH, SAF
    capacity_mtpd: float
    location: str
    country: str
    production_start_year: int
    production_end_year: int


class Step2Economics(BaseModel):
    """Step 2: Project economics"""
    estimated_capex_eur: float
    estimated_opex_eur_kg: float
    target_offtake_price_eur_kg: float
    electricity_source: str  # grid, renewable, nuclear
    feedstock_source: str  # water, biomass, waste, etc.


class Step3Certification(BaseModel):
    """Step 3: Certification requirements"""
    electricity_renewable_percentage: float  # 0-100
    ghg_intensity_target: Optional[float] = None  # kg CO2e/kg fuel
    target_certifications: List[str]  # ["RED_III", "45V", "RFNBO", etc.]
    existing_certifications: Optional[List[str]] = None


class CompleteOnboarding(BaseModel):
    """Complete onboarding wizard submission"""
    step1: Step1ProjectBasics
    step2: Step2Economics
    step3: Step3Certification
    contact_email: Optional[str] = None


# ============================================================================
# STEP 1: PROJECT BASICS + MARKET DEMAND
# ============================================================================

@router.post("/step1/market-demand")
async def check_market_demand(project: Step1ProjectBasics):
    """
    Step 1: Check market demand for this molecule/location
    Returns: Interest level, similar projects, market insights
    """
    try:
        # Check existing marketplace demand
        # In real implementation, would query actual RFQs and offers
        
        # Mock demand data (replace with actual DB queries)
        demand_signals = {
            "H2": {
                "active_rfqs": 12,
                "avg_price_eur_kg": 6.5,
                "demand_level": "high",
                "trend": "increasing"
            },
            "NH3": {
                "active_rfqs": 8,
                "avg_price_eur_kg": 0.45,
                "demand_level": "medium",
                "trend": "stable"
            },
            "SAF": {
                "active_rfqs": 15,
                "avg_price_eur_kg": 2.1,
                "demand_level": "very_high",
                "trend": "increasing"
            },
            "CH3OH": {
                "active_rfqs": 5,
                "avg_price_eur_kg": 0.38,
                "demand_level": "medium",
                "trend": "stable"
            }
        }
        
        molecule_demand = demand_signals.get(project.molecule, {
            "active_rfqs": 0,
            "avg_price_eur_kg": 0,
            "demand_level": "unknown",
            "trend": "unknown"
        })
        
        # Regional demand factors
        regional_multiplier = 1.0
        if project.country in ["Germany", "Netherlands", "France"]:
            regional_multiplier = 1.3  # High EU demand
        elif project.country in ["United States", "Canada"]:
            regional_multiplier = 1.2  # High North America demand
        
        # Timeline feasibility
        years_to_production = project.production_start_year - datetime.now().year
        timeline_assessment = "aggressive" if years_to_production < 3 else "feasible" if years_to_production < 5 else "conservative"
        
        return {
            "molecule": project.molecule,
            "market_demand": {
                "level": molecule_demand["demand_level"],
                "active_buyers": molecule_demand["active_rfqs"],
                "market_price_eur_kg": molecule_demand["avg_price_eur_kg"],
                "trend": molecule_demand["trend"],
                "regional_strength": regional_multiplier,
                "assessment": "Strong demand" if regional_multiplier > 1.1 else "Moderate demand"
            },
            "timeline": {
                "years_to_production": years_to_production,
                "assessment": timeline_assessment,
                "risk_level": "low" if timeline_assessment == "conservative" else "medium" if timeline_assessment == "feasible" else "high"
            },
            "similar_projects": {
                "count": 8,  # Mock - would query actual database
                "avg_capacity_mtpd": 45.0,
                "status_breakdown": {
                    "operational": 2,
                    "under_construction": 3,
                    "development": 3
                }
            },
            "next_step_recommendation": "Market looks promising! Let's check economics..."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Market demand check failed: {str(e)}")


# ============================================================================
# STEP 2: ECONOMICS + BANKABILITY CHECK
# ============================================================================

@router.post("/step2/bankability-check")
async def check_bankability(
    basics: Step1ProjectBasics,
    economics: Step2Economics
):
    """
    Step 2: Check project bankability
    Calls Finance Engine to calculate DSCR and financing feasibility
    """
    try:
        # Calculate annual production
        annual_production_kg = basics.capacity_mtpd * 365
        
        # Estimate subsidies (will be refined in Step 3)
        estimated_subsidies = {}
        if economics.electricity_source == "renewable":
            if basics.country in ["United States", "Canada"]:
                estimated_subsidies["45V"] = 3.0  # US Production Tax Credit
            if basics.country in ["Germany", "France", "Netherlands", "Spain", "Italy"]:
                estimated_subsidies["RED_III"] = 0.5  # EU support
        
        # Call Finance Engine for CFADS calculation
        async with httpx.AsyncClient() as client:
            cfads_response = await client.post(
                f"{FINANCE_ENGINE_URL}/cfads/calculate",
                json={
                    "production_mtpd": basics.capacity_mtpd,
                    "offtake_price_eur_kg": economics.target_offtake_price_eur_kg,
                    "subsidies": estimated_subsidies,
                    "opex_eur_kg": economics.estimated_opex_eur_kg,
                    "maintenance_capex": economics.estimated_capex_eur * 0.02,  # 2% annual maintenance
                    "period_days": 365
                },
                timeout=10.0
            )
            
            if cfads_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Finance engine unavailable")
            
            cfads_result = cfads_response.json()["cfads"]
        
        # Estimate debt capacity (typical 60% senior debt)
        senior_debt_amount = economics.estimated_capex_eur * 0.60
        
        # Typical senior debt: 7% interest, 15 year tenor
        annual_debt_service = senior_debt_amount * 0.095  # Rough annuity
        
        # Calculate DSCR
        dscr = cfads_result["cfads"] / annual_debt_service if annual_debt_service > 0 else 0
        
        # Bankability assessment
        bankability_level = "highly_bankable" if dscr >= 1.4 else "bankable" if dscr >= 1.2 else "marginal" if dscr >= 1.0 else "not_bankable"
        
        # Recommended financing structure
        if dscr >= 1.3:
            structure = {
                "senior_debt": 60,
                "junior_debt": 15,
                "equity": 25,
                "estimated_cost_of_capital": 7.2
            }
        elif dscr >= 1.1:
            structure = {
                "senior_debt": 50,
                "junior_debt": 20,
                "equity": 30,
                "estimated_cost_of_capital": 8.5
            }
        else:
            structure = {
                "senior_debt": 40,
                "junior_debt": 20,
                "equity": 40,
                "estimated_cost_of_capital": 10.0
            }
        
        return {
            "financial_metrics": {
                "annual_revenue": cfads_result["total_revenue"],
                "annual_ebitda": cfads_result["ebitda"],
                "annual_cfads": cfads_result["cfads"],
                "ebitda_margin_pct": cfads_result["ebitda_margin"],
                "annual_debt_service": annual_debt_service,
                "dscr": round(dscr, 2)
            },
            "bankability": {
                "level": bankability_level,
                "dscr_assessment": "Strong" if dscr >= 1.4 else "Adequate" if dscr >= 1.2 else "Weak",
                "lender_confidence": "High" if dscr >= 1.3 else "Medium" if dscr >= 1.1 else "Low"
            },
            "financing_structure": structure,
            "subsidy_estimate": {
                "annual_subsidy_revenue": cfads_result["subsidy_revenue"],
                "subsidy_types": estimated_subsidies,
                "note": "Preliminary estimate - will be refined in certification check"
            },
            "next_step_recommendation": f"DSCR of {dscr:.2f}x looks {'great' if dscr >= 1.3 else 'acceptable' if dscr >= 1.1 else 'challenging'}! Let's verify certification eligibility..."
        }
        
    except httpx.RequestError as e:
        # Finance engine not available - use simplified calculation
        annual_revenue = annual_production_kg * economics.target_offtake_price_eur_kg
        annual_opex = annual_production_kg * economics.estimated_opex_eur_kg
        ebitda = annual_revenue - annual_opex
        
        return {
            "financial_metrics": {
                "annual_revenue": annual_revenue,
                "annual_ebitda": ebitda,
                "note": "Simplified estimate - finance engine unavailable"
            },
            "bankability": {
                "level": "requires_detailed_analysis",
                "note": "Please provide more detailed financials"
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bankability check failed: {str(e)}")


# ============================================================================
# STEP 3: CERTIFICATION CHECK (DECISION TWIN!)
# ============================================================================

@router.post("/step3/certification-eligibility")
async def check_certification_eligibility(
    basics: Step1ProjectBasics,
    economics: Step2Economics,
    certification: Step3Certification
):
    """
    Step 3: Check certification eligibility via Decision Twin.
    RED III and 45V evaluation is delegated to the Decision Twin core engine.
    RFNBO is evaluated inline (not yet in DecisionTwin).
    """
    try:
        annual_production_kg = basics.capacity_mtpd * 365
        eligible: List[Dict] = []
        ineligible: List[Dict] = []
        subsidy_value: Dict[str, float] = {}
        total_annual_subsidy = 0.0

        # ----------------------------------------------------------------
        # RED III + 45V — delegated to Decision Twin
        # ----------------------------------------------------------------
        dt_schemes = [s for s in certification.target_certifications if s in ("RED_III", "45V")]
        if dt_schemes:
            project_data = {
                "molecule": basics.molecule,
                "country": basics.country,
                "ghg_intensity": certification.ghg_intensity_target or 0.45,
                "renewable_electricity_pct": certification.electricity_renewable_percentage,
                "electricity_source": economics.electricity_source,
                "electricity_age_months": 12,
                "temporal_matching": "monthly",
                "geographical_correlation": True,
                "prevailing_wage": False,
            }
            twin = DecisionTwin()
            dt_result = twin.evaluate_all_schemes(project_data)

            for scheme_code in dt_result.get("schemes_evaluated", []):
                if scheme_code not in certification.target_certifications:
                    continue
                sr = dt_result.get(scheme_code, {})
                status = sr.get("status", "ineligible")

                if status == "eligible":
                    value_per_kg = 0.0
                    if scheme_code == "RED_III" and sr.get("subsidy_value"):
                        value_per_kg = sr["subsidy_value"]["amount_eur_kg"]
                    elif scheme_code == "45V" and sr.get("credit_value"):
                        value_per_kg = sr["credit_value"]["final_credit_usd_kg"]
                    eligible.append({
                        "name": scheme_code,
                        "status": "eligible",
                        "subsidy_value_eur_kg": value_per_kg,
                        "annual_value": annual_production_kg * value_per_kg,
                        "requirements_met": [
                            c["check"] for c in sr.get("checks", []) if c.get("passed")
                        ],
                    })
                    subsidy_value[scheme_code] = value_per_kg
                    total_annual_subsidy += annual_production_kg * value_per_kg
                else:
                    ineligible.append({
                        "name": scheme_code,
                        "status": "not_eligible",
                        "reasons": [f["reason"] for f in sr.get("failures", [])],
                        "how_to_qualify": [
                            opt
                            for rec in sr.get("recommendations", [])
                            for opt in (rec.get("options") or [rec.get("action", "")])
                        ],
                    })

        # ----------------------------------------------------------------
        # RFNBO
        # ----------------------------------------------------------------
        if "RFNBO" in certification.target_certifications:
            rfnbo_ok = True
            rfnbo_reasons = []
            if certification.electricity_renewable_percentage < 95:
                rfnbo_ok = False
                rfnbo_reasons.append(
                    f"Renewable electricity {certification.electricity_renewable_percentage}% "
                    f"below 95% requirement"
                )
            if economics.electricity_source not in ["renewable", "wind", "solar", "hydro"]:
                rfnbo_ok = False
                rfnbo_reasons.append("Must use dedicated renewable electricity")

            if rfnbo_ok:
                eligible.append({
                    "name": "RFNBO",
                    "status": "eligible",
                    "subsidy_value_eur_kg": 0.3,
                    "annual_value": annual_production_kg * 0.3,
                    "requirements_met": [
                        "Renewable electricity >= 95%",
                        "Dedicated renewable source",
                        "Temporal correlation with renewable generation",
                    ],
                })
                subsidy_value["RFNBO"] = 0.3
                total_annual_subsidy += annual_production_kg * 0.3
            else:
                ineligible.append({
                    "name": "RFNBO",
                    "status": "not_eligible",
                    "reasons": rfnbo_reasons,
                    "how_to_qualify": [
                        "Use 100% renewable electricity",
                        "Install dedicated renewable generation (wind/solar)",
                        "Ensure temporal and geographical correlation",
                    ],
                })

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        annual_revenue = annual_production_kg * economics.target_offtake_price_eur_kg
        subsidy_pct = (total_annual_subsidy / annual_revenue * 100) if annual_revenue > 0 else 0.0

        return {
            "eligible_certifications": eligible,
            "ineligible_certifications": ineligible,
            "subsidy_value": subsidy_value,
            "total_annual_subsidy": total_annual_subsidy,
            "requirements": {},
            "summary": {
                "total_eligible": len(eligible),
                "total_ineligible": len(ineligible),
                "annual_subsidy_value": total_annual_subsidy,
                "subsidy_percentage_of_revenue": subsidy_pct,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Certification check failed: {str(e)}")


# ============================================================================
# STEP 4: GENERATE VIABILITY REPORT
# ============================================================================

@router.post("/complete")
async def complete_onboarding(submission: CompleteOnboarding):
    """
    Complete onboarding wizard
    Generates comprehensive viability report
    Creates project record if user wants to proceed
    """
    try:
        # Run all checks
        demand_check = await check_market_demand(submission.step1)
        bankability_check = await check_bankability(submission.step1, submission.step2)
        certification_check = await check_certification_eligibility(
            submission.step1,
            submission.step2,
            submission.step3
        )
        
        # Calculate overall viability score (0-100)
        score = 0
        
        # Market demand (30 points)
        if demand_check["market_demand"]["level"] == "very_high":
            score += 30
        elif demand_check["market_demand"]["level"] == "high":
            score += 25
        elif demand_check["market_demand"]["level"] == "medium":
            score += 15
        
        # Bankability (40 points)
        dscr = bankability_check["financial_metrics"]["dscr"]
        if dscr >= 1.4:
            score += 40
        elif dscr >= 1.3:
            score += 35
        elif dscr >= 1.2:
            score += 25
        elif dscr >= 1.0:
            score += 15
        
        # Certification (30 points)
        cert_score = (
            certification_check["summary"]["total_eligible"] * 10
        )
        score += min(cert_score, 30)
        
        # Overall assessment
        if score >= 80:
            viability = "highly_viable"
            recommendation = "Excellent project! Proceed to full listing."
        elif score >= 60:
            viability = "viable"
            recommendation = "Promising project. Upload FEED study to list on marketplace."
        elif score >= 40:
            viability = "potentially_viable"
            recommendation = "Some challenges exist. Consider optimizing economics or certification."
        else:
            viability = "requires_improvement"
            recommendation = "Significant improvements needed before marketplace listing."
        
        # Generate report
        report = {
            "generated_at": datetime.now().isoformat(),
            "viability_score": score,
            "viability_level": viability,
            "recommendation": recommendation,
            
            "project_summary": {
                "molecule": submission.step1.molecule,
                "capacity_mtpd": submission.step1.capacity_mtpd,
                "location": f"{submission.step1.location}, {submission.step1.country}",
                "start_year": submission.step1.production_start_year,
                "capex": submission.step2.estimated_capex_eur
            },
            
            "market_assessment": demand_check,
            "financial_assessment": bankability_check,
            "certification_assessment": certification_check,
            
            "next_steps": []
        }
        
        # Personalized next steps
        if score >= 60:
            report["next_steps"].append({
                "action": "Upload FEED Study",
                "priority": "high",
                "benefit": "Qualify for marketplace listing"
            })
            report["next_steps"].append({
                "action": "Create Full Project Profile",
                "priority": "high",
                "benefit": "Become visible to buyers and lenders"
            })
        
        if certification_check["summary"]["total_ineligible"] > 0:
            report["next_steps"].append({
                "action": "Optimize for Additional Certifications",
                "priority": "medium",
                "benefit": f"Unlock €{certification_check['total_annual_subsidy']:,.0f}/year in subsidies"
            })
        
        if dscr < 1.3:
            report["next_steps"].append({
                "action": "Improve Project Economics",
                "priority": "high",
                "benefit": "Achieve bankable DSCR >1.3x"
            })
        
        report["next_steps"].append({
            "action": "Browse Active RFQs",
            "priority": "medium",
            "benefit": "Find potential offtake partners"
        })
        
        return {
            "success": True,
            "report": report,
            "contact_saved": submission.contact_email is not None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


# ============================================================================
# TRUST SCORE
# ============================================================================

class TrustScoreWeights(BaseModel):
    """Configurable weights for Trust Score factors (must sum to 1.0)"""
    market: float = 0.30
    bankability: float = 0.40
    certification: float = 0.30


class TrustScoreRequest(BaseModel):
    step1: Step1ProjectBasics
    step2: Step2Economics
    step3: Step3Certification
    weights: Optional[TrustScoreWeights] = None


@router.post("/trust-score")
async def compute_trust_score(submission: TrustScoreRequest):
    """
    Compute Trust Score (0–100) for a project.

    Composite of three factors:
      - market      : demand level for the molecule/region  (default 30 pts)
      - bankability : DSCR quality                          (default 40 pts)
      - certification: eligible certification count         (default 30 pts)

    Weights are configurable via the `weights` field.
    Pass actor-specific weight profiles to reflect lender vs. regulator vs. producer perspective.
    """
    try:
        w = submission.weights or TrustScoreWeights()

        demand_check = await check_market_demand(submission.step1)
        bankability_check = await check_bankability(submission.step1, submission.step2)
        certification_check = await check_certification_eligibility(
            submission.step1, submission.step2, submission.step3
        )

        # --- market factor (normalised 0-1) ---
        level = demand_check["market_demand"]["level"]
        market_score = {"very_high": 1.0, "high": 0.85, "medium": 0.5, "low": 0.25}.get(level, 0.0)

        # --- bankability factor (normalised 0-1) ---
        dscr = bankability_check["financial_metrics"].get("dscr", 0)
        if dscr >= 1.4:
            bankability_score = 1.0
        elif dscr >= 1.3:
            bankability_score = 0.875
        elif dscr >= 1.2:
            bankability_score = 0.625
        elif dscr >= 1.0:
            bankability_score = 0.375
        else:
            bankability_score = 0.0

        # --- certification factor (normalised 0-1, max 3 certifications) ---
        n_eligible = certification_check["summary"]["total_eligible"]
        cert_score = min(n_eligible / 3.0, 1.0)

        # --- weighted composite (scaled to 100) ---
        raw = (
            w.market * market_score
            + w.bankability * bankability_score
            + w.certification * cert_score
        )
        trust_score = round(raw * 100, 1)

        if trust_score >= 80:
            band = "STRONG"
        elif trust_score >= 60:
            band = "DEVELOPING"
        elif trust_score >= 40:
            band = "EARLY"
        else:
            band = "SPECULATIVE"

        return {
            "trust_score": trust_score,
            "band": band,
            "weights_used": {"market": w.market, "bankability": w.bankability, "certification": w.certification},
            "factors": {
                "market": {
                    "normalised": market_score,
                    "weighted_pts": round(w.market * market_score * 100, 1),
                    "demand_level": level,
                },
                "bankability": {
                    "normalised": bankability_score,
                    "weighted_pts": round(w.bankability * bankability_score * 100, 1),
                    "dscr": dscr,
                },
                "certification": {
                    "normalised": cert_score,
                    "weighted_pts": round(w.certification * cert_score * 100, 1),
                    "eligible_count": n_eligible,
                },
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trust Score computation failed: {str(e)}")


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/reference-data/molecules")
async def get_molecule_options():
    """Get available molecule types with descriptions"""
    return {
        "molecules": [
            {
                "code": "H2",
                "name": "Hydrogen",
                "description": "Green hydrogen via electrolysis",
                "typical_uses": ["Industry feedstock", "Fuel cells", "Ammonia production"]
            },
            {
                "code": "NH3",
                "name": "Ammonia",
                "description": "Green ammonia from renewable H2",
                "typical_uses": ["Fertilizer", "Shipping fuel", "Energy carrier"]
            },
            {
                "code": "SAF",
                "name": "Sustainable Aviation Fuel",
                "description": "Drop-in jet fuel from renewable sources",
                "typical_uses": ["Aviation", "Military"]
            },
            {
                "code": "CH3OH",
                "name": "Methanol",
                "description": "Green methanol from renewable sources",
                "typical_uses": ["Chemical feedstock", "Shipping fuel", "Fuel blending"]
            }
        ]
    }


@router.get("/reference-data/certifications")
async def get_certification_options():
    """Get available certification schemes"""
    return {
        "certifications": [
            {
                "code": "RED_III",
                "name": "EU Renewable Energy Directive III",
                "region": "European Union",
                "description": "EU sustainability criteria for renewable fuels"
            },
            {
                "code": "45V",
                "name": "US Production Tax Credit (45V)",
                "region": "United States",
                "description": "US tax credit for clean hydrogen production"
            },
            {
                "code": "RFNBO",
                "name": "Renewable Fuels of Non-Biological Origin",
                "region": "European Union",
                "description": "EU qualification for synthetic renewable fuels"
            },
            {
                "code": "CORSIA",
                "name": "Carbon Offsetting for Aviation",
                "region": "International",
                "description": "ICAO sustainability scheme for aviation fuels"
            }
        ]
    }


if __name__ == "__main__":
    print("Onboarding Wizard API loaded")
