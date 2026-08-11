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
from app.core.fuel_catalog import find_fuel, load_fuel_catalog, offered_molecule_payload

router = APIRouter()

# Configuration
import os

from app.services.engine_auth import engine_auth_headers

# Env-var'd: a hardcoded localhost breaks inside Docker, where the engine is
# reachable as pf_engine:8001.
FINANCE_ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001") + "/api/v1/model"


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class Step1ProjectBasics(BaseModel):
    """Step 1: Basic project information"""
    molecule: str  # Product-facing catalogue values or legacy aliases
    capacity_mtpd: float
    location: str = ""
    country: str
    power_basis: Optional[str] = None      # off_grid | ppa | grid | hybrid — drives RFNBO status
    offtake_status: Optional[str] = None   # none | discussion | loi | binding — bankability anchor
    production_start_year: int
    production_end_year: int = 2042


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
            "e-Methane": {"active_rfqs": 7, "avg_price_eur_kg": 0.12, "demand_level": "medium", "trend": "increasing"},
            "e-Methanol": {"active_rfqs": 9, "avg_price_eur_kg": 0.80, "demand_level": "high", "trend": "increasing"},
            "e-NH3": {"active_rfqs": 8, "avg_price_eur_kg": 0.45, "demand_level": "medium", "trend": "stable"},
            "HVO": {"active_rfqs": 11, "avg_price_eur_kg": 1.80, "demand_level": "high", "trend": "stable"},
            "SAF": {"active_rfqs": 15, "avg_price_eur_kg": 2.10, "demand_level": "very_high", "trend": "increasing"},
            "e-Gasoline": {"active_rfqs": 6, "avg_price_eur_kg": 1.25, "demand_level": "medium", "trend": "increasing"},
            "e-LG": {"active_rfqs": 4, "avg_price_eur_kg": 0.15, "demand_level": "emerging", "trend": "increasing"},
            "e-Naphtha": {"active_rfqs": 5, "avg_price_eur_kg": 0.98, "demand_level": "medium", "trend": "stable"},
            "H2": {"active_rfqs": 12, "avg_price_eur_kg": 6.5, "demand_level": "high", "trend": "increasing"},
            "NH3": {"active_rfqs": 8, "avg_price_eur_kg": 0.45, "demand_level": "medium", "trend": "stable"},
            "CH3OH": {"active_rfqs": 5, "avg_price_eur_kg": 0.38, "demand_level": "medium", "trend": "stable"},
            "e-NG": {"active_rfqs": 7, "avg_price_eur_kg": 0.12, "demand_level": "medium", "trend": "increasing"},
        }
        
        fuel = find_fuel(project.molecule)
        molecule_key = fuel["id"] if fuel else project.molecule
        molecule_label = fuel["label"] if fuel else project.molecule
        # demand_signals is keyed by product label; find_fuel gives an id, so fall
        # back to the label and the raw input before defaulting to "unknown".
        molecule_demand = (
            demand_signals.get(molecule_key)
            or demand_signals.get(molecule_label)
            or demand_signals.get(project.molecule)
            or {"active_rfqs": 0, "avg_price_eur_kg": 0, "demand_level": "unknown", "trend": "unknown"}
        )
        
        # Regional demand factors
        regional_multiplier = 1.0
        if project.country in ["Germany", "Netherlands", "France"]:
            regional_multiplier = 1.3  # High EU demand
        elif project.country in ["United States", "Canada"]:
            regional_multiplier = 1.2  # High North America demand
        
        # Timeline feasibility
        years_to_production = project.production_start_year - datetime.now().year
        timeline_assessment = "aggressive" if years_to_production < 3 else "feasible" if years_to_production < 5 else "conservative"

        # ── Eligibility (jurisdiction + molecule) — uses the real EU exclusion screen ──
        EU_COUNTRIES = {"Germany", "France", "Italy", "Spain", "Netherlands", "Belgium", "Portugal",
                        "Denmark", "Sweden", "Finland", "Poland", "Austria", "Ireland", "Greece",
                        "Romania", "Czechia", "Other EU"}
        MOLECULE_NACE = {"e-Methanol": "20.14", "e-NH3": "20.15", "e-Naphtha": "20.14"}
        is_eu = project.country in EU_COUNTRIES
        nace = MOLECULE_NACE.get(molecule_key) or MOLECULE_NACE.get(project.molecule)
        if is_eu and nace:
            try:
                from app.api.v1 import eligibility_policy as elig
                screen = elig.screen_nace(nace)
            except Exception:
                screen = {"excluded": True, "carveout_available": True}
            eligibility = {
                "jurisdiction": "EU — RED III / EU Taxonomy",
                "nace": nace,
                "restricted_sector": bool(screen.get("excluded")),
                "carve_out_available": screen.get("carveout_available"),
                "note": (f"{molecule_label} is on the EU restricted-sector list (NACE {nace}); EU public / "
                         "concessional capital is available only via the EU-Taxonomy carve-out. GEX screens exactly this.")
                        if screen.get("excluded") else "Not on the EU restricted-sector list.",
            }
        elif is_eu:
            eligibility = {"jurisdiction": "EU — RED III / EU Taxonomy", "restricted_sector": False,
                           "note": "RFNBO eligibility runs through RED III; GEX grades the evidence behind each claim."}
        else:
            eligibility = {"jurisdiction": f"{project.country or 'Not stated'} — mapped by GEX",
                           "note": "GEX maps the applicable renewable-fuel regime and the evidence a lender needs."}

        # ── Power basis → RFNBO strength ──
        POWER_RFNBO = {
            "off_grid": ("strong", "Dedicated off-grid renewables — additionality is clean; grid-connection gates drop away."),
            "ppa": ("conditional", "A PPA supports additionality, but RED III temporal (hourly from 2030) and geographic correlation still apply."),
            "grid": ("hard", "Grid power needs cancelled guarantees of origin plus temporal / geographic correlation to count as renewable."),
            "hybrid": ("mixed", "Hybrid supply — correlation is evidenced per source."),
        }
        pb = (project.power_basis or "").strip()
        rfnbo_strength, power_note = POWER_RFNBO.get(pb, ("not_stated", "Add a power basis to see the RFNBO read."))

        # ── Offtake status → bankability signal ──
        OFFTAKE_SIGNAL = {
            "none": ("unsecured", "Offtake is the bankability anchor — lenders size debt off contracted volume, tenor and buyer credit."),
            "discussion": ("early", "Early interest is directional, not bankable."),
            "loi": ("conditional", "An LOI / term sheet is progress but conditional on CPs."),
            "binding": ("secured", "A binding offtake is a strong bankability signal — GEX grades the buyer’s credit and CPs."),
        }
        ost = (project.offtake_status or "").strip()
        offtake_state, offtake_note = OFFTAKE_SIGNAL.get(ost, ("not_stated", "Add offtake status to see the bankability read."))

        return {
            "molecule": molecule_label,
            "market_demand": {
                "level": molecule_demand["demand_level"],
                "active_buyers": molecule_demand["active_rfqs"],
                "market_price_eur_kg": molecule_demand["avg_price_eur_kg"],
                "trend": molecule_demand["trend"],
                "regional_strength": regional_multiplier,
                "assessment": "Strong demand" if regional_multiplier > 1.1 else "Moderate demand"
            },
            "eligibility": eligibility,
            "power_basis": {"value": pb or "not_stated", "rfnbo_strength": rfnbo_strength, "note": power_note},
            "offtake": {"value": ost or "not_stated", "status": offtake_state, "note": offtake_note},
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
            "next_step_recommendation": "Indicative only — a first read, not a viability verdict. Next: economics, then how GEX turns these answers into evidence-graded gates."
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
        annual_production_kg = basics.capacity_mtpd * 1000 * 365  # MTPD (tonnes/day) → kg
        
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
                headers=engine_auth_headers(),
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
        annual_production_kg = basics.capacity_mtpd * 1000 * 365  # MTPD (tonnes/day) → kg
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
        
        # ── Orientation signal (0-100) ────────────────────────────────────────
        # A LIGHT, prospect-facing directional read, built transparently from the
        # SAME decisive reads the report leads with — eligibility, offtake, RFNBO
        # power and market demand — so the number and the coaching always agree.
        # It deliberately does NOT hinge on the finance engine's DSCR or the RED III
        # twin (H2-only today); those are the internal, evidence-graded grade that
        # lives behind the login. Orientation ≠ internal grade — by design.
        elig = demand_check.get("eligibility", {}) or {}
        offt = demand_check.get("offtake", {}) or {}
        powr = demand_check.get("power_basis", {}) or {}
        demand_level = (demand_check.get("market_demand", {}) or {}).get("level")
        # dscr is read (safely) only to tailor the next-steps below, not to score.
        dscr = (bankability_check.get("financial_metrics", {}) or {}).get("dscr", 0)

        score = 0
        # Eligibility / jurisdiction clarity (max 25) — a clear regulatory path.
        if elig.get("restricted_sector"):
            score += 18 if elig.get("carve_out_available") else 6
        elif elig.get("jurisdiction") and "not stated" not in str(elig.get("jurisdiction", "")).lower():
            score += 25
        else:
            score += 8
        # Offtake — the single biggest bankability lever (max 30).
        score += {"secured": 30, "conditional": 20, "early": 10, "unsecured": 4}.get(offt.get("status"), 4)
        # RFNBO power basis (max 25).
        score += {"strong": 25, "conditional": 16, "mixed": 14, "hard": 8}.get(powr.get("rfnbo_strength"), 4)
        # Market demand for the molecule/region (max 20).
        score += {"very_high": 20, "high": 16, "medium": 11, "emerging": 7}.get(demand_level, 6)

        score = max(0, min(round(score), 100))

        # Coaching, not a verdict — where you stand AND the next move.
        if score >= 80:
            viability = "on_track"
            recommendation = "You're most of the way there on paper. Prove the eligibility, power and offtake evidence and this becomes a lender-ready story — GEX takes you gate by gate."
        elif score >= 60:
            viability = "promising"
            recommendation = "Good momentum — a couple of decisive tests still need evidence. Clear those and you're in bankable territory. GEX shows exactly which, and grades each as you go."
        elif score >= 40:
            viability = "shaping_up"
            recommendation = "You're taking shape. A few decisive tests are unproven or at risk — the good news is each has a clear next move, and GEX walks you through them."
        else:
            viability = "early"
            recommendation = "Early days — and that's fine. GEX turns 'I have an idea' into 'here's what to prove first', one gate at a time. Start with the moves below."
        
        # Generate report
        report = {
            "generated_at": datetime.now().isoformat(),
            "viability_score": score,
            "viability_level": viability,
            "recommendation": recommendation,

            # The decisive reads — what the report leads with (from Step 1 answers)
            "readiness": {
                "eligibility": demand_check.get("eligibility"),
                "rfnbo_power": demand_check.get("power_basis"),
                "offtake": demand_check.get("offtake"),
                "note": "Indicative orientation — GEX turns each of these into an evidence-graded gate. Not a verdict, not credit-approved.",
            },

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
    return {"molecules": offered_molecule_payload()}


@router.get("/reference-data/fuels")
async def get_fuel_catalog():
    """Get the full canonical fuel catalogue with measures and aliases."""
    return load_fuel_catalog()


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
