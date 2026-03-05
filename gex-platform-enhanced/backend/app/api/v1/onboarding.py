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
    Step 3: Check certification eligibility
    THIS IS THE DECISION TWIN IN ACTION!
    Returns: Which certifications qualify, subsidy amounts, requirements
    """
    try:
        results = {
            "eligible_certifications": [],
            "ineligible_certifications": [],
            "subsidy_value": {},
            "total_annual_subsidy": 0,
            "requirements": {}
        }
        
        annual_production_kg = basics.capacity_mtpd * 365
        
        # ====================================================================
        # RED III (EU Renewable Energy Directive)
        # ====================================================================
        if "RED_III" in certification.target_certifications:
            red_iii_eligible = True
            red_iii_reasons = []
            
            # Check GHG intensity (must be <70% of fossil comparator)
            fossil_comparator = {
                "H2": 94.0,  # kg CO2e/kg H2 from natural gas
                "NH3": 2.6,  # kg CO2e/kg NH3 from natural gas
                "SAF": 3.0,  # kg CO2e/L SAF from fossil
                "CH3OH": 0.69  # kg CO2e/kg MeOH from natural gas
            }
            
            comparator = fossil_comparator.get(basics.molecule, 100)
            max_ghg = comparator * 0.70  # 70% threshold
            
            if certification.ghg_intensity_target and certification.ghg_intensity_target > max_ghg:
                red_iii_eligible = False
                red_iii_reasons.append(f"GHG intensity {certification.ghg_intensity_target:.1f} exceeds {max_ghg:.1f} kg CO2e/kg threshold")
            
            # Check renewable electricity
            if certification.electricity_renewable_percentage < 90:
                red_iii_eligible = False
                red_iii_reasons.append(f"Renewable electricity {certification.electricity_renewable_percentage}% below 90% requirement")
            
            if red_iii_eligible:
                results["eligible_certifications"].append({
                    "name": "RED III",
                    "status": "eligible",
                    "subsidy_value_eur_kg": 0.5,
                    "annual_value": annual_production_kg * 0.5,
                    "requirements_met": [
                        f"GHG intensity below {max_ghg:.1f} kg CO2e/kg",
                        f"Renewable electricity >= 90%"
                    ]
                })
                results["subsidy_value"]["RED_III"] = 0.5
                results["total_annual_subsidy"] += annual_production_kg * 0.5
            else:
                results["ineligible_certifications"].append({
                    "name": "RED III",
                    "status": "not_eligible",
                    "reasons": red_iii_reasons,
                    "how_to_qualify": [
                        "Increase renewable electricity to >90%",
                        f"Reduce GHG intensity below {max_ghg:.1f} kg CO2e/kg"
                    ]
                })
        
        # ====================================================================
        # 45V (US Production Tax Credit)
        # ====================================================================
        if "45V" in certification.target_certifications:
            credit_45v = 0
            tier = None
            eligible_45v = True
            reasons_45v = []
            
            # Only for H2
            if basics.molecule != "H2":
                eligible_45v = False
                reasons_45v.append("45V only applies to hydrogen production")
            
            # Only in US
            if basics.country not in ["United States", "USA", "US"]:
                eligible_45v = False
                reasons_45v.append("45V only available in United States")
            
            if eligible_45v and certification.ghg_intensity_target:
                ghg = certification.ghg_intensity_target
                
                # Tier system
                if ghg <= 0.45:  # 0.45 kg CO2e/kg H2
                    credit_45v = 3.0  # $3/kg (max credit)
                    tier = "Tier 4 (Best)"
                elif ghg <= 1.5:
                    credit_45v = 1.0  # $1/kg
                    tier = "Tier 3"
                elif ghg <= 2.5:
                    credit_45v = 0.75  # $0.75/kg
                    tier = "Tier 2"
                elif ghg <= 4.0:
                    credit_45v = 0.60  # $0.60/kg
                    tier = "Tier 1"
                else:
                    eligible_45v = False
                    reasons_45v.append(f"GHG intensity {ghg:.2f} exceeds 4.0 kg CO2e/kg maximum")
            
            if eligible_45v and credit_45v > 0:
                results["eligible_certifications"].append({
                    "name": "45V",
                    "status": "eligible",
                    "tier": tier,
                    "subsidy_value_eur_kg": credit_45v,  # Using EUR/kg for consistency
                    "annual_value": annual_production_kg * credit_45v,
                    "requirements_met": [
                        f"Hydrogen production in US",
                        f"GHG intensity {certification.ghg_intensity_target:.2f} qualifies for {tier}"
                    ]
                })
                results["subsidy_value"]["45V"] = credit_45v
                results["total_annual_subsidy"] += annual_production_kg * credit_45v
            else:
                results["ineligible_certifications"].append({
                    "name": "45V",
                    "status": "not_eligible",
                    "reasons": reasons_45v,
                    "how_to_qualify": [
                        "Produce in United States",
                        "Reduce GHG intensity to qualify for higher tiers",
                        "Target <0.45 kg CO2e/kg H2 for maximum $3/kg credit"
                    ]
                })
        
        # ====================================================================
        # RFNBO (Renewable Fuels of Non-Biological Origin - EU)
        # ====================================================================
        if "RFNBO" in certification.target_certifications:
            rfnbo_eligible = True
            rfnbo_reasons = []
            
            # Must use renewable electricity
            if certification.electricity_renewable_percentage < 95:
                rfnbo_eligible = False
                rfnbo_reasons.append(f"Renewable electricity {certification.electricity_renewable_percentage}% below 95% requirement")
            
            # Temporal and geographical correlation (simplified check)
            if economics.electricity_source not in ["renewable", "wind", "solar", "hydro"]:
                rfnbo_eligible = False
                rfnbo_reasons.append("Must use dedicated renewable electricity")
            
            if rfnbo_eligible:
                results["eligible_certifications"].append({
                    "name": "RFNBO",
                    "status": "eligible",
                    "subsidy_value_eur_kg": 0.3,  # Example value
                    "annual_value": annual_production_kg * 0.3,
                    "requirements_met": [
                        "Renewable electricity >= 95%",
                        "Dedicated renewable source",
                        "Temporal correlation with renewable generation"
                    ]
                })
                results["subsidy_value"]["RFNBO"] = 0.3
                results["total_annual_subsidy"] += annual_production_kg * 0.3
            else:
                results["ineligible_certifications"].append({
                    "name": "RFNBO",
                    "status": "not_eligible",
                    "reasons": rfnbo_reasons,
                    "how_to_qualify": [
                        "Use 100% renewable electricity",
                        "Install dedicated renewable generation (wind/solar)",
                        "Ensure temporal and geographical correlation"
                    ]
                })
        
        # ====================================================================
        # Summary
        # ====================================================================
        results["summary"] = {
            "total_eligible": len(results["eligible_certifications"]),
            "total_ineligible": len(results["ineligible_certifications"]),
            "annual_subsidy_value": results["total_annual_subsidy"],
            "subsidy_percentage_of_revenue": 0  # Calculated below
        }
        
        # Calculate subsidy as % of revenue
        annual_revenue = annual_production_kg * economics.target_offtake_price_eur_kg
        if annual_revenue > 0:
            results["summary"]["subsidy_percentage_of_revenue"] = (
                results["total_annual_subsidy"] / annual_revenue * 100
            )
        
        return results
        
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
