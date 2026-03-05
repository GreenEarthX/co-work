"""
Decision Twin - Certification Rules Engine
The competitive moat of GreenEarthX

Determines certification eligibility with:
- Deterministic rule-based logic
- Complete explainability
- Event-driven audit trail
- Multiple certification schemes (RED III, 45V, RFNBO, CORSIA)
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import json


class CertificationScheme(Enum):
    """Supported certification schemes"""
    RED_III = "RED_III"
    RFNBO = "RFNBO"
    FORTY_FIVE_V = "45V"
    CORSIA = "CORSIA"
    LCFS = "LCFS"
    RTFO = "RTFO"


class EligibilityStatus(Enum):
    """Certification eligibility status"""
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    CONDITIONAL = "conditional"
    PENDING_DATA = "pending_data"


class Molecule(Enum):
    """Supported molecules"""
    H2 = "H2"
    NH3 = "NH3"
    CH3OH = "CH3OH"
    SAF = "SAF"
    HVO = "HVO"
    RENEWABLE_DIESEL = "RD"


# ============================================================================
# CERTIFICATION KNOWLEDGE BASE
# ============================================================================

class CertificationKnowledgeBase:
    """
    Knowledge base containing all certification rules
    This is the COMPETITIVE MOAT - accumulated domain expertise
    """
    
    @staticmethod
    def get_red_iii_rules() -> Dict:
        """RED III (Renewable Energy Directive III) - EU"""
        return {
            "scheme": "RED_III",
            "jurisdiction": "European Union",
            "version": "2023",
            "effective_date": "2024-01-01",
            
            "eligibility_criteria": {
                "ghg_intensity": {
                    "description": "GHG emissions savings vs fossil comparator",
                    "rules": [
                        {
                            "name": "GHG Savings Requirement",
                            "requirement": ">=70% emissions savings vs fossil comparator",
                            "threshold": 0.70,
                            "mandatory": True
                        }
                    ],
                    "fossil_comparators": {
                        "H2": 94.0,
                        "NH3": 2.6,
                        "SAF": 3.0,
                        "CH3OH": 0.69,
                        "HVO": 3.1,
                    }
                },
                
                "renewable_electricity": {
                    "description": "Renewable electricity criteria",
                    "rules": [
                        {
                            "name": "Renewable Share",
                            "requirement": ">=90% renewable electricity",
                            "threshold": 0.90,
                            "mandatory": True
                        },
                        {
                            "name": "Temporal Correlation",
                            "requirement": "Hourly matching from 2030",
                            "mandatory": False,
                            "phase_in": "2030-01-01"
                        },
                        {
                            "name": "Geographical Correlation",
                            "requirement": "Same bidding zone",
                            "mandatory": True
                        }
                    ]
                }
            },
            
            "subsidy_value": {
                "amount_eur_kg": 0.5,
                "notes": "Varies by member state"
            }
        }
    
    @staticmethod
    def get_45v_rules() -> Dict:
        """45V Clean Hydrogen Production Tax Credit - US"""
        return {
            "scheme": "45V",
            "jurisdiction": "United States",
            "version": "IRA 2022",
            "effective_date": "2023-01-01",
            "expires": "2032-12-31",
            
            "eligibility_criteria": {
                "molecule_restriction": {
                    "allowed_molecules": ["H2"],
                    "mandatory": True
                },
                
                "ghg_intensity_tiers": {
                    "tiers": [
                        {
                            "tier": 4,
                            "name": "Best",
                            "ghg_max": 0.45,
                            "credit_usd_kg": 3.00
                        },
                        {
                            "tier": 3,
                            "name": "Good",
                            "ghg_min": 0.45,
                            "ghg_max": 1.5,
                            "credit_usd_kg": 1.00
                        },
                        {
                            "tier": 2,
                            "name": "Medium",
                            "ghg_min": 1.5,
                            "ghg_max": 2.5,
                            "credit_usd_kg": 0.75
                        },
                        {
                            "tier": 1,
                            "name": "Basic",
                            "ghg_min": 2.5,
                            "ghg_max": 4.0,
                            "credit_usd_kg": 0.60
                        }
                    ]
                },
                
                "additionality": {
                    "rules": [
                        {
                            "name": "Incremental/New",
                            "requirement": "Electricity source <36 months old",
                            "mandatory": True
                        },
                        {
                            "name": "Temporal Matching",
                            "requirement": "Hourly matching by 2032"
                        },
                        {
                            "name": "Regional Deliverability",
                            "requirement": "Same ISO/RTO"
                        }
                    ]
                },
                
                "prevailing_wage": {
                    "requirement": "Davis-Bacon wages",
                    "impact": "Without: 20% of credit"
                }
            }
        }
    
    @staticmethod
    def get_rfnbo_rules() -> Dict:
        """RFNBO - EU Synthetic Fuels"""
        return {
            "scheme": "RFNBO",
            "jurisdiction": "European Union",
            "version": "Delegated Act 2023",
            
            "eligibility_criteria": {
                "renewable_electricity": {
                    "rules": [
                        {
                            "name": "Additionality",
                            "requirement": "New capacity <36 months",
                            "mandatory": True
                        },
                        {
                            "name": "Temporal Correlation",
                            "requirement": "Hourly matching from 2030",
                            "mandatory": True
                        }
                    ]
                }
            },
            
            "value_proposition": {
                "multiplier": 1.2,
                "estimated_premium_eur_kg": 0.3
            }
        }
    
    @staticmethod
    def get_corsia_rules() -> Dict:
        """CORSIA - Aviation Carbon Offsetting"""
        return {
            "scheme": "CORSIA",
            "jurisdiction": "International (ICAO)",
            
            "eligibility_criteria": {
                "ghg_reduction": {
                    "requirement": ">=10% reduction",
                    "threshold": 0.10,
                    "baseline": 89.0
                }
            },
            
            "market_value": {
                "typical_premium_pct": 150,
                "estimated_premium_eur_l": 0.8
            }
        }


# ============================================================================
# DECISION TWIN ENGINE
# ============================================================================

class DecisionTwin:
    """
    Main Decision Twin engine
    Evaluates projects against certification schemes
    """
    
    def __init__(self, project_id: str = None, correlation_id: str = None):
        self.project_id = project_id
        self.correlation_id = correlation_id or f"DT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.kb = CertificationKnowledgeBase()
    
    def evaluate_red_iii(
        self,
        molecule: str,
        ghg_intensity: float,
        renewable_electricity_pct: float,
        temporal_matching: str = "monthly",
        geographical_correlation: bool = True,
        additional_data: Dict = None
    ) -> Dict:
        """Evaluate RED III eligibility"""
        rules = self.kb.get_red_iii_rules()
        
        result = {
            "scheme": "RED_III",
            "status": EligibilityStatus.ELIGIBLE.value,
            "timestamp": datetime.now().isoformat(),
            "correlation_id": self.correlation_id,
            "checks": [],
            "failures": [],
            "warnings": [],
            "recommendations": [],
            "subsidy_value": None
        }
        
        # Check 1: GHG Intensity
        fossil_comparator = rules["eligibility_criteria"]["ghg_intensity"]["fossil_comparators"].get(molecule)
        if not fossil_comparator:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "Molecule Support",
                "reason": f"Molecule {molecule} not supported",
                "severity": "critical"
            })
            return result
        
        ghg_savings = (fossil_comparator - ghg_intensity) / fossil_comparator
        ghg_required = 0.70
        
        ghg_check = {
            "check": "GHG Savings",
            "required": f">={ghg_required * 100}%",
            "actual": f"{ghg_savings * 100:.1f}%",
            "passed": ghg_savings >= ghg_required,
            "details": {
                "fossil_comparator": fossil_comparator,
                "actual_ghg": ghg_intensity,
                "savings_percentage": ghg_savings * 100
            }
        }
        result["checks"].append(ghg_check)
        
        if not ghg_check["passed"]:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "GHG Savings",
                "reason": f"Only {ghg_savings*100:.1f}% savings (need >=70%)",
                "severity": "critical",
                "gap": f"Reduce GHG by {ghg_intensity - (fossil_comparator * 0.30):.2f} kg CO2e/kg"
            })
        
        # Check 2: Renewable Electricity
        renewable_required = 90
        renewable_check = {
            "check": "Renewable Electricity",
            "required": f">={renewable_required}%",
            "actual": f"{renewable_electricity_pct}%",
            "passed": renewable_electricity_pct >= renewable_required
        }
        result["checks"].append(renewable_check)
        
        if not renewable_check["passed"]:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "Renewable Electricity",
                "reason": f"Only {renewable_electricity_pct}% renewable",
                "severity": "critical",
                "gap": f"Need {renewable_required - renewable_electricity_pct}% more"
            })
        
        # Check 3: Geographical Correlation
        geo_check = {
            "check": "Geographical Correlation",
            "required": "Same bidding zone",
            "actual": "Same zone" if geographical_correlation else "Different",
            "passed": geographical_correlation
        }
        result["checks"].append(geo_check)
        
        if not geo_check["passed"]:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "Geographical Correlation",
                "reason": "Not from same bidding zone",
                "severity": "critical"
            })
        
        # Check 4: Temporal Matching
        temporal_check = {
            "check": "Temporal Matching",
            "required": "Hourly (from 2030)",
            "actual": temporal_matching,
            "passed": True
        }
        result["checks"].append(temporal_check)
        
        if temporal_matching not in ["hourly", "monthly"]:
            result["warnings"].append({
                "check": "Temporal Matching",
                "message": "Annual matching not acceptable from 2030",
                "severity": "medium"
            })
        
        # Final determination
        if result["status"] == EligibilityStatus.ELIGIBLE.value:
            result["subsidy_value"] = {
                "amount_eur_kg": rules["subsidy_value"]["amount_eur_kg"],
                "notes": rules["subsidy_value"]["notes"]
            }
            result["summary"] = f"✅ Eligible for RED III with {ghg_savings*100:.1f}% GHG savings"
        else:
            result["summary"] = f"❌ Not eligible. {len(result['failures'])} failures."
            
            if any(f["check"] == "GHG Savings" for f in result["failures"]):
                result["recommendations"].append({
                    "action": "Reduce GHG Intensity",
                    "options": [
                        "Use 100% renewable electricity",
                        "Optimize electrolysis efficiency",
                        "Reduce upstream emissions"
                    ]
                })
        
        return result
    
    def evaluate_45v(
        self,
        molecule: str,
        ghg_intensity: float,
        electricity_source: str,
        electricity_age_months: int,
        temporal_matching: str = "annual",
        region: str = "US",
        prevailing_wage_compliance: bool = False
    ) -> Dict:
        """Evaluate 45V eligibility"""
        rules = self.kb.get_45v_rules()
        
        result = {
            "scheme": "45V",
            "status": EligibilityStatus.ELIGIBLE.value,
            "timestamp": datetime.now().isoformat(),
            "correlation_id": self.correlation_id,
            "checks": [],
            "failures": [],
            "warnings": [],
            "tier": None,
            "credit_value": None
        }
        
        # Check 1: Molecule
        if molecule != "H2":
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "Molecule",
                "reason": "45V only for hydrogen",
                "severity": "critical"
            })
            return result
        
        # Check 2: Jurisdiction
        if region not in ["US", "USA", "United States"]:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "Jurisdiction",
                "reason": "45V only in United States",
                "severity": "critical"
            })
            return result
        
        # Check 3: Tier
        tier_info = None
        for tier in rules["eligibility_criteria"]["ghg_intensity_tiers"]["tiers"]:
            if ghg_intensity <= tier["ghg_max"]:
                tier_info = tier
                break
        
        if not tier_info:
            result["status"] = EligibilityStatus.INELIGIBLE.value
            result["failures"].append({
                "check": "GHG Intensity",
                "reason": f"GHG {ghg_intensity:.2f} exceeds max 4.0",
                "severity": "critical"
            })
            return result
        
        result["tier"] = tier_info["tier"]
        base_credit = tier_info["credit_usd_kg"]
        
        result["checks"].append({
            "check": "GHG Tier",
            "tier": tier_info["tier"],
            "ghg_intensity": ghg_intensity,
            "base_credit": f"${base_credit}/kg",
            "passed": True
        })
        
        # Check 4: Additionality
        new_source = electricity_age_months <= 36
        result["checks"].append({
            "check": "Additionality",
            "required": "<36 months",
            "actual": f"{electricity_age_months} months",
            "passed": new_source
        })
        
        # Check 5: Prevailing Wage
        wage_multiplier = 1.0 if prevailing_wage_compliance else 0.2
        
        result["checks"].append({
            "check": "Prevailing Wage",
            "compliant": prevailing_wage_compliance,
            "multiplier": f"{wage_multiplier}x",
            "passed": True
        })
        
        if not prevailing_wage_compliance:
            result["warnings"].append({
                "check": "Prevailing Wage",
                "message": f"Credit reduced to ${base_credit * wage_multiplier:.2f}/kg (20%)",
                "severity": "critical"
            })
        
        final_credit = base_credit * wage_multiplier
        
        result["credit_value"] = {
            "base_credit_usd_kg": base_credit,
            "wage_multiplier": wage_multiplier,
            "final_credit_usd_kg": final_credit
        }
        
        result["summary"] = f"✅ Eligible for 45V Tier {tier_info['tier']} (${final_credit:.2f}/kg)"
        
        return result
    
    def evaluate_all_schemes(self, project_data: Dict) -> Dict:
        """Evaluate against all relevant schemes"""
        results = {
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "timestamp": datetime.now().isoformat(),
            "schemes_evaluated": [],
            "eligible_schemes": [],
            "ineligible_schemes": [],
            "total_subsidy_value": 0,
            "recommendations": []
        }
        
        molecule = project_data.get("molecule")
        country = project_data.get("country")
        
        # EU countries
        eu_countries = ["Germany", "France", "Netherlands", "Spain", "Italy", 
                       "Belgium", "Austria", "Denmark", "Sweden", "Finland", "Poland"]
        
        # RED III
        if country in eu_countries:
            red_iii = self.evaluate_red_iii(
                molecule=molecule,
                ghg_intensity=project_data.get("ghg_intensity", 0.45),
                renewable_electricity_pct=project_data.get("renewable_electricity_pct", 100),
                temporal_matching=project_data.get("temporal_matching", "monthly"),
                geographical_correlation=project_data.get("geographical_correlation", True)
            )
            results["schemes_evaluated"].append("RED_III")
            
            if red_iii["status"] == EligibilityStatus.ELIGIBLE.value:
                results["eligible_schemes"].append("RED_III")
                if red_iii.get("subsidy_value"):
                    results["total_subsidy_value"] += red_iii["subsidy_value"]["amount_eur_kg"]
            
            results["RED_III"] = red_iii
        
        # 45V
        if country in ["United States", "USA", "US"] and molecule == "H2":
            v45 = self.evaluate_45v(
                molecule=molecule,
                ghg_intensity=project_data.get("ghg_intensity", 0.45),
                electricity_source=project_data.get("electricity_source", "renewable"),
                electricity_age_months=project_data.get("electricity_age_months", 12),
                prevailing_wage_compliance=project_data.get("prevailing_wage", False)
            )
            results["schemes_evaluated"].append("45V")
            
            if v45["status"] == EligibilityStatus.ELIGIBLE.value:
                results["eligible_schemes"].append("45V")
                if v45.get("credit_value"):
                    results["total_subsidy_value"] += v45["credit_value"]["final_credit_usd_kg"]
            
            results["45V"] = v45
        
        return results


if __name__ == "__main__":
    # Test
    twin = DecisionTwin(project_id="test-1")
    
    result = twin.evaluate_red_iii(
        molecule="H2",
        ghg_intensity=0.35,
        renewable_electricity_pct=100,
        temporal_matching="monthly",
        geographical_correlation=True
    )
    
    print(json.dumps(result, indent=2))
