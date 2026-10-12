"""
GEX Bankability Orchestration Engine
=====================================
Integrates into gex_pf_engine as a core service module.
Called by gex-platform-enhanced via HTTP bridge (port 8001).

Responsibilities:
  - Evaluate gate completion from evidence status
  - Compute project bankability state (forward transitions)
  - Detect and enforce regression rules
  - Scope gate/evidence visibility per stakeholder persona
  - Emit events for the event store (audit trail)

Architecture:
  gex-platform-enhanced (8000)
    └─ services/bankability_client.py  ──HTTP──►  gex_pf_engine (8001)
                                                    └─ core/bankability_engine.py  ← THIS FILE
                                                    └─ api/routes_bankability.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# R2: Import verification weights — gate scores are weighted by evidence state
from app.core.verification import VerificationState, VERIFICATION_WEIGHTS


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class BankabilityState(str, Enum):
    SPECULATIVE = "SPECULATIVE"
    TECHNICALLY_PLAUSIBLE = "TECHNICALLY_PLAUSIBLE"
    COMMERCIALLY_PLAUSIBLE = "COMMERCIALLY_PLAUSIBLE"
    BUILDABLE = "BUILDABLE"
    STRUCTURALLY_BANKABLE = "STRUCTURALLY_BANKABLE"
    CREDIT_APPROVED = "CREDIT_APPROVED"
    FINANCEABLE = "FINANCEABLE"
    OPERATIONAL = "OPERATIONAL"
    REFINANCING_ELIGIBLE = "REFINANCING_ELIGIBLE"


STATE_ORDER = list(BankabilityState)


class Department(str, Enum):
    ENGINEERING = "ENGINEERING"
    PROJECT = "PROJECT"
    SALES = "SALES"
    FINANCE = "FINANCE"
    TREASURY = "TREASURY"
    LEGAL = "LEGAL"
    INDEPENDENT_ENGINEER = "INDEPENDENT_ENGINEER"
    LENDERS = "LENDERS"


class CapitalType(str, Enum):
    GRANTS_TA = "GRANTS_TA"
    SEED_VC_ANGEL = "SEED_VC_ANGEL"
    STRATEGIC_EQUITY = "STRATEGIC_EQUITY"
    PROJECT_EQUITY = "PROJECT_EQUITY"
    DFI_MEZZ_GUARANTEES = "DFI_MEZZ_GUARANTEES"
    SENIOR_DEBT_COMMITMENT = "SENIOR_DEBT_COMMITMENT"
    DEBT_DRAWDOWN = "DEBT_DRAWDOWN"
    REFINANCE_BONDS_INFRA = "REFINANCE_BONDS_INFRA"


# Display labels, held identical to the engine's CAPITAL_TYPE_LABELS by
# tests/test_gate_registries_agree.py. Identifiers stay stable; since rules 4.1.0
# SENIOR_DEBT_COMMITMENT reads as what it is — a conditional credit approval.
CAPITAL_TYPE_LABELS: dict[str, str] = {
    "GRANTS_TA": "Grants & TA",
    "SEED_VC_ANGEL": "Seed / VC / Angel",
    "STRATEGIC_EQUITY": "Strategic Equity",
    "PROJECT_EQUITY": "Project Equity",
    "DFI_MEZZ_GUARANTEES": "DFI / Mezz / Guarantees",
    "SENIOR_DEBT_COMMITMENT": "Senior Debt Credit Approval (conditional)",
    "DEBT_DRAWDOWN": "Debt Drawdown",
    "REFINANCE_BONDS_INFRA": "Refinance / Bonds / Infra",
}


# ═══════════════════════════════════════════════════════════════════════════════
# STAKEHOLDER PERSONA DEFINITIONS
# Maps each platform workspace/view to the departments + gates it can see.
# The frontend in gex-platform-enhanced passes persona on every API call.
# ═══════════════════════════════════════════════════════════════════════════════

class StakeholderPersona(str, Enum):
    """
    These map 1:1 to workspace types in gex-platform-enhanced.
    Each persona gets a filtered view of gates + evidence.
    """
    PRODUCER = "PRODUCER"           # Production management, construction gates
    FINANCE = "FINANCE"             # Risk, milestones, covenants, model
    REGULATOR = "REGULATOR"         # Verification, audit, IE sign-off
    OFFTAKER = "OFFTAKER"           # The buyer: certification, offtake, EPC, permits, FID, delivery (4.0.0)
    EXECUTIVE = "EXECUTIVE"         # Strategic KPIs, full progression visibility


# Which departments each persona has visibility into
PERSONA_DEPARTMENTS: dict[StakeholderPersona, set[Department]] = {
    StakeholderPersona.PRODUCER: {
        Department.ENGINEERING, Department.PROJECT,
    },
    StakeholderPersona.FINANCE: {
        Department.FINANCE, Department.TREASURY, Department.LENDERS,
    },
    StakeholderPersona.REGULATOR: {
        Department.INDEPENDENT_ENGINEER, Department.LENDERS,
        Department.LEGAL,
    },
    # 4.0.0 — the buyer reads commercial, legal and engineering evidence: the
    # contract it signs, the plant's ability to deliver it, and the certificate.
    StakeholderPersona.OFFTAKER: {
        Department.SALES, Department.LEGAL, Department.ENGINEERING,
    },
    StakeholderPersona.EXECUTIVE: set(Department),  # sees everything
}

# PERSONA_GATES is derived from each gate's own `personas`, exactly as in the
# runtime engine — defined after GATE_REGISTRY below. (The hand-written copy
# that lived here gave REGULATOR a gate the runtime did not.)


# ═══════════════════════════════════════════════════════════════════════════════
# GATE DEFINITIONS (from gates JSON)
# ═══════════════════════════════════════════════════════════════════════════════

class GateDefinition(BaseModel):
    id: str
    name: str
    required_evidence: list[str]
    # Two distinct ownership axes, identical to the runtime registry in
    # gex_pf_engine/backend/pf_engine/core/bankability_engine.py.
    #   owners / accountable_functions = who DOES the work (org function)
    #   personas                       = who SEES the gate (platform visibility)
    # They were previously one field meaning different things in each registry,
    # which is why the two disagreed on every gate.
    owners: list[Department]
    personas: list[str] = []
    unlocks_capital: list[CapitalType]
    unlocks_state: Optional[BankabilityState] = None

    @property
    def accountable_functions(self) -> list[str]:
        return [o.value for o in self.owners]


# Generated from the runtime engine's GATES
# (gex_pf_engine/backend/pf_engine/core/bankability_engine.py, rules 4.0.0)
# and held identical to it by tests/test_gate_registries_agree.py. Edit both, or
# the build fails. The reasoning for each gate's evidence lives beside the
# runtime definition, not here.
GATE_REGISTRY: list[GateDefinition] = [
    GateDefinition(
        id="G0_SITE_RIGHTS", name="Site Rights & Social License",
        required_evidence=[
            "land_option_or_lease_executed",
            "zoning_compatibility_memo",
            "stakeholder_map_v1",
            "site_technical_suitability",
        ],
        owners=[Department.PROJECT, Department.LEGAL],
        personas=["PRODUCER", "EXECUTIVE"],
        unlocks_capital=[CapitalType.GRANTS_TA],
        unlocks_state=BankabilityState.TECHNICALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G1_GRID_UTILITIES_REALITY", name="Power, Utilities & Technology Basis",
        required_evidence=[
            "grid_interconnection_study",
            "queue_position_evidence",
            "grid_connection_cost_estimate",
            "connection_date_cod_compatibility_memo",
            "ppa_register",
            "ppa_signed_or_term_sheet_evidence",
            "ppa_volume_load_coverage_analysis",
            "ppa_tenor_debt_comparison",
            "curtailment_assessment",
            "dispatch_load_factor_production_impact",
            "water_source_plan",
            "water_permit_pathway_memo",
            "btm_generation_asset_evidence",
            "generation_yield_study",
            "grid_independence_note",
            "backup_construction_power_plan",
            "technology_maturity_dossier",
            "technology_licensor_term_sheet",
            "integrated_mass_energy_balance",
        ],
        owners=[Department.ENGINEERING, Department.PROJECT, Department.FINANCE],
        personas=["PRODUCER"],
        unlocks_capital=[CapitalType.SEED_VC_ANGEL],
        unlocks_state=BankabilityState.TECHNICALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G2_CERTIFICATION_PATH_LOCKED", name="Green Certification Pathway",
        required_evidence=[
            "certification_scheme_selection",
            "additionality_evidence",
            "power_sourcing_alignment_note",
            "ghg_methodology_memo",
            "mrv_plan_v1",
            "product_qualification_pathway",
        ],
        owners=[Department.ENGINEERING, Department.LEGAL],
        personas=["REGULATOR", "OFFTAKER"],
        unlocks_capital=[],
        unlocks_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G3_INPUTS_SECURED", name="Feedstock & Logistics Terms",
        required_evidence=[
            "feedstock_supply_agreement",
            "transport_logistics_study",
            "storage_plan",
            "feedstock_spec_eligibility",
        ],
        owners=[Department.ENGINEERING, Department.PROJECT, Department.FINANCE],
        personas=["PRODUCER"],
        unlocks_capital=[CapitalType.STRATEGIC_EQUITY],
        unlocks_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G4_OFFTAKE_BANKABLE", name="Binding Offtake",
        required_evidence=[
            "binding_offtake_contract_executed",
            "offtake_credit_assessment",
            "credit_support_package",
            "take_or_pay_floor",
            "termination_payment_formula",
            "assignment_rights",
            "step_in_rights",
            "hedgeable_pricing_index",
            "price_review_mechanism_memo",
            "offtake_seller_obligations",
        ],
        owners=[Department.SALES, Department.LEGAL, Department.FINANCE],
        personas=["FINANCE", "OFFTAKER"],
        unlocks_capital=[CapitalType.PROJECT_EQUITY],
        unlocks_state=BankabilityState.BUILDABLE,
    ),
    GateDefinition(
        id="G5_EPC_RISK_PRICED", name="EPC Risk Priced",
        required_evidence=[
            "epc_contract_fixed_price_or_capped_gmp",
            "liquidated_damages_schedule",
            "date_certain_schedule",
            "performance_test_protocol",
            "interface_matrix",
            "oem_warranties",
            "epc_contractor_dd",
            "feed_complete_class3",
            "technology_licence_process_guarantee",
            "long_lead_items_reserved",
            "epc_security_package",
            "independent_technical_review",
        ],
        owners=[Department.PROJECT, Department.ENGINEERING, Department.LEGAL],
        personas=["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        unlocks_capital=[],
        unlocks_state=BankabilityState.BUILDABLE,
    ),
    GateDefinition(
        id="G6_IE_SIGNOFF", name="Independent Engineer Sign-off",
        required_evidence=[
            "ie_report_issued",
            "energy_balance_verified",
            "capex_opinion_reasonableness",
            "opex_opinion_reasonableness",
            "completion_test_definitions",
        ],
        owners=[Department.INDEPENDENT_ENGINEER, Department.LENDERS],
        personas=["FINANCE", "REGULATOR"],
        unlocks_capital=[CapitalType.DFI_MEZZ_GUARANTEES],
        unlocks_state=BankabilityState.STRUCTURALLY_BANKABLE,
    ),
    GateDefinition(
        id="G7_INSURANCE_BOUND", name="Insurability Confirmed",
        required_evidence=[
            "insurance_term_sheet",
            "insurance_market_report",
            "deductibles_accepted",
            "exclusions_register_reviewed",
            "foak_exclusions_warranty_backstop",
        ],
        owners=[Department.TREASURY, Department.LEGAL, Department.LENDERS],
        personas=["FINANCE"],
        unlocks_capital=[],
        unlocks_state=BankabilityState.STRUCTURALLY_BANKABLE,
    ),
    GateDefinition(
        id="G8_AUDIT_GRADE_MODEL", name="Audit-Grade Financial Model",
        required_evidence=[
            "base_case_model",
            "model_audit_opinion",
            "downside_cases",
            "covenant_suite_defined",
            "dsra_maintenance_reserve_logic",
            "hedging_plan",
            "model_consistency_with_ie",
        ],
        owners=[Department.FINANCE, Department.LENDERS],
        personas=["FINANCE"],
        unlocks_capital=[CapitalType.SENIOR_DEBT_COMMITMENT],
        unlocks_state=BankabilityState.CREDIT_APPROVED,
    ),
    GateDefinition(
        id="G9_PERMITS_SAFE", name="Permits Granted & Appeal Risk Managed",
        required_evidence=[
            "eia_permit_granted",
            "construction_permit_granted",
            "ancillary_permits_granted",
            "legal_opinion_on_appeal_risk",
            "operating_permit_pathway",
            "stakeholder_management_plan_v2",
        ],
        owners=[Department.PROJECT, Department.LEGAL],
        personas=["PRODUCER", "REGULATOR", "OFFTAKER"],
        unlocks_capital=[],
        unlocks_state=BankabilityState.FINANCEABLE,
    ),
    GateDefinition(
        id="G10_FINANCIAL_CLOSE_CP", name="Financial Close",
        required_evidence=[
            "cp_checklist_completed",
            "equity_injected",
            "dsra_funded",
            "security_package_perfected",
            "insurance_certificates_delivered",
            "all_major_contracts_executed",
            "legal_opinions_issued",
            "om_contract_or_organisation",
        ],
        owners=[Department.LENDERS, Department.LEGAL, Department.TREASURY, Department.FINANCE],
        personas=["FINANCE", "OFFTAKER"],
        unlocks_capital=[CapitalType.DEBT_DRAWDOWN],
        unlocks_state=BankabilityState.FINANCEABLE,
    ),
    GateDefinition(
        id="G11_COD_STABILIZATION", name="COD & Stabilization",
        required_evidence=[
            "cod_certificate",
            "performance_tests_passed",
            "operating_permit_effective",
            "mrv_reporting_live",
            "six_to_twelve_months_stable_ops",
            "certificates_issued",
            "first_deliveries_accepted",
        ],
        owners=[Department.PROJECT, Department.ENGINEERING, Department.FINANCE],
        personas=["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        unlocks_capital=[CapitalType.REFINANCE_BONDS_INFRA],
        unlocks_state=BankabilityState.OPERATIONAL,
    ),
]

GATE_INDEX: dict[str, GateDefinition] = {g.id: g for g in GATE_REGISTRY}

# Which gates each persona sees — derived, never hand-kept. EXECUTIVE keeps the
# historic "empty = all gates" convention of this module.
PERSONA_GATES: dict[StakeholderPersona, list[str]] = {
    p: [g.id for g in GATE_REGISTRY if p.value in g.personas]
    for p in StakeholderPersona if p != StakeholderPersona.EXECUTIVE
}
PERSONA_GATES[StakeholderPersona.EXECUTIVE] = []  # empty = all gates


# ═══════════════════════════════════════════════════════════════════════════════
# STATE TRANSITION RULES (from state_rules JSON)
# ═══════════════════════════════════════════════════════════════════════════════

class StateTransitionRule(BaseModel):
    to_state: BankabilityState
    requires_all_gates: list[str]


STATE_RULES: list[StateTransitionRule] = [
    StateTransitionRule(to_state=BankabilityState.TECHNICALLY_PLAUSIBLE,
                        requires_all_gates=["G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY", "G2_CERTIFICATION_PATH_LOCKED", "G3_INPUTS_SECURED"]),
    StateTransitionRule(to_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
                        requires_all_gates=["G4_OFFTAKE_BANKABLE"]),
    StateTransitionRule(to_state=BankabilityState.BUILDABLE,
                        requires_all_gates=["G5_EPC_RISK_PRICED"]),
    StateTransitionRule(to_state=BankabilityState.STRUCTURALLY_BANKABLE,
                        requires_all_gates=["G6_IE_SIGNOFF"]),
    StateTransitionRule(to_state=BankabilityState.CREDIT_APPROVED,
                        requires_all_gates=["G7_INSURANCE_BOUND", "G8_AUDIT_GRADE_MODEL", "G9_PERMITS_SAFE"]),
    StateTransitionRule(to_state=BankabilityState.FINANCEABLE,
                        requires_all_gates=["G10_FINANCIAL_CLOSE_CP"]),
    StateTransitionRule(to_state=BankabilityState.OPERATIONAL,
                        requires_all_gates=["G11_COD_STABILIZATION"]),
    StateTransitionRule(to_state=BankabilityState.REFINANCING_ELIGIBLE,
                        requires_all_gates=["G11_COD_STABILIZATION"]),
]


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION RULES (from regression_rules JSON)
# ═══════════════════════════════════════════════════════════════════════════════

class RegressionRule(BaseModel):
    from_state: BankabilityState
    if_gate_fails: str
    to_state: BankabilityState
    reason: str


REGRESSION_RULES: list[RegressionRule] = [
    RegressionRule(
        from_state=BankabilityState.BUILDABLE,
        if_gate_fails="G5_EPC_RISK_PRICED",
        to_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
        reason="EPC/interface gap discovered",
    ),
    RegressionRule(
        from_state=BankabilityState.CREDIT_APPROVED,
        if_gate_fails="G7_INSURANCE_BOUND",
        to_state=BankabilityState.STRUCTURALLY_BANKABLE,
        reason="Insurance exclusions or DSU gap",
    ),
    RegressionRule(
        from_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
        if_gate_fails="G4_OFFTAKE_BANKABLE",
        to_state=BankabilityState.TECHNICALLY_PLAUSIBLE,
        reason="Offtake credit support removed or contract loses assignability",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE STATUS (input from the platform DB)
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# The evidence bar — rules 4.0.0 (3.0.0 "the stronger bar", plus the multi-party
# items of 27 Sept 2026), identical to the runtime.
#
# MATURITY is a separate axis from verification. Verification answers "is this
# document authentic?"; maturity answers "how far has the instrument got?". A
# VERIFIED item counts only when its declared maturity meets REQUIRED_MATURITY,
# and undeclared maturity fails closed. Before 3.0.0 the only maturity signal
# was the key's name, so an LOI uploaded into an "..._executed" slot satisfied it.
MATURITY_LEVELS: list[str] = ["INTENT", "INDICATIVE", "AGREED", "EXECUTED", "EFFECTIVE"]

MATURITY_DEFINITIONS: dict[str, str] = {
    "INTENT": "Plan, mandate, letter of intent, MOU, strategy, or application in preparation.",
    "INDICATIVE": "Term sheet, quotation, indication of terms, or application submitted.",
    "AGREED": "Agreed-form document with all terms settled, not yet signed or granted.",
    "EXECUTED": "Signed, bound, granted, issued or passed.",
    "EFFECTIVE": "In force: conditions precedent satisfied, policy incepted, appeal period expired.",
}

REQUIRED_MATURITY: dict[str, str] = {
    "land_option_or_lease_executed": "EXECUTED",
    "ppa_signed_or_term_sheet_evidence": "INDICATIVE",
    "feedstock_supply_agreement": "INDICATIVE",
    "binding_offtake_contract_executed": "EXECUTED",
    "credit_support_package": "EXECUTED",
    "technology_licensor_term_sheet": "INDICATIVE",
    "epc_contract_fixed_price_or_capped_gmp": "AGREED",
    "oem_warranties": "AGREED",
    "technology_licence_process_guarantee": "AGREED",
    "long_lead_items_reserved": "AGREED",
    "epc_security_package": "AGREED",
    "ie_report_issued": "EXECUTED",
    "insurance_term_sheet": "INDICATIVE",
    "model_audit_opinion": "EXECUTED",
    "eia_permit_granted": "EXECUTED",
    "construction_permit_granted": "EXECUTED",
    "ancillary_permits_granted": "EXECUTED",
    "legal_opinion_on_appeal_risk": "EXECUTED",
    "cp_checklist_completed": "EFFECTIVE",
    "equity_injected": "EXECUTED",
    "dsra_funded": "EXECUTED",
    "security_package_perfected": "EFFECTIVE",
    "insurance_certificates_delivered": "EFFECTIVE",
    "all_major_contracts_executed": "EXECUTED",
    "legal_opinions_issued": "EXECUTED",
    "om_contract_or_organisation": "EXECUTED",
    "cod_certificate": "EXECUTED",
    "performance_tests_passed": "EXECUTED",
    "operating_permit_effective": "EFFECTIVE",
    "certificates_issued": "EXECUTED",
    "first_deliveries_accepted": "EXECUTED",
}

# Keys removed in 3.0.0. Rows on them remain as history — they are true records
# of what happened — but no gate scores them, and a retired key is never
# re-labelled as its replacement: an EIA *submission* must not become a *grant*.
RETIRED_EVIDENCE: dict[str, dict[str, str]] = {
    "feedstock_supply_loi": {"gate": "G3_INPUTS_SECURED", "replaced_by": "feedstock_supply_agreement", "reason": "An LOI is an intention; G3 requires indicative terms."},
    "binding_offtake_term_sheet": {"gate": "G4_OFFTAKE_BANKABLE", "replaced_by": "binding_offtake_contract_executed", "reason": "A term sheet is not binding offtake."},
    "epc_contract_heads_of_terms": {"gate": "G5_EPC_RISK_PRICED", "replaced_by": "epc_contract_fixed_price_or_capped_gmp", "reason": "Heads of terms do not price risk; G5 requires the agreed form."},
    "performance_guarantees_draft": {"gate": "G5_EPC_RISK_PRICED", "replaced_by": "liquidated_damages_schedule", "reason": "Guarantees and LDs are settled in the agreed-form EPC."},
    "ie_appointment_letter": {"gate": "G6_IE_SIGNOFF", "replaced_by": "ie_report_issued", "reason": "An appointment is not a sign-off."},
    "ie_technical_model_review": {"gate": "G6_IE_SIGNOFF", "replaced_by": "energy_balance_verified", "reason": "Replaced by the IE's specific technical opinions."},
    "ie_site_visit_report": {"gate": "G6_IE_SIGNOFF", "replaced_by": "ie_report_issued", "reason": "Site findings are contained in the issued report."},
    "insurance_broker_mandate": {"gate": "G7_INSURANCE_BOUND", "replaced_by": "insurance_term_sheet", "reason": "A mandate is not evidence of insurability."},
    "financial_model_v1": {"gate": "G8_AUDIT_GRADE_MODEL", "replaced_by": "base_case_model", "reason": "Renamed to the locked base case."},
    "model_audit_engagement": {"gate": "G8_AUDIT_GRADE_MODEL", "replaced_by": "model_audit_opinion", "reason": "An engagement is not an audit."},
    "sensitivity_analysis": {"gate": "G8_AUDIT_GRADE_MODEL", "replaced_by": "downside_cases", "reason": "Lender downside cases subsume one-factor sensitivities."},
    "eia_submission": {"gate": "G9_PERMITS_SAFE", "replaced_by": "eia_permit_granted", "reason": "A submission is not a permit."},
    "construction_permit_application": {"gate": "G9_PERMITS_SAFE", "replaced_by": "construction_permit_granted", "reason": "An application is not a permit."},
    "cp_checklist_draft": {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "cp_checklist_completed", "reason": "A draft checklist is not close."},
    "legal_opinions_draft": {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "legal_opinions_issued", "reason": "Draft opinions are not a closing condition met."},
    "security_package_structure": {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "security_package_perfected", "reason": "A structure is not perfected security."},
    "commissioning_plan": {"gate": "G11_COD_STABILIZATION", "replaced_by": "performance_tests_passed", "reason": "A plan is not a passed test."},
    "handover_documentation_plan": {"gate": "G11_COD_STABILIZATION", "replaced_by": "cod_certificate", "reason": "Acceptance is evidenced by the COD / taking-over certificate."},
    "certification_route_definition": {"gate": "G2_CERTIFICATION_PATH_LOCKED", "replaced_by": "certification_scheme_selection", "reason": "Duplicate concept."},
    "power_supply_structure_defined": {"gate": "G3_INPUTS_SECURED", "replaced_by": "ppa_register", "reason": "Power supply is evidenced in G1."},
    "co2_or_biomass_supply_strategy": {"gate": "G3_INPUTS_SECURED", "replaced_by": "feedstock_supply_agreement", "reason": "A strategy is not a supply."},
    "logistics_concept_note": {"gate": "G3_INPUTS_SECURED", "replaced_by": "transport_logistics_study", "reason": "A concept note is not a study."},
    "car_ear_bound": {"gate": "G7_INSURANCE_BOUND", "replaced_by": "insurance_certificates_delivered", "reason": "Binding happens at financial close, not before credit approval."},
    "dsu_bi_bound": {"gate": "G7_INSURANCE_BOUND", "replaced_by": "insurance_certificates_delivered", "reason": "Binding happens at financial close, not before credit approval."},
    "liability_bound": {"gate": "G7_INSURANCE_BOUND", "replaced_by": "insurance_certificates_delivered", "reason": "Binding happens at financial close, not before credit approval."},
    "lenders_loss_payee": {"gate": "G7_INSURANCE_BOUND", "replaced_by": "insurance_certificates_delivered", "reason": "Loss-payee endorsement is shown on the certificates at close."},
}


def maturity_meets(declared: Optional[str], required: Optional[str]) -> bool:
    """True when `declared` is at or above `required`. Unknown fails closed."""
    if not required:
        return True
    if declared not in MATURITY_LEVELS:
        return False
    return MATURITY_LEVELS.index(declared) >= MATURITY_LEVELS.index(required)


# Every evidence key the platform may receive, mapped to its gate. Authorization
# resolves an incoming evidence_key through this map (abac.gate_for_evidence);
# an unresolved key leaves gate_id None and rule R5 denies every actor. Retired
# keys resolve to the gate they were retired from, so a stale client gets the
# write handler's explanation of what replaced the key rather than a bare 403.
EVIDENCE_GATE_MAP: dict[str, str] = {
    **{ek: info["gate"] for ek, info in RETIRED_EVIDENCE.items()},
    **{ek: g.id for g in GATE_REGISTRY for ek in g.required_evidence},
}


# The organisational function that produces each evidence item — copied from the
# engine's EVIDENCE_META (owner_function) and held identical to it by
# tests/test_gate_registries_agree.py. A function is not a person: evidence
# requests are assigned to a named account of the owning company by
# resolve_assignee() below, and this map is the first half of that decision.
EVIDENCE_OWNER_FUNCTION: dict[str, str] = {
    # G0_SITE_RIGHTS
    "land_option_or_lease_executed": "LEGAL",
    "zoning_compatibility_memo": "LEGAL",
    "stakeholder_map_v1": "PROJECT",
    "site_technical_suitability": "ENGINEERING",
    # G1_GRID_UTILITIES_REALITY
    "grid_interconnection_study": "ENGINEERING",
    "queue_position_evidence": "ENGINEERING",
    "grid_connection_cost_estimate": "ENGINEERING",
    "connection_date_cod_compatibility_memo": "ENGINEERING",
    "ppa_register": "SALES",
    "ppa_signed_or_term_sheet_evidence": "SALES",
    "ppa_volume_load_coverage_analysis": "ENGINEERING",
    "ppa_tenor_debt_comparison": "FINANCE",
    "curtailment_assessment": "ENGINEERING",
    "dispatch_load_factor_production_impact": "ENGINEERING",
    "water_source_plan": "ENGINEERING",
    "water_permit_pathway_memo": "LEGAL",
    "btm_generation_asset_evidence": "ENGINEERING",
    "generation_yield_study": "ENGINEERING",
    "grid_independence_note": "ENGINEERING",
    "backup_construction_power_plan": "PROJECT",
    "technology_maturity_dossier": "ENGINEERING",
    "technology_licensor_term_sheet": "ENGINEERING",
    "integrated_mass_energy_balance": "ENGINEERING",
    # G2_CERTIFICATION_PATH_LOCKED
    "certification_scheme_selection": "LEGAL",
    "additionality_evidence": "ENGINEERING",
    "power_sourcing_alignment_note": "ENGINEERING",
    "ghg_methodology_memo": "ENGINEERING",
    "mrv_plan_v1": "ENGINEERING",
    "product_qualification_pathway": "ENGINEERING",
    # G3_INPUTS_SECURED
    "feedstock_supply_agreement": "PROJECT",
    "transport_logistics_study": "ENGINEERING",
    "storage_plan": "ENGINEERING",
    "feedstock_spec_eligibility": "ENGINEERING",
    # G4_OFFTAKE_BANKABLE
    "binding_offtake_contract_executed": "SALES",
    "offtake_credit_assessment": "FINANCE",
    "credit_support_package": "FINANCE",
    "take_or_pay_floor": "LEGAL",
    "termination_payment_formula": "LEGAL",
    "assignment_rights": "LEGAL",
    "step_in_rights": "LEGAL",
    "hedgeable_pricing_index": "FINANCE",
    "price_review_mechanism_memo": "LEGAL",
    "offtake_seller_obligations": "LEGAL",
    # G5_EPC_RISK_PRICED
    "epc_contract_fixed_price_or_capped_gmp": "PROJECT",
    "liquidated_damages_schedule": "LEGAL",
    "date_certain_schedule": "PROJECT",
    "performance_test_protocol": "ENGINEERING",
    "interface_matrix": "ENGINEERING",
    "oem_warranties": "ENGINEERING",
    "epc_contractor_dd": "PROJECT",
    "feed_complete_class3": "ENGINEERING",
    "technology_licence_process_guarantee": "ENGINEERING",
    "long_lead_items_reserved": "PROJECT",
    "epc_security_package": "LEGAL",
    "independent_technical_review": "INDEPENDENT_ENGINEER",
    # G6_IE_SIGNOFF
    "ie_report_issued": "INDEPENDENT_ENGINEER",
    "energy_balance_verified": "INDEPENDENT_ENGINEER",
    "capex_opinion_reasonableness": "INDEPENDENT_ENGINEER",
    "opex_opinion_reasonableness": "INDEPENDENT_ENGINEER",
    "completion_test_definitions": "INDEPENDENT_ENGINEER",
    # G7_INSURANCE_BOUND
    "insurance_term_sheet": "TREASURY",
    "insurance_market_report": "TREASURY",
    "deductibles_accepted": "TREASURY",
    "exclusions_register_reviewed": "LEGAL",
    "foak_exclusions_warranty_backstop": "TREASURY",
    # G8_AUDIT_GRADE_MODEL
    "base_case_model": "FINANCE",
    "model_audit_opinion": "FINANCE",
    "downside_cases": "FINANCE",
    "covenant_suite_defined": "FINANCE",
    "dsra_maintenance_reserve_logic": "FINANCE",
    "hedging_plan": "TREASURY",
    "model_consistency_with_ie": "FINANCE",
    # G9_PERMITS_SAFE
    "eia_permit_granted": "LEGAL",
    "construction_permit_granted": "LEGAL",
    "ancillary_permits_granted": "LEGAL",
    "legal_opinion_on_appeal_risk": "LEGAL",
    "operating_permit_pathway": "LEGAL",
    "stakeholder_management_plan_v2": "PROJECT",
    # G10_FINANCIAL_CLOSE_CP
    "cp_checklist_completed": "LEGAL",
    "equity_injected": "FINANCE",
    "dsra_funded": "TREASURY",
    "security_package_perfected": "LEGAL",
    "insurance_certificates_delivered": "TREASURY",
    "all_major_contracts_executed": "LEGAL",
    "legal_opinions_issued": "LEGAL",
    "om_contract_or_organisation": "PROJECT",
    # G11_COD_STABILIZATION
    "cod_certificate": "ENGINEERING",
    "performance_tests_passed": "ENGINEERING",
    "operating_permit_effective": "LEGAL",
    "mrv_reporting_live": "ENGINEERING",
    "six_to_twelve_months_stable_ops": "ENGINEERING",
    "certificates_issued": "ENGINEERING",
    "first_deliveries_accepted": "SALES",
}


# Rules 4.0.0 — financing scope per ITEM. Only these items protect an external
# lender; for BALANCE_SHEET funding they are not applicable and no request is
# raised for them. Held identical to the runtime by tests/test_gate_registries_agree.py.
EVIDENCE_SCOPE: dict[str, str] = {
    "credit_support_package": "PROJECT_FINANCE",
    "take_or_pay_floor": "PROJECT_FINANCE",
    "termination_payment_formula": "PROJECT_FINANCE",
    "assignment_rights": "PROJECT_FINANCE",
    "step_in_rights": "PROJECT_FINANCE",
    "hedgeable_pricing_index": "PROJECT_FINANCE",
    "ie_report_issued": "PROJECT_FINANCE",
    "energy_balance_verified": "PROJECT_FINANCE",
    "capex_opinion_reasonableness": "PROJECT_FINANCE",
    "opex_opinion_reasonableness": "PROJECT_FINANCE",
    "completion_test_definitions": "PROJECT_FINANCE",
    "deductibles_accepted": "PROJECT_FINANCE",
    "base_case_model": "PROJECT_FINANCE",
    "model_audit_opinion": "PROJECT_FINANCE",
    "downside_cases": "PROJECT_FINANCE",
    "covenant_suite_defined": "PROJECT_FINANCE",
    "dsra_maintenance_reserve_logic": "PROJECT_FINANCE",
    "hedging_plan": "PROJECT_FINANCE",
    "model_consistency_with_ie": "PROJECT_FINANCE",
    "cp_checklist_completed": "PROJECT_FINANCE",
    "dsra_funded": "PROJECT_FINANCE",
    "security_package_perfected": "PROJECT_FINANCE",
    "legal_opinions_issued": "PROJECT_FINANCE",
}

# Gates whose every item protects a lender — waived for balance-sheet funding.
LENDER_ONLY_GATES: frozenset[str] = frozenset(
    g.id for g in GATE_REGISTRY
    if all(EVIDENCE_SCOPE.get(k) == "PROJECT_FINANCE" for k in g.required_evidence)
)

# Power-model scoping — the runtime's EVIDENCE_META "applies_to", for the items
# restricted to some power models only. Every other item applies to all. Before
# this copy existed the platform could not tell whether an item applied, so the
# 2026-09-26 conversion raised requests for behind-the-meter evidence on a
# grid-connected plant, and nothing refused assigning or committing to them.
# Held identical to the runtime by tests/test_gate_registries_agree.py.
EVIDENCE_POWER_MODELS: dict[str, list[str]] = {
    "grid_interconnection_study": ["GRID_CONNECTED", "HYBRID"],
    "queue_position_evidence": ["GRID_CONNECTED", "HYBRID"],
    "grid_connection_cost_estimate": ["GRID_CONNECTED", "HYBRID"],
    "connection_date_cod_compatibility_memo": ["GRID_CONNECTED", "HYBRID"],
    "ppa_register": ["GRID_CONNECTED", "HYBRID"],
    "ppa_signed_or_term_sheet_evidence": ["GRID_CONNECTED", "HYBRID"],
    "ppa_volume_load_coverage_analysis": ["GRID_CONNECTED", "HYBRID"],
    "ppa_tenor_debt_comparison": ["GRID_CONNECTED", "HYBRID"],
    "btm_generation_asset_evidence": ["OFF_GRID_BTM", "HYBRID"],
    "generation_yield_study": ["OFF_GRID_BTM", "HYBRID"],
    "grid_independence_note": ["OFF_GRID_BTM", "HYBRID"],
    "backup_construction_power_plan": ["OFF_GRID_BTM", "HYBRID"],
}


def inapplicability(key: str, power_model: str | None, financing_model: str | None) -> str | None:
    """Why an item does not apply to a project, or None if it does.

    Mirrors the engine's not_applicable_reason exactly (a test compares every
    item under every premise): POWER_MODEL first, then FINANCING_MODEL. An
    undeclared power model applies everything — the engine scores the superset.
    """
    models = EVIDENCE_POWER_MODELS.get(key)
    if models and power_model and power_model not in models:
        return "POWER_MODEL"
    if financing_model == "BALANCE_SHEET" and EVIDENCE_SCOPE.get(key) == "PROJECT_FINANCE":
        return "FINANCING_MODEL"
    return None


# Rules 4.0.0 — commitment cards. The structured terms a project records for its
# offtake, EPC, schedule, supply and model; the engine derives the offtake (O0–O7)
# and EPC (E0–E6) ladders and the coherence checks from them. Types: str, number,
# bool, date (YYYY-MM-DD), list (of strings), enum:A|B|C. Held identical to the
# runtime's COMMITMENT_CARD_FIELDS by tests/test_gate_registries_agree.py.
COMMITMENT_CARD_FIELDS: dict[str, dict[str, str]] = {
    "offtake": {
        # contracted_tonnes_per_year: volume under offtake terms, all buyers;
        # planned_output_tonnes_per_year: what it is measured against (4.1.0).
        "counterparty_name": "str",
        "counterparty_role": "enum:END_USER|OBLIGATED_SUPPLIER|TRADER|INTERMEDIARY|EQUITY_PARTNER",
        "planned_output_tonnes_per_year": "number",
        "buyer_investment_grade": "bool",
        "credit_support": "bool",
        "commitment_form": "enum:TAKE_OR_PAY|TAKE_IF_TENDERED|TAKE_AND_PAY|TAKE_IF_DELIVERED|FRAMEWORK",
        "take_or_pay_pct": "number",
        "contracted_tonnes_per_year": "number",
        "tenor_years": "number",
        "price_mechanism": "enum:FIXED|COST_PLUS|INDEX_PLUS_PREMIUM|FLOOR_CAP|OTHER",
        "cps_satisfied": "bool",
        "conditions_precedent": "list",
        "longstop_date": "date",
        "first_delivery_date": "date",
        "delay_ld_cap_eur": "number",
        "product_spec_standard": "str",
        "certification_scheme": "str",
        "compliance_regime": "list",
        "fm_definition_ref": "str",
        "change_in_law_allocated": "bool",
    },
    "epc": {
        "contractor_name": "str",
        "contracting_model": "enum:LSTK|EPCM|SPLIT_PACKAGES|EPC_CONVERSION|OWNER_INTEGRATED",
        "contract_price_eur": "number",
        "guaranteed_completion_date": "date",
        "guaranteed_capacity_tonnes_per_year": "number",
        "expected_availability_pct": "number",
        "delay_ld_cap_eur": "number",
        "performance_ld_cap_eur": "number",
        "guaranteed_product_spec": "str",
        "contingency_eur": "number",
        "sponsor_support_eur": "number",
        "fm_definition_ref": "str",
        "counterparty_insolvent": "bool",
    },
    "schedule": {
        "permits_expected_date": "date",
        "appeal_period_months": "number",
        "fid_target_date": "date",
        "construction_months_p80": "number",
        "commissioning_allowance_months": "number",
        "forecast_cod_date": "date",
    },
    "supply": {
        "feedstock_required_tonnes_per_year": "number",
        "feedstock_contracted_tonnes_per_year": "number",
        "feedstock_tenor_years": "number",
        "power_required_mwh_per_year": "number",
        "power_contracted_mwh_per_year": "number",
        "power_tenor_years": "number",
        "power_meets_certification": "bool",
        "co2_source_eligible": "bool",
        "certification_scheme": "str",
        "fm_definition_ref": "str",
        "support_or_ppa_revoked": "bool",
        "certification_suspended": "bool",
    },
    "model": {
        "debt_tenor_years": "number",
        "model_contracted_tonnes_per_year": "number",
        "model_offtake_tenor_years": "number",
        "model_epc_price_eur": "number",
    },
}

# Which gate a card belongs to — for write authorisation (abac R5 resolves every
# bankability write to a gate) and for display. Supply feeds G3's feedstock and
# G1's power; it is written by the producer's inputs team, so it sits with G3.
TERMS_CARD_GATE: dict[str, str] = {
    "offtake": "G4_OFFTAKE_BANKABLE",
    "epc": "G5_EPC_RISK_PRICED",
    "schedule": "G5_EPC_RISK_PRICED",
    "supply": "G3_INPUTS_SECURED",
    "model": "G8_AUDIT_GRADE_MODEL",
}

# Evidence owner function -> auth_users.business_function. The account vocabulary
# is coarser than the evidence one: there is no LEGAL or PROJECT business
# function, so those items route to the company's EXECUTIVE, who is accountable
# for them in every gate's RACI. INDEPENDENT_ENGINEER maps to nothing on purpose:
# the IE is appointed by the lenders and is never an account of the producer.
OWNER_FUNCTION_TO_BUSINESS_FUNCTION: dict[str, Optional[str]] = {
    "ENGINEERING": "ENGINEERING",
    "SALES": "COMMERCIAL",
    "FINANCE": "FINANCE_TREASURY",
    "TREASURY": "FINANCE_TREASURY",
    "LEGAL": "EXECUTIVE",
    "PROJECT": "EXECUTIVE",
    "INDEPENDENT_ENGINEER": None,
}


def resolve_assignee(evidence_key: str, accounts: list[dict]) -> tuple[Optional[str], str]:
    """Pick the account that should own an evidence request, and say why.

    `accounts` are the ACTIVE auth_users rows of the company that owns the
    project (dicts with user_id and business_function). Returns
    (user_id or None, reason). Deterministic: among several accounts with the
    same function, the lowest user_id wins, so a re-run assigns the same person.
    Falls back to the EXECUTIVE when the company has nobody in the function, and
    returns None — an honest gap, never a guess — when there is no one to ask.
    """
    owner = EVIDENCE_OWNER_FUNCTION.get(evidence_key)
    if owner is None:
        return None, f"'{evidence_key}' is not a live evidence item"
    target = OWNER_FUNCTION_TO_BUSINESS_FUNCTION.get(owner)
    if target is None:
        return None, f"{owner} is an external party, not an account of the producer"
    by_function: dict[str, list[str]] = {}
    for a in accounts:
        by_function.setdefault(a.get("business_function") or "", []).append(a["user_id"])
    if by_function.get(target):
        if target == "EXECUTIVE":
            return (sorted(by_function[target])[0],
                    f"{owner} item; accounts carry no {owner} function, so the company's EXECUTIVE owns it")
        return sorted(by_function[target])[0], f"{owner} item, assigned to the company's {target} account"
    if target != "EXECUTIVE" and by_function.get("EXECUTIVE"):
        return (sorted(by_function["EXECUTIVE"])[0],
                f"{owner} item; the company has no {target} account, so it routes to its EXECUTIVE")
    missing = target if target == "EXECUTIVE" else f"{target} or EXECUTIVE"
    return None, f"{owner} item; the company has no {missing} account to assign it to"


class EvidenceStatus(str, Enum):
    """
    Evidence items progress through these states.
    Only VERIFIED counts as "complete" for gate evaluation.
    """
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"         # uploaded but not reviewed
    UNDER_REVIEW = "UNDER_REVIEW"   # reviewer assigned
    VERIFIED = "VERIFIED"           # approved — counts toward gate
    REJECTED = "REJECTED"           # sent back — needs rework
    EXPIRED = "EXPIRED"             # was verified, now lapsed


class EvidenceItem(BaseModel):
    key: str
    status: EvidenceStatus = EvidenceStatus.NOT_STARTED
    submitted_by: Optional[str] = None
    verified_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    document_hash: Optional[str] = None
    notes: Optional[str] = None
    # R2: Verification state for weighted gate scoring
    verification_state: VerificationState = VerificationState.UNVERIFIED
    verifier_firm: Optional[str] = None
    verifier_reference: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE OUTPUT MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class GateEvaluation(BaseModel):
    gate_id: str
    gate_name: str
    owners: list[Department]
    total_evidence: int
    verified_count: int
    completion_pct: float          # raw score — evidence present / total
    effective_completion_pct: float = 0.0  # R2: verification-weighted score
    verification_summary: dict[str, int] = Field(default_factory=dict)  # R2: count per state
    is_complete: bool
    evidence_detail: list[EvidenceItem]
    unlocks_capital: list[CapitalType]
    unlocks_state: Optional[BankabilityState] = None
    blocking_items: list[str] = Field(default_factory=list)


class RegressionEvent(BaseModel):
    from_state: BankabilityState
    to_state: BankabilityState
    trigger_gate: str
    reason: str
    detected_at: datetime


class CapitalUnlock(BaseModel):
    capital_type: CapitalType
    is_unlocked: bool
    gating_gates: list[str]
    best_progress_pct: float


class CertaintyDimension(BaseModel):
    """Decomposed certainty sub-score for a single risk dimension."""
    dimension: str  # COST, REVENUE, CERTIFICATION, EXECUTION, COUNTERPARTY
    raw_score: float  # 0.0-1.0
    verification_weight: float  # from verification.py weights
    weighted_score: float  # raw_score * verification_weight
    blocking_flag: bool  # True if this dimension blocks capital eligibility


class ProjectBankabilitySnapshot(BaseModel):
    """
    The complete bankability evaluation for a project.
    This is the primary response from the engine.
    """
    project_id: str
    evaluated_at: datetime
    current_state: BankabilityState
    previous_state: Optional[BankabilityState] = None
    regression: Optional[RegressionEvent] = None
    gate_evaluations: list[GateEvaluation]
    capital_unlocks: list[CapitalUnlock]
    total_evidence: int
    total_verified: int
    overall_completion_pct: float
    # R2: Verification-weighted scores (these govern state machine transitions)
    gate_scores_raw: dict[str, float] = Field(default_factory=dict)
    gate_scores_effective: dict[str, float] = Field(default_factory=dict)
    verification_summary: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Decomposed certainty stack — 5-axis sub-scores
    certainty_stack: list[CertaintyDimension] = Field(default_factory=list)
    next_state: Optional[BankabilityState] = None
    gates_blocking_next_state: list[str] = Field(default_factory=list)
    snapshot_hash: str = ""


class PersonaScopedSnapshot(BaseModel):
    """
    Filtered view of a snapshot for a specific stakeholder persona.
    """
    persona: StakeholderPersona
    project_id: str
    current_state: BankabilityState
    visible_gates: list[GateEvaluation]
    visible_capital: list[CapitalUnlock]
    department_progress: dict[str, dict]   # dept -> {total, verified, pct}
    action_items: list[dict]               # blocking evidence for this persona
    kpi_summary: dict                      # persona-specific KPIs


# ═══════════════════════════════════════════════════════════════════════════════
# THE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class BankabilityEngine:
    """
    Stateless evaluation engine.
    Takes evidence state as input, returns deterministic bankability snapshot.
    Designed to be called on every evidence status change.

    Integration:
      - gex-platform-enhanced writes evidence to its DB
      - On every write, it calls POST /api/v1/bankability/evaluate
      - This engine evaluates and returns the snapshot
      - The platform stores the snapshot and pushes to frontend via WebSocket
    """

    def __init__(self):
        self.gates = GATE_REGISTRY
        self.gate_index = GATE_INDEX
        self.state_rules = STATE_RULES
        self.regression_rules = REGRESSION_RULES

    # ─── GATE EVALUATION ────────────────────────────────────────────────────

    def evaluate_gate(
        self, gate: GateDefinition, evidence_map: dict[str, EvidenceItem]
    ) -> GateEvaluation:
        """
        Evaluate a single gate against current evidence state.

        R2: Gate score is now reported as both raw (evidence present / total)
        and effective (raw × mean verification weight). The state machine uses
        the effective score. Raw scores remain visible in the analytics panel.
        """
        detail = []
        verified = 0
        blocking = []
        v_states: list[VerificationState] = []

        for key in gate.required_evidence:
            item = evidence_map.get(key, EvidenceItem(key=key))
            detail.append(item)
            v_states.append(item.verification_state)
            if item.status == EvidenceStatus.VERIFIED:
                verified += 1
            else:
                blocking.append(key)

        total = len(gate.required_evidence)
        raw_pct = round((verified / total) * 100, 1) if total > 0 else 0.0

        # R2: Effective score = raw × mean(verification_weights)
        if v_states:
            avg_weight = sum(VERIFICATION_WEIGHTS[s] for s in v_states) / len(v_states)
        else:
            avg_weight = VERIFICATION_WEIGHTS[VerificationState.UNVERIFIED]
        effective_pct = round(raw_pct * avg_weight, 2)

        # R2: Verification state summary for this gate
        v_summary: dict[str, int] = {s.value: 0 for s in VerificationState}
        for s in v_states:
            v_summary[s.value] += 1

        return GateEvaluation(
            gate_id=gate.id,
            gate_name=gate.name,
            owners=gate.owners,
            total_evidence=total,
            verified_count=verified,
            completion_pct=raw_pct,
            effective_completion_pct=effective_pct,
            verification_summary=v_summary,
            is_complete=(verified == total),
            evidence_detail=detail,
            unlocks_capital=gate.unlocks_capital,
            unlocks_state=gate.unlocks_state,
            blocking_items=blocking,
        )

    # ─── STATE COMPUTATION ──────────────────────────────────────────────────

    def compute_state(
        self, gate_results: dict[str, GateEvaluation]
    ) -> BankabilityState:
        """
        Walk the state rules in order. A project reaches a state only when
        ALL prior states are also satisfied (sequential progression).
        """
        achieved = BankabilityState.SPECULATIVE

        for rule in self.state_rules:
            all_gates_complete = all(
                gate_results[gid].is_complete
                for gid in rule.requires_all_gates
                if gid in gate_results
            )
            if all_gates_complete:
                # Only advance if this state is >= current achieved
                candidate_idx = STATE_ORDER.index(rule.to_state)
                achieved_idx = STATE_ORDER.index(achieved)
                if candidate_idx > achieved_idx:
                    achieved = rule.to_state
            else:
                # Sequential: stop at first unsatisfied transition
                # unless later rules reference already-complete gates
                break

        return achieved

    # ─── REGRESSION DETECTION ───────────────────────────────────────────────

    def check_regressions(
        self,
        current_state: BankabilityState,
        previous_state: Optional[BankabilityState],
        gate_results: dict[str, GateEvaluation],
    ) -> Optional[RegressionEvent]:
        """
        Check if a previously-complete gate has become incomplete,
        triggering a state regression per the regression rules.
        """
        if previous_state is None:
            return None

        for rule in self.regression_rules:
            if rule.from_state == previous_state:
                gate_eval = gate_results.get(rule.if_gate_fails)
                if gate_eval and not gate_eval.is_complete:
                    return RegressionEvent(
                        from_state=rule.from_state,
                        to_state=rule.to_state,
                        trigger_gate=rule.if_gate_fails,
                        reason=rule.reason,
                        detected_at=datetime.now(timezone.utc),
                    )
        return None

    # ─── CAPITAL UNLOCKS ────────────────────────────────────────────────────

    def compute_capital_unlocks(
        self, gate_results: dict[str, GateEvaluation]
    ) -> list[CapitalUnlock]:
        """Determine which capital types are unlocked based on gate completion."""
        unlocks = []
        for cap in CapitalType:
            gating = [g for g in self.gates if cap in g.unlocks_capital]
            gating_ids = [g.id for g in gating]

            # Capital is unlocked when ANY gating gate is complete
            # (a capital type can be unlocked by multiple gates)
            is_unlocked = any(
                gate_results[gid].is_complete
                for gid in gating_ids
                if gid in gate_results
            )
            best_pct = max(
                (gate_results[gid].completion_pct for gid in gating_ids if gid in gate_results),
                default=0.0,
            )
            unlocks.append(CapitalUnlock(
                capital_type=cap,
                is_unlocked=is_unlocked,
                gating_gates=gating_ids,
                best_progress_pct=best_pct if not is_unlocked else 100.0,
            ))
        return unlocks

    # ─── NEXT STATE ANALYSIS ────────────────────────────────────────────────

    def compute_next_state_blockers(
        self,
        current_state: BankabilityState,
        gate_results: dict[str, GateEvaluation],
    ) -> tuple[Optional[BankabilityState], list[str]]:
        """What's the next state and which gates are blocking it?"""
        current_idx = STATE_ORDER.index(current_state)
        if current_idx >= len(STATE_ORDER) - 1:
            return None, []

        for rule in self.state_rules:
            target_idx = STATE_ORDER.index(rule.to_state)
            if target_idx > current_idx:
                blockers = [
                    gid for gid in rule.requires_all_gates
                    if gid in gate_results and not gate_results[gid].is_complete
                ]
                if blockers:
                    return rule.to_state, blockers
                # If no blockers, this state is satisfied, try next
                continue

        return None, []

    # ─── FULL EVALUATION (primary entry point) ──────────────────────────────

    def evaluate(
        self,
        project_id: str,
        evidence_map: dict[str, EvidenceItem],
        previous_state: Optional[BankabilityState] = None,
    ) -> ProjectBankabilitySnapshot:
        """
        Full bankability evaluation. Call this on every evidence change.

        Args:
            project_id: The GEX project identifier
            evidence_map: Current evidence status (key -> EvidenceItem)
            previous_state: Last known state (for regression detection)

        Returns:
            Complete ProjectBankabilitySnapshot
        """
        now = datetime.now(timezone.utc)

        # 1. Evaluate all gates
        gate_results: dict[str, GateEvaluation] = {}
        for gate in self.gates:
            gate_results[gate.id] = self.evaluate_gate(gate, evidence_map)

        # 2. Compute current state
        computed_state = self.compute_state(gate_results)

        # 3. Check for regression
        regression = self.check_regressions(computed_state, previous_state, gate_results)
        if regression:
            computed_state = regression.to_state

        # 4. Capital unlocks
        capital_unlocks = self.compute_capital_unlocks(gate_results)

        # 5. Next state blockers
        next_state, blockers = self.compute_next_state_blockers(computed_state, gate_results)

        # 6. Totals
        all_evidence = list(evidence_map.values())
        total = len(all_evidence)
        verified = sum(1 for e in all_evidence if e.status == EvidenceStatus.VERIFIED)
        overall_pct = round((verified / total) * 100, 1) if total > 0 else 0.0

        # 7. Decomposed certainty stack
        certainty_stack = self.compute_certainty_stack(gate_results)

        snapshot = ProjectBankabilitySnapshot(
            project_id=project_id,
            evaluated_at=now,
            current_state=computed_state,
            previous_state=previous_state,
            regression=regression,
            gate_evaluations=list(gate_results.values()),
            capital_unlocks=capital_unlocks,
            total_evidence=total,
            total_verified=verified,
            overall_completion_pct=overall_pct,
            certainty_stack=certainty_stack,
            next_state=next_state,
            gates_blocking_next_state=blockers,
        )

        # 7. Tamper-proof hash
        snapshot.snapshot_hash = self._hash_snapshot(snapshot)

        return snapshot

    # ─── PERSONA-SCOPED VIEW ────────────────────────────────────────────────

    def scope_for_persona(
        self,
        snapshot: ProjectBankabilitySnapshot,
        persona: StakeholderPersona,
    ) -> PersonaScopedSnapshot:
        """
        Filter a full snapshot to what a specific stakeholder persona can see.
        This is what the frontend workspace views call.
        """
        allowed_gates = PERSONA_GATES[persona]
        allowed_depts = PERSONA_DEPARTMENTS[persona]

        # Filter gates
        if allowed_gates:  # empty = all (Executive)
            visible = [g for g in snapshot.gate_evaluations if g.gate_id in allowed_gates]
        else:
            visible = snapshot.gate_evaluations

        # Filter capital (show only capital relevant to visible gates)
        visible_gate_ids = {g.gate_id for g in visible}
        visible_capital = [
            c for c in snapshot.capital_unlocks
            if any(gid in visible_gate_ids for gid in c.gating_gates)
        ]

        # Department progress
        dept_progress = {}
        for dept in allowed_depts:
            dept_gates = [g for g in visible if dept in g.owners]
            total = sum(g.total_evidence for g in dept_gates)
            verified = sum(g.verified_count for g in dept_gates)
            dept_progress[dept.value] = {
                "total": total,
                "verified": verified,
                "pct": round((verified / total) * 100, 1) if total > 0 else 0.0,
                "gates_owned": len(dept_gates),
            }

        # Action items: blocking evidence for this persona's gates
        action_items = []
        for gate in visible:
            if not gate.is_complete:
                for key in gate.blocking_items:
                    action_items.append({
                        "gate_id": gate.gate_id,
                        "gate_name": gate.gate_name,
                        "evidence_key": key,
                        "owners": [d.value for d in gate.owners],
                        "priority": "HIGH" if gate.unlocks_state else "MEDIUM",
                    })

        # Persona-specific KPIs
        kpi = self._build_persona_kpis(snapshot, persona, visible)

        return PersonaScopedSnapshot(
            persona=persona,
            project_id=snapshot.project_id,
            current_state=snapshot.current_state,
            visible_gates=visible,
            visible_capital=visible_capital,
            department_progress=dept_progress,
            action_items=action_items,
            kpi_summary=kpi,
        )

    # ─── PERSONA KPIs ──────────────────────────────────────────────────────

    def _build_persona_kpis(
        self,
        snapshot: ProjectBankabilitySnapshot,
        persona: StakeholderPersona,
        visible_gates: list[GateEvaluation],
    ) -> dict:
        """Build KPI payload specific to each persona's needs."""

        base = {
            "state": snapshot.current_state.value,
            "overall_pct": snapshot.overall_completion_pct,
            "gates_complete": sum(1 for g in visible_gates if g.is_complete),
            "gates_total": len(visible_gates),
        }

        if persona == StakeholderPersona.PRODUCER:
            # Production management focus: construction gates, permits, COD
            epc_gate = next((g for g in visible_gates if g.gate_id == "G5_EPC_RISK_PRICED"), None)
            cod_gate = next((g for g in visible_gates if g.gate_id == "G11_COD_STABILIZATION"), None)
            base["epc_readiness_pct"] = epc_gate.completion_pct if epc_gate else 0.0
            base["cod_readiness_pct"] = cod_gate.completion_pct if cod_gate else 0.0
            base["permits_status"] = next(
                (g.completion_pct for g in visible_gates if g.gate_id == "G9_PERMITS_SAFE"), 0.0
            )

        elif persona == StakeholderPersona.FINANCE:
            # CFO/Treasury focus: capital unlocked, model status, covenants
            base["capital_unlocked"] = sum(1 for c in snapshot.capital_unlocks if c.is_unlocked)
            base["capital_total"] = len(snapshot.capital_unlocks)
            model_gate = next((g for g in visible_gates if g.gate_id == "G8_AUDIT_GRADE_MODEL"), None)
            base["model_signoff_pct"] = model_gate.completion_pct if model_gate else 0.0
            close_gate = next((g for g in visible_gates if g.gate_id == "G10_FINANCIAL_CLOSE_CP"), None)
            base["financial_close_pct"] = close_gate.completion_pct if close_gate else 0.0
            base["regression_risk"] = snapshot.regression is not None

        elif persona == StakeholderPersona.REGULATOR:
            # Verification & audit focus: certification, IE, insurance
            base["certification_pct"] = next(
                (g.completion_pct for g in visible_gates if g.gate_id == "G2_CERTIFICATION_PATH_LOCKED"), 0.0
            )
            ie_gate = next((g for g in visible_gates if g.gate_id == "G6_IE_SIGNOFF"), None)
            base["ie_signoff_pct"] = ie_gate.completion_pct if ie_gate else 0.0
            base["audit_trail_hash"] = snapshot.snapshot_hash[:16]

        elif persona == StakeholderPersona.EXECUTIVE:
            # CEO/CFO/Head of Legal: strategic progression + risk
            base["state_progression"] = [
                {"state": s.value, "achieved": STATE_ORDER.index(snapshot.current_state) >= STATE_ORDER.index(s)}
                for s in BankabilityState
            ]
            base["capital_unlocked"] = sum(1 for c in snapshot.capital_unlocks if c.is_unlocked)
            base["capital_total"] = len(snapshot.capital_unlocks)
            base["regression_risk"] = snapshot.regression is not None
            base["regression_detail"] = (
                {
                    "from": snapshot.regression.from_state.value,
                    "to": snapshot.regression.to_state.value,
                    "reason": snapshot.regression.reason,
                }
                if snapshot.regression
                else None
            )
            base["blocking_next_state"] = snapshot.gates_blocking_next_state
            base["next_state"] = snapshot.next_state.value if snapshot.next_state else None

        return base

    # ─── DECOMPOSED CERTAINTY STACK ───────────────────────────────────────

    def compute_certainty_stack(
        self, gate_results: dict[str, GateEvaluation]
    ) -> list[CertaintyDimension]:
        """
        Compute 5 decomposed certainty dimensions from gate evaluation data.
        Each dimension maps to specific gates and produces a 0-1 score
        weighted by verification state.

        Dimensions:
          COST         — G5 (EPC) + G8 (Model) estimate class & cost spread
          REVENUE      — G4 (Offtake) bankability
          CERTIFICATION — G2 (Certification path)
          EXECUTION    — G5 (EPC) + G11 (COD) construction progress
          COUNTERPARTY — G4 (Offtake) + G7 (Insurance) credit quality
        """
        dimensions: list[CertaintyDimension] = []

        # Helper: compute dimension from a set of gate ids
        def _dim(name: str, gate_ids: list[str], blocking_gate: str) -> CertaintyDimension:
            scores = []
            v_weights = []
            for gid in gate_ids:
                ge = gate_results.get(gid)
                if ge:
                    scores.append(ge.completion_pct / 100.0)
                    # Average verification weight across this gate's evidence
                    v_states_for_gate = [
                        e.verification_state for e in ge.evidence_detail
                    ]
                    if v_states_for_gate:
                        avg_w = sum(VERIFICATION_WEIGHTS[s] for s in v_states_for_gate) / len(v_states_for_gate)
                    else:
                        avg_w = VERIFICATION_WEIGHTS[VerificationState.UNVERIFIED]
                    v_weights.append(avg_w)

            raw = sum(scores) / len(scores) if scores else 0.0
            v_weight = sum(v_weights) / len(v_weights) if v_weights else VERIFICATION_WEIGHTS[VerificationState.UNVERIFIED]
            weighted = round(raw * v_weight, 4)

            # Blocking: dimension blocks if its primary gate is incomplete
            blocking_eval = gate_results.get(blocking_gate)
            blocking = blocking_eval is not None and not blocking_eval.is_complete

            return CertaintyDimension(
                dimension=name,
                raw_score=round(raw, 4),
                verification_weight=round(v_weight, 4),
                weighted_score=weighted,
                blocking_flag=blocking,
            )

        dimensions.append(_dim("COST", ["G5_EPC_RISK_PRICED", "G8_AUDIT_GRADE_MODEL"], "G8_AUDIT_GRADE_MODEL"))
        dimensions.append(_dim("REVENUE", ["G4_OFFTAKE_BANKABLE"], "G4_OFFTAKE_BANKABLE"))
        dimensions.append(_dim("CERTIFICATION", ["G2_CERTIFICATION_PATH_LOCKED"], "G2_CERTIFICATION_PATH_LOCKED"))
        dimensions.append(_dim("EXECUTION", ["G5_EPC_RISK_PRICED", "G11_COD_STABILIZATION"], "G5_EPC_RISK_PRICED"))
        dimensions.append(_dim("COUNTERPARTY", ["G4_OFFTAKE_BANKABLE", "G7_INSURANCE_BOUND"], "G4_OFFTAKE_BANKABLE"))

        return dimensions

    # ─── AUDIT HASH ─────────────────────────────────────────────────────────

    @staticmethod
    def _hash_snapshot(snapshot: ProjectBankabilitySnapshot) -> str:
        """Create tamper-proof hash of the evaluation for audit trail."""
        payload = {
            "project_id": snapshot.project_id,
            "evaluated_at": snapshot.evaluated_at.isoformat(),
            "current_state": snapshot.current_state.value,
            "gates": {
                g.gate_id: {"complete": g.is_complete, "pct": g.completion_pct}
                for g in snapshot.gate_evaluations
            },
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
