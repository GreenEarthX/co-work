"""
GEX Bankability Engine — Core Logic
=====================================
12 stage gates, 9 bankability states, 8 capital unlock types.
Stateless evaluator: receives evidence + previous_state, returns snapshot.
in: gex_pf_engine/backend/app/core/bankability_engine.py
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE RULES VERSION
# ═══════════════════════════════════════════════════════════════════════════════
# Stamped into every snapshot so an auditor can answer: "which rules judged
# this project, on this date?" Bump on ANY change to GATES, EVIDENCE_META,
# severity logic, or applicability logic — and record it in the changelog.
#
# CHANGELOG
#   1.0.0              Original 12-gate registry. G1 = 5 items
#                      (grid study, queue, curtailment, water ×2), static
#                      deal_killers, no power-model or phase awareness.
#   2.0.0 (2026-06-12) G1 expanded to 16-item superset (A power access,
#                      B PPA procurement, C curtailment/dispatch, D water,
#                      E BTM generation). EVIDENCE_META introduced:
#                      power-model applicability (applicable items only in
#                      denominator), phase-aware severity escalation
#                      (warning → deal_killer at construction).
#   2.1.0 (2026-06-12) Financing-model scoping: lender gates (G4 offtake,
#                      G6 IE, G7 insurance, G8 model audit, G10 financial
#                      close) apply to PROJECT_FINANCE only. BALANCE_SHEET
#                      projects (prosumers, corporates) are not judged
#                      against third-party offtake / lender evidence; those
#                      gates are waived from state transitions and capital
#                      unlock arithmetic, and reported financing_applicable
#                      = false rather than silently failing.
#   2.1.1 (2026-06-12) Route fix: curtailment_assessment and
#                      dispatch_load_factor_production_impact routed to the
#                      project edit page (where ENGINEERING works the
#                      premise) instead of /dscr-sensitivity (a
#                      finance-restricted consequence screen a producer
#                      cannot act on). Severity/applicability unchanged.
#   2.2.0 (2026-09-25) Gate ids aligned with the platform registry
#                      (G1_GRID_WATER -> G1_GRID_UTILITIES_REALITY, etc.);
#                      personas / accountable_functions added. No change to
#                      what any gate requires.
#   3.0.0 (2026-09-25) BREAKING — the stronger bar. Decision recorded in
#                      docs/GEX-Twelve-Bankability-Gates.docx and in
#                      GEX_Bankability_Ambition_Gap_and_Remediation_Standard.
#                      Where a gate's name claims an achieved condition, its
#                      evidence now requires the achievement, not an intention:
#                      G9 permits GRANTED (not submitted), G10 CPs SATISFIED
#                      (not drafted), G11 tests PASSED (not planned), G8 audit
#                      OPINION (not engagement). Readiness gates stay readiness
#                      gates at the maturity their stage allows, and every
#                      readiness instrument reaches EXECUTED at G10.
#                      Introduces a MATURITY axis distinct from verification:
#                      a VERIFIED item counts only when its declared maturity
#                      meets REQUIRED_MATURITY. Undeclared maturity fails
#                      closed. 49 -> 77 evidence items; 26 keys retired (18 the engine
#                      scored, 8 only the platform registry declared), each with
#                      a named replacement in RETIRED_EVIDENCE. G1 unchanged
#                      except ppa_signed_or_term_sheet_evidence >= INDICATIVE.
#                      Gate evaluations gain an explicit `determination`.
#   4.0.0 (2026-09-27) BREAKING — every gate read through every party's eyes.
#                      Decision and evidence: docs/GEX-Twelve-Gates-Multi-Party-
#                      Review.docx. (1) Financing scope moves from GATES to ITEMS:
#                      only lender-protection items drop out for BALANCE_SHEET;
#                      G4 offtake, G7 insurance and G10 are no longer waived
#                      whole, G6 and G8 are (all their items protect lenders).
#                      (2) The offtake and the EPC are graded on commitment
#                      ladders O0–O7 and E0–E6, derived from evidence maturity
#                      plus structured commitment terms; G4 needs O4, G5 needs E4,
#                      and later states need O6/O7, effectiveness and E6.
#                      (3) Ten coherence checks compare commitments across
#                      contracts; a FAIL blocks its gate. (4) Post-FID triggers
#                      (power or support revoked, certification suspended,
#                      contractor insolvent) block the gates they undermine.
#                      (5) 16 evidence items added (77 -> 93): technology basis,
#                      FEED, licence guarantee, long-lead, EPC security,
#                      independent technical review, product qualification,
#                      seller-side offtake terms, certificates issued, deliveries
#                      accepted. (6) Every item carries lenses (PRODUCER,
#                      OFFTAKER, CAPITAL, CERTIFIER); OFFTAKER becomes a persona.
#                      (7) G1 renamed "Power, Utilities & Technology Basis".
#   4.2.0 (2026-10-28) STRICTER — can lower a state. JML: a gate whose items are
#                      all verified but whose cross-contract checks cannot run
#                      for lack of data is UNRESOLVED, not SATISFIED, and does
#                      not count toward the ladder. `unresolved_reasons` names
#                      the missing card fields. Only a FAIL used to hold a gate.
#   4.1.0 (2026-09-29) STRICTER — can lower a state. Evidence:
#                      docs/master-reconciliation/00_market_evidence_gate_timing.md
#                      in the platform repo. (1) COMMERCIALLY_PLAUSIBLE now also
#                      needs offtake terms (O2 or better) covering at least
#                      OFFTAKE_COVERAGE_MIN_PCT of planned output — the bar the EU
#                      Hydrogen Bank sets at application. Coverage is computed from
#                      the offtake card (new field planned_output_tonnes_per_year;
#                      EPC guaranteed capacity as fallback); unknown fails closed.
#                      (2) Capital types gain display labels (CAPITAL_TYPE_LABELS);
#                      SENIOR_DEBT_COMMITMENT reads "Senior debt credit approval
#                      (conditional)": every financing sampled separated credit
#                      approval, financial close and drawdown, and conditional
#                      commitments lapse. The identifier is unchanged.

EVIDENCE_RULES_VERSION = "4.2.0"


# ═══════════════════════════════════════════════════════════════════════════════
# MATURITY — a separate axis from verification
# ═══════════════════════════════════════════════════════════════════════════════
# Verification answers "is this document authentic and what it claims to be?"
# Maturity answers "how far has the underlying instrument progressed?" They are
# independent: a letter of intent can be perfectly authentic. Before 3.0.0 the
# only maturity signal was the evidence KEY'S NAME, so an LOI uploaded into a
# slot called "..._executed" and marked VERIFIED satisfied the slot — the engine
# never learned what had been uploaded.
#
# The submitter declares maturity; the verifier confirms or DOWNGRADES it and
# may never upgrade it (enforced on the platform write path). An item that
# declares no maturity cannot satisfy a maturity requirement.
MATURITY_LEVELS: list[str] = ["INTENT", "INDICATIVE", "AGREED", "EXECUTED", "EFFECTIVE"]

MATURITY_DEFINITIONS: dict[str, str] = {
    "INTENT":     "Plan, mandate, letter of intent, MOU, strategy, or application in preparation.",
    "INDICATIVE": "Term sheet, quotation, indication of terms, or application submitted.",
    "AGREED":     "Agreed-form document with all terms settled, not yet signed or granted.",
    "EXECUTED":   "Signed, bound, granted, issued or passed.",
    "EFFECTIVE":  "In force: conditions precedent satisfied, policy incepted, appeal period expired.",
}


def maturity_meets(declared: Optional[str], required: Optional[str]) -> bool:
    """True when `declared` is at or above `required`. Unknown fails closed."""
    if not required:
        return True
    if declared not in MATURITY_LEVELS:
        return False
    return MATURITY_LEVELS.index(declared) >= MATURITY_LEVELS.index(required)

# Financing models. PROJECT_FINANCE = SPV with external debt. BALANCE_SHEET =
# corporate / prosumer funding from its own balance sheet. Since rules 4.0.0 the
# difference is scoped per ITEM (EVIDENCE_SCOPE, below GATES), not per gate:
# 2.1.0 waived five whole gates for balance-sheet projects as "gates that exist
# purely to protect external capital providers", which also waived the offtake,
# construction insurance and the investment decision — things every producer
# needs, whoever funds it.
FINANCING_MODELS = ("PROJECT_FINANCE", "BALANCE_SHEET")


def _item_applies_financing(key: str, financing_model: Optional[str]) -> bool:
    """Lender-protection items apply only to PROJECT_FINANCE; everything else to all.
    Unknown financing (None) is legacy: every item applies."""
    if financing_model != "BALANCE_SHEET":
        return True
    return EVIDENCE_SCOPE.get(key) != "PROJECT_FINANCE"


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE METADATA — server-side policy for evidence items
# ═══════════════════════════════════════════════════════════════════════════════
# This registry is the AUTHORITATIVE source of evidence policy:
#   - applies_to:   which power models the item is relevant for
#                   (OFF_GRID_BTM | GRID_CONNECTED | HYBRID | ALL)
#   - severity:     consequence when the item is missing ("advisory" |
#                   "warning" | "deal_killer")
#   - escalates_at_construction: warning → deal_killer once the project phase
#                   is construction/commissioning/operating (capital at work)
#   - owner_function / blocked_action / route: who fixes it, what it holds
#                   hostage, and where it is worked (no dead ends)
# The frontend renders this; it must NOT define its own copy as policy.

_ESCALATION_PHASES = {"construction", "commissioning", "operating"}

EVIDENCE_META: dict[str, dict] = {
    # ── G0 ────────────────────────────────────────────────────────────────────
    "land_option_or_lease_executed": {
        "label": "Land Option or Lease Executed",
        "section": "A", "section_label": "Site Control",
        "applies_to": ["ALL"], "severity": "deal_killer", "escalates_at_construction": False,
        "owner_function": "LEGAL", "blocked_action": "Site control — no project without it",
        "route": "/projects/{project_id}/edit",
    },
    "zoning_compatibility_memo": {
        "label": "Zoning Compatibility Memo",
        "section": "A", "section_label": "Site Control",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "LEGAL", "blocked_action": "Planning permission pathway",
        "route": "/projects/{project_id}/edit",
    },
    "stakeholder_map_v1": {
        "label": "Stakeholder Map v1",
        "section": "B", "section_label": "Stakeholder & Community",
        "applies_to": ["ALL"], "severity": "advisory", "escalates_at_construction": False,
        "owner_function": "PROJECT", "blocked_action": "Social licence foundation",
        "route": "/projects/{project_id}/edit",
    },
    # ── G1 — A. Power Access (grid-connected / hybrid only) ──────────────────
    "grid_interconnection_study": {
        "label": "Grid Interconnection Study",
        "section": "A", "section_label": "Power Access",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "deal_killer", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Connection feasibility confirmation",
        "route": "/projects/{project_id}/edit",
    },
    "queue_position_evidence": {
        "label": "Grid Queue Position / Capacity Reservation",
        "section": "A", "section_label": "Power Access",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "ENGINEERING", "blocked_action": "COD timeline certainty",
        "route": "/projects/{project_id}/edit",
    },
    "grid_connection_cost_estimate": {
        "label": "Grid Connection Cost & Reinforcement Scope",
        "section": "A", "section_label": "Power Access",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "CAPEX floor accuracy",
        "route": "/finance-plant-builder",
    },
    "connection_date_cod_compatibility_memo": {
        "label": "Connection Date vs COD Compatibility Memo",
        "section": "A", "section_label": "Power Access",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "ENGINEERING", "blocked_action": "Schedule bankability",
        "route": "/projects/{project_id}/edit",
    },
    # ── G1 — B. Renewable Power Procurement (grid-connected / hybrid only) ───
    # Phase rule (shared with the project-edit contradiction engine): missing
    # PPA = warning in development, deal_killer once construction starts.
    "ppa_register": {
        "label": "PPA Register (counterparty, MW, €/MWh, tenor)",
        "section": "B", "section_label": "Renewable Power Procurement",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "SALES", "blocked_action": "RFNBO/45V additionality evidence; OPEX hedge",
        "route": "/projects/{project_id}/edit",
    },
    "ppa_signed_or_term_sheet_evidence": {
        "label": "Signed PPA / Term Sheet / LOI Evidence",
        "section": "B", "section_label": "Renewable Power Procurement",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "SALES", "blocked_action": "Electricity price hedge — dominant OPEX of electrolysis",
        "route": "/projects/{project_id}/edit",
    },
    "ppa_volume_load_coverage_analysis": {
        "label": "PPA Volume vs Plant Load Coverage Analysis",
        "section": "B", "section_label": "Renewable Power Procurement",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Hourly renewable matching for RFNBO",
        "route": "/projects/{project_id}/edit",
    },
    "ppa_tenor_debt_comparison": {
        "label": "PPA Tenor vs Debt / Offtake Tenor Comparison",
        "section": "B", "section_label": "Renewable Power Procurement",
        "applies_to": ["GRID_CONNECTED", "HYBRID"], "severity": "advisory", "escalates_at_construction": True,
        "owner_function": "FINANCE", "blocked_action": "Lender tenor mismatch risk",
        "route": "/dscr-sensitivity",
    },
    # ── G1 — C. Curtailment & Dispatch (all power models) ────────────────────
    # Routes lead where the WORK is done, in the owner function's reach.
    # Curtailment/dispatch are ENGINEERING evidence — they are worked on the
    # project's technical premise (edit page), not on /dscr-sensitivity,
    # which is a finance-restricted CONSEQUENCE screen a producer cannot act on.
    "curtailment_assessment": {
        "label": "Curtailment Assessment (grid node congestion + load profile)",
        "section": "C", "section_label": "Curtailment & Dispatch",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Availability factor; CFADS downside case",
        "route": "/projects/{project_id}/edit",
    },
    "dispatch_load_factor_production_impact": {
        "label": "Dispatch / Load Factor Impact on Production Volume",
        "section": "C", "section_label": "Curtailment & Dispatch",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Production volume bankability; offtake delivery obligations",
        "route": "/projects/{project_id}/edit",
    },
    # ── G1 — D. Water Supply & Permitting (all power models) ─────────────────
    "water_source_plan": {
        "label": "Water Source Plan (volume, cost, seasonal availability)",
        "section": "D", "section_label": "Water Supply",
        "applies_to": ["ALL"], "severity": "deal_killer", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Social licence; permitting pathway",
        "route": "/projects/{project_id}/edit",
    },
    "water_permit_pathway_memo": {
        "label": "Water Permit / Abstraction / Discharge Pathway",
        "section": "D", "section_label": "Water Supply",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "LEGAL", "blocked_action": "Construction permit; lender environmental covenant",
        "route": "/projects/{project_id}/edit",
    },
    # ── G1 — E. BTM Generation (off-grid / hybrid only) ──────────────────────
    "btm_generation_asset_evidence": {
        "label": "BTM Generation Asset Spec & CAPEX",
        "section": "E", "section_label": "BTM Generation",
        "applies_to": ["OFF_GRID_BTM", "HYBRID"], "severity": "deal_killer", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Power supply premise — electricity is CAPEX for off-grid",
        "route": "/finance-plant-builder",
    },
    "generation_yield_study": {
        "label": "Generation Yield Study (P50/P90)",
        "section": "E", "section_label": "BTM Generation",
        "applies_to": ["OFF_GRID_BTM", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "ENGINEERING", "blocked_action": "Production volume bankability; lender P90 case",
        "route": "/finance-plant-builder",
    },
    "grid_independence_note": {
        "label": "Grid-Independence Design Note",
        "section": "E", "section_label": "BTM Generation",
        "applies_to": ["OFF_GRID_BTM", "HYBRID"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Evidence that no interconnect is required (or surplus-export scope)",
        "route": "/projects/{project_id}/edit",
    },
    "backup_construction_power_plan": {
        "label": "Backup / Construction Power Plan",
        "section": "E", "section_label": "BTM Generation",
        "applies_to": ["OFF_GRID_BTM", "HYBRID"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "PROJECT", "blocked_action": "Construction schedule; commissioning power",
        "route": "/projects/{project_id}/edit",
    },
    # ── Rules 4.0.0 — the producer's questions ───────────────────────────────
    # G0 — is the site fit for the PROCESS, not only leased?
    "site_technical_suitability": {
        "label": "Site Technical Suitability (major-hazard siting, geotechnics, logistics access)",
        "section": "C", "section_label": "Site Suitability",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": True,
        "owner_function": "ENGINEERING", "blocked_action": "Process safety distances and product export route",
        "route": "/projects/{project_id}/edit",
    },
    # G1 — F. Technology Basis. Before 4.0.0 the state this gate leads to was
    # called TECHNICALLY_PLAUSIBLE and no item asked whether the conversion
    # technology works at the intended scale; the first independent look came
    # at G6, from the lenders' engineer, after offtake and EPC.
    "technology_maturity_dossier": {
        "label": "Technology Maturity Dossier (readiness level, reference plants, operating hours, scale-up factor)",
        "section": "F", "section_label": "Technology Basis",
        "applies_to": ["ALL"], "severity": "deal_killer", "escalates_at_construction": False,
        "owner_function": "ENGINEERING",
        "blocked_action": "Technical plausibility at this scale — lenders weigh deployed fleet over readiness labels",
        "route": "/projects/{project_id}/edit",
    },
    "technology_licensor_term_sheet": {
        "label": "Technology Licensor Identified — Term Sheet",
        "section": "F", "section_label": "Technology Basis",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Process design basis and the path to a performance guarantee",
        "route": "/projects/{project_id}/edit",
    },
    "integrated_mass_energy_balance": {
        "label": "Integrated Mass & Energy Balance at Design Basis (incl. hydrogen buffer and turndown vs power profile)",
        "section": "F", "section_label": "Technology Basis",
        "applies_to": ["ALL"], "severity": "warning", "escalates_at_construction": False,
        "owner_function": "ENGINEERING", "blocked_action": "Real output vs nameplate — what the plant can actually sell",
        "route": "/projects/{project_id}/edit",
    },
}


def _evidence_applies(key: str, power_model: Optional[str]) -> bool:
    """An item applies unless its metadata restricts it to other power models."""
    meta = EVIDENCE_META.get(key)
    if meta is None or "ALL" in meta["applies_to"]:
        return True
    if not power_model:
        return True  # unknown power model — score everything (legacy behaviour)
    return power_model in meta["applies_to"]


def _effective_severity(key: str, gate: dict, project_phase: Optional[str]) -> str:
    """Phase-aware severity: warnings escalate to deal_killer once capital is at work."""
    meta = EVIDENCE_META.get(key)
    if meta is None:
        # Unannotated key — fall back to the gate's static deal_killers list.
        return "deal_killer" if key in gate.get("deal_killers", []) else "warning"
    severity = meta["severity"]
    if (
        severity == "warning"
        and meta.get("escalates_at_construction")
        and project_phase in _ESCALATION_PHASES
    ):
        return "deal_killer"
    return severity


# ═══════════════════════════════════════════════════════════════════════════════
# GATE DEFINITIONS — the 12 gates of project bankability
# ═══════════════════════════════════════════════════════════════════════════════

GATES = [
    {
        "gate_id": "G0_SITE_RIGHTS",
        "gate_name": "Site Rights & Social License",
        "owners": ["PRODUCER", "EXECUTIVE"],
        # Two distinct ownership axes, identical in both registries.
        # personas = who SEES the gate; accountable_functions = who DOES the work.
        "personas": ["PRODUCER", "EXECUTIVE"],
        "accountable_functions": ["PROJECT", "LEGAL"],
        "required_evidence": [
            "land_option_or_lease_executed",
            "zoning_compatibility_memo",
            "stakeholder_map_v1",
            "site_technical_suitability",
        ],
        "deal_killers": ["land_option_or_lease_executed"],
        "unlocks_capital": ["GRANTS_TA"],
        "unlocks_state": "TECHNICALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G1_GRID_UTILITIES_REALITY",
        "gate_name": "Power, Utilities & Technology Basis",
        "owners": ["PRODUCER"],
        # Two distinct ownership axes, identical in both registries.
        # personas = who SEES the gate; accountable_functions = who DOES the work.
        "personas": ["PRODUCER"],
        "accountable_functions": ["ENGINEERING", "PROJECT", "FINANCE"],
        # Superset across power models. EVIDENCE_META.applies_to filters which
        # items are scored for a given project — OFF_GRID_BTM is never asked
        # for a grid study or a PPA; GRID_CONNECTED is never asked for a BTM
        # yield study. Gate id stays G1_GRID_UTILITIES_REALITY (state machine, ABAC, and
        # persona scoping all reference it).
        "required_evidence": [
            # A. Power Access (GRID_CONNECTED / HYBRID)
            "grid_interconnection_study",
            "queue_position_evidence",
            "grid_connection_cost_estimate",
            "connection_date_cod_compatibility_memo",
            # B. Renewable Power Procurement (GRID_CONNECTED / HYBRID)
            "ppa_register",
            "ppa_signed_or_term_sheet_evidence",
            "ppa_volume_load_coverage_analysis",
            "ppa_tenor_debt_comparison",
            # C. Curtailment & Dispatch (ALL)
            "curtailment_assessment",
            "dispatch_load_factor_production_impact",
            # D. Water Supply & Permitting (ALL)
            "water_source_plan",
            "water_permit_pathway_memo",
            # E. BTM Generation (OFF_GRID_BTM / HYBRID)
            "btm_generation_asset_evidence",
            "generation_yield_study",
            "grid_independence_note",
            "backup_construction_power_plan",
            # F. Technology Basis (ALL) — rules 4.0.0
            "technology_maturity_dossier",
            "technology_licensor_term_sheet",
            "integrated_mass_energy_balance",
        ],
        # Static fallback only — effective deal killers come from EVIDENCE_META
        # severity + phase escalation, scoped to applicable items.
        "deal_killers": ["grid_interconnection_study", "water_source_plan", "btm_generation_asset_evidence",
                         "technology_maturity_dossier"],
        "unlocks_capital": ["SEED_VC_ANGEL"],
        "unlocks_state": "TECHNICALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G2_CERTIFICATION_PATH_LOCKED",
        "gate_name": "Green Certification Pathway",
        # READINESS gate by name ("pathway", "path locked") — not final
        # certification. Carries the RFNBO additionality pillar the platform
        # registry had dropped, and the MRV plan the runtime had lacked.
        "owners": ["REGULATOR", "OFFTAKER"],
        "personas": ["REGULATOR", "OFFTAKER"],
        "accountable_functions": ["ENGINEERING", "LEGAL"],
        "required_evidence": [
            "certification_scheme_selection",
            "additionality_evidence",
            "power_sourcing_alignment_note",
            "ghg_methodology_memo",
            "mrv_plan_v1",
            # 4.0.0 — can the product be qualified at all (ASTM annex, ISO spec)?
            "product_qualification_pathway",
        ],
        "deal_killers": [
            "certification_scheme_selection",
            "additionality_evidence",
        ],
        "unlocks_capital": [],
        "unlocks_state": "COMMERCIALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G3_INPUTS_SECURED",
        "gate_name": "Feedstock & Logistics Terms",
        # READINESS gate. Supply must be at INDICATIVE maturity — terms from a
        # named counterparty with volume, quality and tenor — which is stronger
        # than the LOI the runtime accepted and the "strategy" the registry
        # accepted. Execution is required at G10 (all_major_contracts_executed):
        # a CO2 supplier will not sign before the offtake that gives the plant
        # a reason to exist. The id keeps "SECURED" for identifier stability;
        # the name and evidence state what is actually tested.
        "owners": ["PRODUCER"],
        "personas": ["PRODUCER"],
        "accountable_functions": ["ENGINEERING", "PROJECT", "FINANCE"],
        "required_evidence": [
            "feedstock_supply_agreement",
            "transport_logistics_study",
            "storage_plan",
            "feedstock_spec_eligibility",
        ],
        "deal_killers": [
            "feedstock_supply_agreement",
        ],
        "unlocks_capital": ["STRATEGIC_EQUITY"],
        "unlocks_state": "COMMERCIALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G4_OFFTAKE_BANKABLE",
        "gate_name": "Binding Offtake",
        # ACHIEVEMENT gate: "binding" means executed. Carries the lender
        # protection terms, plus the offtaker credit assessment the registry had
        # dropped and the price-review mechanism — the clause through which an
        # offtaker moves a goalpost after signature.
        # 4.0.0: no longer waived for balance-sheet projects — only its lender-
        # protection items are (EVIDENCE_SCOPE). The contract is graded on the
        # offtake ladder and must reach O4 (binding, with a longstop if
        # conditional); the seller-side terms are now evidence too.
        "owners": ["FINANCE", "OFFTAKER"],
        "personas": ["FINANCE", "OFFTAKER"],
        "accountable_functions": ["SALES", "LEGAL", "FINANCE"],
        "required_evidence": [
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
        "deal_killers": [
            "binding_offtake_contract_executed",
            "offtake_credit_assessment",
        ],
        "unlocks_capital": ["PROJECT_EQUITY"],
        "unlocks_state": "BUILDABLE",
    },
    {
        "gate_id": "G5_EPC_RISK_PRICED",
        "gate_name": "EPC Risk Priced",
        # ACHIEVEMENT at the maturity the stage allows: the EPC price, schedule
        # and performance regime are AGREED (agreed form), not merely heads of
        # terms. Execution is required at G10. performance_test_protocol lives
        # here — the protocol is agreed with the EPC; passing it is G11.
        # 4.0.0: graded on the EPC ladder (must reach E4); FEED completion, the
        # licence guarantee, long-lead items, the security package and an
        # independent technical review — for every project, not only
        # project-financed ones — are now evidence.
        "owners": ["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        "personas": ["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        "accountable_functions": ["PROJECT", "ENGINEERING", "LEGAL"],
        "required_evidence": [
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
        "deal_killers": [
            "epc_contract_fixed_price_or_capped_gmp",
            "liquidated_damages_schedule",
            "feed_complete_class3",
        ],
        "unlocks_capital": [],
        "unlocks_state": "BUILDABLE",
    },
    {
        "gate_id": "G6_IE_SIGNOFF",
        "gate_name": "Independent Engineer Sign-off",
        # ACHIEVEMENT gate: the IE report is ISSUED (final, not draft), with the
        # component opinions a lender relies on. An appointment letter is not a
        # sign-off. The single most independence-critical gate: the producer
        # must never verify its own items here.
        "owners": ["FINANCE", "REGULATOR"],
        "personas": ["FINANCE", "REGULATOR"],
        "accountable_functions": ["INDEPENDENT_ENGINEER", "LENDERS"],
        "required_evidence": [
            "ie_report_issued",
            "energy_balance_verified",
            "capex_opinion_reasonableness",
            "opex_opinion_reasonableness",
            "completion_test_definitions",
        ],
        "deal_killers": [
            "ie_report_issued",
            "energy_balance_verified",
        ],
        "unlocks_capital": ["DFI_MEZZ_GUARANTEES"],
        "unlocks_state": "STRUCTURALLY_BANKABLE",
    },
    {
        "gate_id": "G7_INSURANCE_BOUND",
        "gate_name": "Insurability Confirmed",
        # READINESS gate at this stage. STRUCTURALLY_BANKABLE precedes credit
        # approval, and cover cannot be BOUND with lenders named as loss payee
        # before lenders have approved — the platform registry's version of this
        # gate was a financial-close checklist placed two states too early, and
        # duplicated G10's insurance certificates. Insurers must have QUOTED the
        # programme (not merely been mandated); binding is a G10 condition. The
        # id keeps "BOUND" for identifier stability; the name states the test.
        "owners": ["FINANCE"],
        "personas": ["FINANCE"],
        "accountable_functions": ["TREASURY", "LEGAL", "LENDERS"],
        "required_evidence": [
            "insurance_term_sheet",
            "insurance_market_report",
            "deductibles_accepted",
            "exclusions_register_reviewed",
            "foak_exclusions_warranty_backstop",
        ],
        "deal_killers": [
            "insurance_term_sheet",
        ],
        "unlocks_capital": [],
        "unlocks_state": "STRUCTURALLY_BANKABLE",
    },
    {
        "gate_id": "G8_AUDIT_GRADE_MODEL",
        "gate_name": "Audit-Grade Financial Model",
        # ACHIEVEMENT gate: "audit-grade" means AUDITED. Before 3.0.0 neither
        # definition required a completed audit — the runtime accepted an
        # engagement letter and the registry had no audit item at all.
        "owners": ["FINANCE"],
        "personas": ["FINANCE"],
        "accountable_functions": ["FINANCE", "LENDERS"],
        "required_evidence": [
            "base_case_model",
            "model_audit_opinion",
            "downside_cases",
            "covenant_suite_defined",
            "dsra_maintenance_reserve_logic",
            "hedging_plan",
            "model_consistency_with_ie",
        ],
        "deal_killers": [
            "base_case_model",
            "model_audit_opinion",
        ],
        "unlocks_capital": ["SENIOR_DEBT_COMMITMENT"],
        "unlocks_state": "CREDIT_APPROVED",
    },
    {
        "gate_id": "G9_PERMITS_SAFE",
        "gate_name": "Permits Granted & Appeal Risk Managed",
        # ACHIEVEMENT gate: the pre-construction consents are GRANTED. The
        # construction permit is named explicitly rather than folded into
        # "ancillary". The OPERATING permit is a pathway here and must be in
        # force at G11 — it cannot exist before the plant does.
        "owners": ["PRODUCER", "REGULATOR", "OFFTAKER"],
        "personas": ["PRODUCER", "REGULATOR", "OFFTAKER"],
        "accountable_functions": ["PROJECT", "LEGAL"],
        "required_evidence": [
            "eia_permit_granted",
            "construction_permit_granted",
            "ancillary_permits_granted",
            "legal_opinion_on_appeal_risk",
            "operating_permit_pathway",
            "stakeholder_management_plan_v2",
        ],
        "deal_killers": [
            "eia_permit_granted",
            "construction_permit_granted",
        ],
        "unlocks_capital": [],
        "unlocks_state": "FINANCEABLE",
    },
    {
        "gate_id": "G10_FINANCIAL_CLOSE_CP",
        "gate_name": "Financial Close",
        # ACHIEVEMENT gate: close has HAPPENED. CPs satisfied, equity in, reserve
        # funded, security perfected, insurance bound and incepted, legal
        # opinions issued, and every readiness instrument from G1, G3, G5 and G7
        # now executed. This is where the ladder turns terms into commitments.
        # 4.0.0: the investment-decision lock applies to every project; only the
        # financing conditions (CPs, reserve, security, lenders' opinions) are
        # project-finance scope. Offtake must be effective and EPC at E6.
        "owners": ["FINANCE", "OFFTAKER"],
        "personas": ["FINANCE", "OFFTAKER"],
        "accountable_functions": ["LENDERS", "LEGAL", "TREASURY", "FINANCE"],
        "required_evidence": [
            "cp_checklist_completed",
            "equity_injected",
            "dsra_funded",
            "security_package_perfected",
            "insurance_certificates_delivered",
            "all_major_contracts_executed",
            "legal_opinions_issued",
            "om_contract_or_organisation",
        ],
        "deal_killers": [
            "cp_checklist_completed",
            "equity_injected",
            "security_package_perfected",
            "all_major_contracts_executed",
            "legal_opinions_issued",
        ],
        "unlocks_capital": ["DEBT_DRAWDOWN"],
        "unlocks_state": "FINANCEABLE",
    },
    {
        "gate_id": "G11_COD_STABILIZATION",
        "gate_name": "COD & Stabilization",
        # ACHIEVEMENT gate, and the terminal one, so a stabilization period
        # blocks nothing downstream. Tests PASSED and COD CERTIFIED (not
        # planned); the operating permit IN FORCE; a stable operating record,
        # which is what refinancing eligibility actually rests on.
        # 4.0.0: a certificate must actually be issued and the offtaker must
        # have accepted on-specification deliveries — what the buyer pays for.
        "owners": ["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        "personas": ["PRODUCER", "EXECUTIVE", "OFFTAKER"],
        "accountable_functions": ["PROJECT", "ENGINEERING", "FINANCE"],
        "required_evidence": [
            "cod_certificate",
            "performance_tests_passed",
            "operating_permit_effective",
            "mrv_reporting_live",
            "six_to_twelve_months_stable_ops",
            "certificates_issued",
            "first_deliveries_accepted",
        ],
        "deal_killers": [
            "cod_certificate",
            "performance_tests_passed",
            "operating_permit_effective",
            "certificates_issued",
        ],
        "unlocks_capital": ["REFINANCE_BONDS_INFRA"],
        "unlocks_state": "OPERATIONAL",
    },
]


# Minimum maturity per evidence item. Only INSTRUMENTS carry one — contracts,
# permits, policies, opinions, certificates, funding events. Studies, analyses,
# plans and memos are either done or not; verification covers them.
REQUIRED_MATURITY: dict[str, str] = {
    # G0
    "land_option_or_lease_executed":         "EXECUTED",
    # G1 — the only G1 change in 3.0.0: the key's own name admits a term sheet
    # and no weaker, so an LOI no longer satisfies it.
    "ppa_signed_or_term_sheet_evidence":     "INDICATIVE",
    # G3
    "feedstock_supply_agreement":            "INDICATIVE",
    # G4
    "binding_offtake_contract_executed":     "EXECUTED",
    "credit_support_package":                "EXECUTED",
    # G1 — 4.0.0
    "technology_licensor_term_sheet":        "INDICATIVE",
    # G5
    "epc_contract_fixed_price_or_capped_gmp": "AGREED",
    "oem_warranties":                        "AGREED",
    "technology_licence_process_guarantee":  "AGREED",
    "long_lead_items_reserved":              "AGREED",
    "epc_security_package":                  "AGREED",
    # G6
    "ie_report_issued":                      "EXECUTED",
    # G7
    "insurance_term_sheet":                  "INDICATIVE",
    # G8
    "model_audit_opinion":                   "EXECUTED",
    # G9
    "eia_permit_granted":                    "EXECUTED",
    "construction_permit_granted":           "EXECUTED",
    "ancillary_permits_granted":             "EXECUTED",
    "legal_opinion_on_appeal_risk":          "EXECUTED",
    # G10
    "cp_checklist_completed":                "EFFECTIVE",
    "equity_injected":                       "EXECUTED",
    "dsra_funded":                           "EXECUTED",
    "security_package_perfected":            "EFFECTIVE",
    "insurance_certificates_delivered":      "EFFECTIVE",
    "all_major_contracts_executed":          "EXECUTED",
    "legal_opinions_issued":                 "EXECUTED",
    "om_contract_or_organisation":           "EXECUTED",
    # G11
    "cod_certificate":                       "EXECUTED",
    "performance_tests_passed":              "EXECUTED",
    "operating_permit_effective":            "EFFECTIVE",
    "certificates_issued":                   "EXECUTED",
    "first_deliveries_accepted":             "EXECUTED",
}


# ─── Item metadata for G2–G11 ─────────────────────────────────────────────────
# Before 3.0.0 only the 19 items of G0/G1 carried a label, an owning function,
# the action they block and the place they are worked; the other 30 fell back to
# a title-cased key owned by "PROJECT" with no route — a dead end for anyone
# trying to clear them. Owning functions here draw from the same vocabulary as
# each gate's accountable_functions. Severity is DERIVED from the gate's own
# deal_killers list below, so adding metadata changes no scoring.
_G2_G11_META: list[tuple[str, str, str, str, str, str]] = [
    # key, label, section, section_label, owner_function, blocked_action
    ("certification_scheme_selection", "Certification Scheme Selected (RFNBO / RED III / 45V / ISCC)", "A", "Scheme & Eligibility", "LEGAL", "Green price and subsidy eligibility"),
    ("additionality_evidence", "Additionality Evidence (generator age, no state aid)", "A", "Scheme & Eligibility", "ENGINEERING", "RFNBO eligibility — a failed pillar forfeits the green premium"),
    ("power_sourcing_alignment_note", "Temporal & Geographic Correlation Alignment", "A", "Scheme & Eligibility", "ENGINEERING", "RFNBO correlation pillars; hourly matching from 1 Jan 2030"),
    ("ghg_methodology_memo", "GHG Methodology Memo", "B", "Carbon Accounting", "ENGINEERING", "Carbon-intensity verdict against the scheme threshold"),
    ("mrv_plan_v1", "MRV Plan v1 (monitoring, reporting, verification)", "B", "Carbon Accounting", "ENGINEERING", "Certificate issuance once operating"),
    ("feedstock_supply_agreement", "Feedstock Supply Terms (volume, quality, tenor)", "A", "Feedstock", "PROJECT", "Production premise — no feedstock, no molecule"),
    ("transport_logistics_study", "Transport & Logistics Study", "B", "Logistics", "ENGINEERING", "Delivered cost and offtake delivery obligations"),
    ("storage_plan", "Storage Plan", "B", "Logistics", "ENGINEERING", "Throughput and inventory assumptions"),
    ("binding_offtake_contract_executed", "Executed Offtake Agreement", "A", "Offtake Contract", "SALES", "The revenue line — no bankable cash flow without it"),
    ("offtake_credit_assessment", "Offtaker Credit Assessment", "A", "Offtake Contract", "FINANCE", "Lender acceptance of the counterparty"),
    ("credit_support_package", "Credit Support (parent guarantee / letter of credit)", "A", "Offtake Contract", "FINANCE", "Counterparty risk for a sub-investment-grade buyer"),
    ("take_or_pay_floor", "Take-or-Pay Floor", "B", "Bankability Terms", "LEGAL", "Volume certainty in the lender case"),
    ("termination_payment_formula", "Termination Payment Formula", "B", "Bankability Terms", "LEGAL", "Debt recovery on early termination"),
    ("assignment_rights", "Assignment to Lenders", "B", "Bankability Terms", "LEGAL", "Security over the offtake contract"),
    ("step_in_rights", "Lender Step-in Rights", "B", "Bankability Terms", "LEGAL", "Lender cure on sponsor default"),
    ("hedgeable_pricing_index", "Hedgeable Pricing Index", "B", "Bankability Terms", "FINANCE", "Price-risk hedging in the lender case"),
    ("price_review_mechanism_memo", "Price Review / Reopener Mechanism", "B", "Bankability Terms", "LEGAL", "Revenue stability — the clause through which terms move after signature"),
    ("epc_contract_fixed_price_or_capped_gmp", "EPC Contract — Fixed Price or Capped GMP (agreed form)", "A", "EPC Contract", "PROJECT", "Capital-cost certainty"),
    ("liquidated_damages_schedule", "Delay & Performance Liquidated Damages", "A", "EPC Contract", "LEGAL", "Construction risk transfer"),
    ("date_certain_schedule", "Date-Certain Construction Schedule", "A", "EPC Contract", "PROJECT", "COD certainty and debt sizing"),
    ("performance_test_protocol", "Performance Test Protocol", "B", "Performance Regime", "ENGINEERING", "Definition of what the plant must prove at COD"),
    ("interface_matrix", "Interface Matrix (EPC / OEM / balance of plant)", "B", "Performance Regime", "ENGINEERING", "Uncovered interface risk"),
    ("oem_warranties", "OEM Warranties (agreed form)", "B", "Performance Regime", "ENGINEERING", "Stack and equipment performance risk"),
    ("epc_contractor_dd", "EPC Contractor Due Diligence", "C", "Contractor", "PROJECT", "Contractor capability and balance sheet"),
    ("ie_report_issued", "Independent Engineer Report — Issued (final)", "A", "IE Report", "INDEPENDENT_ENGINEER", "Lender reliance on the technical basis"),
    ("energy_balance_verified", "Energy Balance Verified by the IE", "A", "IE Report", "INDEPENDENT_ENGINEER", "Production and specific-energy assumptions in the lender case"),
    ("capex_opinion_reasonableness", "IE Opinion — CAPEX Reasonableness", "B", "IE Opinions", "INDEPENDENT_ENGINEER", "Debt sizing on capital cost"),
    ("opex_opinion_reasonableness", "IE Opinion — OPEX Reasonableness", "B", "IE Opinions", "INDEPENDENT_ENGINEER", "CFADS and DSCR"),
    ("completion_test_definitions", "Completion Test Definitions (IE-agreed)", "B", "IE Opinions", "INDEPENDENT_ENGINEER", "Release of sponsor completion support"),
    ("insurance_term_sheet", "Insurance Programme Terms — Quoted by Insurers", "A", "Programme", "TREASURY", "Insurability of construction and operating risk"),
    ("insurance_market_report", "Broker Market Report", "A", "Programme", "TREASURY", "Evidence the market will write the risk"),
    ("deductibles_accepted", "Deductible Levels Accepted by Lenders", "B", "Lender Terms", "TREASURY", "Uninsured loss retained by the project"),
    ("exclusions_register_reviewed", "Exclusions Register Reviewed", "B", "Lender Terms", "LEGAL", "Risks the programme will not pay for"),
    ("base_case_model", "Locked Base-Case Financial Model", "A", "Model", "FINANCE", "Every DSCR a lender reads"),
    ("model_audit_opinion", "Model Audit Opinion — Issued", "A", "Model", "FINANCE", "Credit-committee reliance on the model"),
    ("downside_cases", "Lender Downside Cases", "B", "Cases & Covenants", "FINANCE", "Debt sizing under stress"),
    ("covenant_suite_defined", "Covenant Suite Defined", "B", "Cases & Covenants", "FINANCE", "Lock-up and default triggers"),
    ("dsra_maintenance_reserve_logic", "DSRA & Maintenance Reserve Logic", "B", "Cases & Covenants", "FINANCE", "Liquidity protection"),
    ("hedging_plan", "Hedging Plan (rates, FX, power)", "B", "Cases & Covenants", "TREASURY", "Market-risk exposure in the lender case"),
    ("model_consistency_with_ie", "Model Consistent with IE Findings", "C", "Consistency", "FINANCE", "Convergence of the model with the independent technical basis"),
    ("eia_permit_granted", "EIA / Environmental Permit — Granted", "A", "Consents", "LEGAL", "Licence to build"),
    ("construction_permit_granted", "Construction Permit — Granted", "A", "Consents", "LEGAL", "Licence to build"),
    ("ancillary_permits_granted", "Ancillary Permits — Granted", "A", "Consents", "LEGAL", "Construction start"),
    ("legal_opinion_on_appeal_risk", "Legal Opinion on Appeal Risk", "B", "Appeal Risk", "LEGAL", "Lender acceptance of challenge risk"),
    ("operating_permit_pathway", "Operating Permit Pathway", "B", "Appeal Risk", "LEGAL", "Lawful operation after COD"),
    ("stakeholder_management_plan_v2", "Stakeholder Management Plan v2", "C", "Social Licence", "PROJECT", "Social licence through construction"),
    ("cp_checklist_completed", "Conditions Precedent Satisfied", "A", "Closing", "LEGAL", "First drawdown"),
    ("equity_injected", "Funding Committed (equity injected, or board-approved funding)", "A", "Closing", "FINANCE", "Money to build — debt-to-equity ratio at close where project-financed"),
    ("dsra_funded", "Debt Service Reserve Funded", "A", "Closing", "TREASURY", "Liquidity from day one"),
    ("security_package_perfected", "Security Package Perfected", "A", "Closing", "LEGAL", "Lender recourse"),
    ("insurance_certificates_delivered", "Insurance Bound & Certificates Delivered (lenders as loss payee where project-financed)", "B", "Insurance at Close", "TREASURY", "Cover in force from construction start"),
    ("all_major_contracts_executed", "All Major Project Contracts Executed (PPA, feedstock, EPC, O&M, offtake)", "B", "Contracts", "LEGAL", "Every readiness term from G1, G3, G5 and G7 becomes a commitment"),
    ("legal_opinions_issued", "Legal Opinions — Issued", "B", "Contracts", "LEGAL", "Enforceability of the finance documents"),
    ("cod_certificate", "COD / Taking-Over Certificate", "A", "Completion", "ENGINEERING", "Term conversion and the end of construction risk"),
    ("performance_tests_passed", "Performance Tests Passed", "A", "Completion", "ENGINEERING", "Proof of the performance the plant was financed on"),
    ("operating_permit_effective", "Operating Permit — In Force", "A", "Completion", "LEGAL", "Lawful operation"),
    ("mrv_reporting_live", "MRV Reporting Live", "B", "Operations", "ENGINEERING", "Certificate issuance and green revenue"),
    ("six_to_twelve_months_stable_ops", "6–12 Months Stable Operation", "B", "Operations", "ENGINEERING", "Refinancing eligibility"),
    # ── Rules 4.0.0 — the producer's and offtaker's questions ────────────────
    ("product_qualification_pathway", "Product Qualification Pathway (spec standard and annex status, e.g. ASTM D7566, ISO 6583)", "C", "Product Qualification", "ENGINEERING", "A saleable fuel — methanol-to-jet only cleared its ASTM milestone in June 2026"),
    ("feedstock_spec_eligibility", "Feedstock Specification & Eligibility Matched to Design Basis and Certification Scheme", "C", "Feedstock Eligibility", "ENGINEERING", "Licensor guarantees assume a feedstock spec; certification assumes an eligible source"),
    ("offtake_seller_obligations", "Seller-Side Offtake Terms Reviewed (delivery, specification, delay and shortfall caps, certification warranty, longstop)", "C", "Seller Obligations", "LEGAL", "The producer's ability to perform what it sells"),
    ("feed_complete_class3", "FEED Complete — AACE Class 3 or Better", "D", "Definition & Technology", "ENGINEERING", "An EPC price nobody can defend without a defined plant"),
    ("technology_licence_process_guarantee", "Technology Licence & Process Performance Guarantee (or equivalent wrap)", "D", "Definition & Technology", "ENGINEERING", "Who pays if the process under-performs"),
    ("long_lead_items_reserved", "Long-Lead Items Reserved", "D", "Definition & Technology", "PROJECT", "Schedule — electrolysers, compressors and reactors set the critical path"),
    ("epc_security_package", "EPC Security Package & Damage Caps (performance bond, parent guarantee, retention)", "E", "Security & Review", "LEGAL", "A guarantee is only as good as what stands behind it"),
    ("independent_technical_review", "Independent Technical Review of FEED", "E", "Security & Review", "INDEPENDENT_ENGINEER", "An independent technical view before binding offtake and EPC, whoever funds the plant"),
    ("foak_exclusions_warranty_backstop", "First-of-a-Kind Exclusions & OEM Warranty Backstop Reviewed", "C", "Producer Cover", "TREASURY", "Technology failure the programme will not pay for; warranties an insolvent OEM cannot honour"),
    ("om_contract_or_organisation", "O&M Contract or Operating Organisation in Place", "C", "Operations Readiness", "PROJECT", "Somebody able to run the plant on day one"),
    ("certificates_issued", "Certification Audit Passed & First Certificates / Proofs of Sustainability Issued", "C", "Buyer Acceptance", "ENGINEERING", "The attribute the offtaker pays the premium for"),
    ("first_deliveries_accepted", "First On-Specification Deliveries Accepted by the Offtaker", "C", "Buyer Acceptance", "SALES", "Proof the plant makes what the buyer contracted"),
]

_DK = {k for g in GATES for k in g["deal_killers"]}
for _key, _label, _sec, _sec_label, _owner, _blocked in _G2_G11_META:
    EVIDENCE_META[_key] = {
        "label": _label,
        "section": _sec,
        "section_label": _sec_label,
        "applies_to": ["ALL"],
        "severity": "deal_killer" if _key in _DK else "warning",
        "escalates_at_construction": False,
        "owner_function": _owner,
        "blocked_action": _blocked,
        "route": "/stage-gates",
    }


# Evidence keys removed from the gates in 3.0.0, each with what replaces it.
# Rows keyed on these remain in the store as history — they are true records of
# what happened — but no gate scores them. A retired key is never silently
# re-labelled as its replacement: an EIA *submission* must not become an EIA
# *grant*, which is exactly the false positive 3.0.0 exists to remove.
RETIRED_EVIDENCE: dict[str, dict[str, str]] = {
    # previously scored by the runtime engine
    "feedstock_supply_loi":            {"gate": "G3_INPUTS_SECURED",      "replaced_by": "feedstock_supply_agreement",             "reason": "An LOI is an intention; G3 requires indicative terms."},
    "binding_offtake_term_sheet":      {"gate": "G4_OFFTAKE_BANKABLE",    "replaced_by": "binding_offtake_contract_executed",      "reason": "A term sheet is not binding offtake."},
    "epc_contract_heads_of_terms":     {"gate": "G5_EPC_RISK_PRICED",     "replaced_by": "epc_contract_fixed_price_or_capped_gmp", "reason": "Heads of terms do not price risk; G5 requires the agreed form."},
    "performance_guarantees_draft":    {"gate": "G5_EPC_RISK_PRICED",     "replaced_by": "liquidated_damages_schedule",            "reason": "Guarantees and LDs are settled in the agreed-form EPC."},
    "ie_appointment_letter":           {"gate": "G6_IE_SIGNOFF",          "replaced_by": "ie_report_issued",                       "reason": "An appointment is not a sign-off."},
    "ie_technical_model_review":       {"gate": "G6_IE_SIGNOFF",          "replaced_by": "energy_balance_verified",                "reason": "Replaced by the IE's specific technical opinions."},
    "ie_site_visit_report":            {"gate": "G6_IE_SIGNOFF",          "replaced_by": "ie_report_issued",                       "reason": "Site findings are contained in the issued report."},
    "insurance_broker_mandate":        {"gate": "G7_INSURANCE_BOUND",     "replaced_by": "insurance_term_sheet",                   "reason": "A mandate is not evidence of insurability."},
    "financial_model_v1":              {"gate": "G8_AUDIT_GRADE_MODEL",   "replaced_by": "base_case_model",                        "reason": "Renamed to the locked base case."},
    "model_audit_engagement":          {"gate": "G8_AUDIT_GRADE_MODEL",   "replaced_by": "model_audit_opinion",                    "reason": "An engagement is not an audit."},
    "sensitivity_analysis":            {"gate": "G8_AUDIT_GRADE_MODEL",   "replaced_by": "downside_cases",                         "reason": "Lender downside cases subsume one-factor sensitivities."},
    "eia_submission":                  {"gate": "G9_PERMITS_SAFE",        "replaced_by": "eia_permit_granted",                     "reason": "A submission is not a permit."},
    "construction_permit_application": {"gate": "G9_PERMITS_SAFE",        "replaced_by": "construction_permit_granted",            "reason": "An application is not a permit."},
    "cp_checklist_draft":              {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "cp_checklist_completed",                 "reason": "A draft checklist is not close."},
    "legal_opinions_draft":            {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "legal_opinions_issued",                  "reason": "Draft opinions are not a closing condition met."},
    "security_package_structure":      {"gate": "G10_FINANCIAL_CLOSE_CP", "replaced_by": "security_package_perfected",             "reason": "A structure is not perfected security."},
    "commissioning_plan":              {"gate": "G11_COD_STABILIZATION",  "replaced_by": "performance_tests_passed",               "reason": "A plan is not a passed test."},
    "handover_documentation_plan":     {"gate": "G11_COD_STABILIZATION",  "replaced_by": "cod_certificate",                        "reason": "Acceptance is evidenced by the COD / taking-over certificate."},
    # previously declared by the platform registry
    "certification_route_definition":  {"gate": "G2_CERTIFICATION_PATH_LOCKED", "replaced_by": "certification_scheme_selection",  "reason": "Duplicate concept."},
    "power_supply_structure_defined":  {"gate": "G3_INPUTS_SECURED",      "replaced_by": "ppa_register",                           "reason": "Power supply is evidenced in G1."},
    "co2_or_biomass_supply_strategy":  {"gate": "G3_INPUTS_SECURED",      "replaced_by": "feedstock_supply_agreement",             "reason": "A strategy is not a supply."},
    "logistics_concept_note":          {"gate": "G3_INPUTS_SECURED",      "replaced_by": "transport_logistics_study",              "reason": "A concept note is not a study."},
    "car_ear_bound":                   {"gate": "G7_INSURANCE_BOUND"    , "replaced_by": "insurance_certificates_delivered",       "reason": "Binding happens at financial close, not before credit approval."},
    "dsu_bi_bound":                    {"gate": "G7_INSURANCE_BOUND"    , "replaced_by": "insurance_certificates_delivered",       "reason": "Binding happens at financial close, not before credit approval."},
    "liability_bound":                 {"gate": "G7_INSURANCE_BOUND"    , "replaced_by": "insurance_certificates_delivered",       "reason": "Binding happens at financial close, not before credit approval."},
    "lenders_loss_payee":              {"gate": "G7_INSURANCE_BOUND"    , "replaced_by": "insurance_certificates_delivered",       "reason": "Loss-payee endorsement is shown on the certificates at close."},
}


# ═══════════════════════════════════════════════════════════════════════════════
# RULES 4.0.0 — EVERY GATE READ THROUGH EVERY PARTY'S EYES
# ═══════════════════════════════════════════════════════════════════════════════
# Decision and evidence: docs/GEX-Twelve-Gates-Multi-Party-Review.docx
# (2026-09-27). Four additions, none of them a new gate:
#   1. financing scope per ITEM, not per gate            (EVIDENCE_SCOPE)
#   2. lenses — which party each item speaks to           (EVIDENCE_LENSES)
#   3. commitment ladders for offtake and EPC              (O0–O7, E0–E6)
#   4. coherence checks and post-FID triggers across contracts (C1–C10, T1–T3)
# Commitment terms are structured fields the platform stores per project
# ("cards": offtake, epc, schedule, supply, model) and passes in with the
# evidence. The engine stays stateless.

# ── 1. Lender protection vs commercial substance ─────────────────────────────
# Only these items protect an external lender. For BALANCE_SHEET funding they
# are NOT_APPLICABLE; every other item applies to every project. A gate is
# WAIVED only when none of its items apply (G6, G8).
EVIDENCE_SCOPE: dict[str, str] = {k: "PROJECT_FINANCE" for k in (
    # G4 — lender security over the revenue line
    "credit_support_package", "take_or_pay_floor", "termination_payment_formula",
    "assignment_rights", "step_in_rights", "hedgeable_pricing_index",
    # G6 — the lenders' own engineer (every project now carries an independent
    # technical review in G5)
    "ie_report_issued", "energy_balance_verified", "capex_opinion_reasonableness",
    "opex_opinion_reasonableness", "completion_test_definitions",
    # G7 — lender acceptance of retained risk
    "deductibles_accepted",
    # G8 — the credit committee's model
    "base_case_model", "model_audit_opinion", "downside_cases", "covenant_suite_defined",
    "dsra_maintenance_reserve_logic", "hedging_plan", "model_consistency_with_ie",
    # G10 — financing conditions
    "cp_checklist_completed", "dsra_funded", "security_package_perfected", "legal_opinions_issued",
)}


def evidence_scope(key: str) -> str:
    return EVIDENCE_SCOPE.get(key, "ALL")


# Gates whose every item protects a lender — waived for balance-sheet funding.
LENDER_ONLY_GATES: frozenset[str] = frozenset(
    g["gate_id"] for g in GATES
    if all(EVIDENCE_SCOPE.get(k) == "PROJECT_FINANCE" for k in g["required_evidence"])
)

# Debt capital is out of scope for a balance-sheet project, whatever its gates.
CAPITAL_SCOPE: dict[str, str] = {
    "DFI_MEZZ_GUARANTEES": "PROJECT_FINANCE",
    "SENIOR_DEBT_COMMITMENT": "PROJECT_FINANCE",
    "DEBT_DRAWDOWN": "PROJECT_FINANCE",
}

# ── 2. Lenses ────────────────────────────────────────────────────────────────
# Views over ONE evidence base, never separate scores: a gate has one
# determination; each lens shows what it means for one party. The seven
# stakeholder groups of the review collapse into four lenses plus the computed
# coherence checks (EPC and technology sit under PRODUCER; lawyers' work is the
# coherence test; insurers sit under CAPITAL).
LENSES: list[str] = ["PRODUCER", "OFFTAKER", "CAPITAL", "CERTIFIER"]
LENS_DEFINITIONS: dict[str, str] = {
    "PRODUCER":  "Can the developer build, run, certify and deliver what it is being asked to commit to?",
    "OFFTAKER":  "Can the buyer rely on receiving certified product, on time and to specification?",
    "CAPITAL":   "Can equity, lenders, development finance and insurers underwrite the risk allocation?",
    "CERTIFIER": "Will the product be certifiable, and certified, under the scheme the market requires?",
}
_P, _O, _C, _X = "PRODUCER", "OFFTAKER", "CAPITAL", "CERTIFIER"
EVIDENCE_LENSES: dict[str, list[str]] = {
    # G0
    "land_option_or_lease_executed": [_P, _C], "zoning_compatibility_memo": [_P],
    "stakeholder_map_v1": [_P], "site_technical_suitability": [_P, _O],
    # G1
    "grid_interconnection_study": [_P, _C], "queue_position_evidence": [_P, _C],
    "grid_connection_cost_estimate": [_P, _C], "connection_date_cod_compatibility_memo": [_P, _O, _C],
    "ppa_register": [_P, _C, _X], "ppa_signed_or_term_sheet_evidence": [_P, _C, _X],
    "ppa_volume_load_coverage_analysis": [_P, _X], "ppa_tenor_debt_comparison": [_C],
    "curtailment_assessment": [_P, _O, _C], "dispatch_load_factor_production_impact": [_P, _O, _C],
    "water_source_plan": [_P], "water_permit_pathway_memo": [_P],
    "btm_generation_asset_evidence": [_P, _C], "generation_yield_study": [_P, _C],
    "grid_independence_note": [_P], "backup_construction_power_plan": [_P],
    "technology_maturity_dossier": [_P, _O, _C], "technology_licensor_term_sheet": [_P],
    "integrated_mass_energy_balance": [_P, _O],
    # G2
    "certification_scheme_selection": [_X, _O, _P], "additionality_evidence": [_X, _O],
    "power_sourcing_alignment_note": [_X, _O], "ghg_methodology_memo": [_X, _O],
    "mrv_plan_v1": [_X, _O], "product_qualification_pathway": [_P, _O, _X],
    # G3
    "feedstock_supply_agreement": [_P, _C], "transport_logistics_study": [_P, _O],
    "storage_plan": [_P], "feedstock_spec_eligibility": [_P, _X, _O],
    # G4
    "binding_offtake_contract_executed": [_O, _P, _C], "offtake_credit_assessment": [_C, _P],
    "credit_support_package": [_C], "take_or_pay_floor": [_C], "termination_payment_formula": [_C],
    "assignment_rights": [_C], "step_in_rights": [_C], "hedgeable_pricing_index": [_C],
    "price_review_mechanism_memo": [_O, _P, _C], "offtake_seller_obligations": [_P, _O],
    # G5
    "epc_contract_fixed_price_or_capped_gmp": [_P, _C, _O], "liquidated_damages_schedule": [_P, _C, _O],
    "date_certain_schedule": [_P, _O, _C], "performance_test_protocol": [_P, _O],
    "interface_matrix": [_P], "oem_warranties": [_P, _C], "epc_contractor_dd": [_P, _C],
    "feed_complete_class3": [_P, _C], "technology_licence_process_guarantee": [_P, _C, _O],
    "long_lead_items_reserved": [_P, _O], "epc_security_package": [_P, _C],
    "independent_technical_review": [_P, _C, _O],
    # G6
    "ie_report_issued": [_C], "energy_balance_verified": [_C], "capex_opinion_reasonableness": [_C],
    "opex_opinion_reasonableness": [_C], "completion_test_definitions": [_C],
    # G7
    "insurance_term_sheet": [_P, _C], "insurance_market_report": [_C, _P],
    "deductibles_accepted": [_C], "exclusions_register_reviewed": [_P, _C],
    "foak_exclusions_warranty_backstop": [_P, _C],
    # G8
    "base_case_model": [_C], "model_audit_opinion": [_C], "downside_cases": [_C],
    "covenant_suite_defined": [_C], "dsra_maintenance_reserve_logic": [_C], "hedging_plan": [_C],
    "model_consistency_with_ie": [_C],
    # G9
    "eia_permit_granted": [_P, _C, _O], "construction_permit_granted": [_P, _C, _O],
    "ancillary_permits_granted": [_P, _C], "legal_opinion_on_appeal_risk": [_C, _O],
    "operating_permit_pathway": [_P], "stakeholder_management_plan_v2": [_P],
    # G10
    "cp_checklist_completed": [_C], "equity_injected": [_C, _P], "dsra_funded": [_C],
    "security_package_perfected": [_C], "insurance_certificates_delivered": [_P, _C],
    "all_major_contracts_executed": [_P, _O, _C], "legal_opinions_issued": [_C],
    "om_contract_or_organisation": [_P, _O],
    # G11
    "cod_certificate": [_P, _C, _O], "performance_tests_passed": [_P, _C, _O],
    "operating_permit_effective": [_P], "mrv_reporting_live": [_X, _O],
    "six_to_twelve_months_stable_ops": [_C, _P], "certificates_issued": [_X, _O, _P],
    "first_deliveries_accepted": [_O, _P],
}

# ── 3. Commitment ladders ────────────────────────────────────────────────────
# "Signed" is not "bankable", and "EPC approved" means nothing on its own. Each
# ladder is DERIVED — from the maturity of verified evidence plus the structured
# commitment terms — so a level can never be typed in, only evidenced.
OFFTAKE_LEVELS: list[str] = ["O0", "O1", "O2", "O3", "O4", "O5", "O6", "O7"]
OFFTAKE_LEVEL_DEFINITIONS: dict[str, str] = {
    "O0": "No verified offtake document with a declared maturity.",
    "O1": "MoU or letter of intent: a buyer exists; nothing binds.",
    "O2": "Term sheet, heads of agreement or agreed form: commercial fit, not binding.",
    "O3": "Signed, but not a binding commitment: a framework, volume or price not firm, or conditions with no longstop.",
    "O4": "Binding, subject to conditions precedent with a longstop date.",
    "O5": "Binding and effective: conditions satisfied; obligations run from COD.",
    "O6": "Firm take-or-pay or take-if-tendered from an investment-grade or credit-supported buyer.",
    "O7": "Project-finance grade: O6 plus tenor covering debt, assignment, step-in, a termination payment and allocated change in law.",
}
# O5 and O6 differ in kind: O5 is effectiveness, O6 is firmness. O6 is reachable
# before financial close, when conditions tied to close are necessarily still
# open; that is why FINANCEABLE separately requires the offtake to be effective.
COMMITMENT_FORMS: list[str] = ["TAKE_OR_PAY", "TAKE_IF_TENDERED", "TAKE_AND_PAY", "TAKE_IF_DELIVERED", "FRAMEWORK"]
_BINDING_FORMS = {"TAKE_OR_PAY", "TAKE_IF_TENDERED", "TAKE_AND_PAY", "TAKE_IF_DELIVERED"}
# Take-or-pay below this share of contract quantity is not a firm commitment.
# Parameter, not a finding: OIES (Aug 2025) reports clean-hydrogen take-or-pay
# negotiated at 60–80% of annual contract quantity, against >90% in early LNG.
TAKE_OR_PAY_FIRM_PCT: float = 60.0
# Share of planned output that offtake terms (O2 or better) must cover before a
# project is COMMERCIALLY_PLAUSIBLE. Parameter, not a finding: it is the bar the
# EU Hydrogen Bank sets at application — Heads of Terms or signed pre-contractual
# term sheets for at least 60 % of production volume (IF25 terms and conditions;
# CINEA Q&A v0.2, 3 Feb 2026), with binding contracts "expected at financial close".
OFFTAKE_COVERAGE_MIN_PCT: float = 60.0

EPC_LEVELS: list[str] = ["E0", "E1", "E2", "E3", "E4", "E5", "E6"]
EPC_LEVEL_DEFINITIONS: dict[str, str] = {
    "E0": "No contracting strategy and no verified EPC document.",
    "E1": "Strategy defined: contracting model chosen, contractor candidates identified.",
    "E2": "FEED complete (AACE Class 3 or better).",
    "E3": "Priced proposal: a verified quotation or term sheet on the FEED basis.",
    "E4": "Agreed form: price, schedule, guarantees, damages and caps, security and licence guarantee all agreed.",
    "E5": "Executed; long-lead items ordered.",
    "E6": "Effective and bankable: notice to proceed issued, security posted.",
}
CONTRACTING_MODELS: list[str] = ["LSTK", "EPCM", "SPLIT_PACKAGES", "EPC_CONVERSION", "OWNER_INTEGRATED"]

# What a gate needs on its own ladder. Later states add their own requirements.
GATE_COMMITMENT_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "G4_OFFTAKE_BANKABLE": ("offtake", "O4"),
    "G5_EPC_RISK_PRICED": ("epc", "E4"),
}
STATE_COMMITMENT_REQUIREMENTS: dict[str, dict[str, dict]] = {
    # 4.1.0: offtake terms for most of the output before a project is called
    # commercially plausible — whoever funds it. Binding comes at G4.
    "COMMERCIALLY_PLAUSIBLE": {
        "PROJECT_FINANCE": {"offtake": "O2", "offtake_coverage_pct": OFFTAKE_COVERAGE_MIN_PCT},
        "BALANCE_SHEET": {"offtake": "O2", "offtake_coverage_pct": OFFTAKE_COVERAGE_MIN_PCT},
    },
    "STRUCTURALLY_BANKABLE": {
        "PROJECT_FINANCE": {"offtake": "O6"},
    },
    "FINANCEABLE": {
        "PROJECT_FINANCE": {"offtake": "O7", "offtake_effective": True, "epc": "E6"},
        "BALANCE_SHEET": {"offtake": "O5", "offtake_effective": True, "epc": "E6"},
    },
}

# The commitment each state makes possible, read next to the capital label.
STATE_COMMITMENT_LABELS: dict[str, str] = {
    "SPECULATIVE": "Idea stage — nothing can be committed yet",
    "TECHNICALLY_PLAUSIBLE": "Site and technology basis confirmed",
    "COMMERCIALLY_PLAUSIBLE": "Commercially defined — offtake term sheets cover most of the output",
    "BUILDABLE": "Commitment-ready — producer and offtaker can sign binding-with-conditions",
    "STRUCTURALLY_BANKABLE": "Independently validated",
    # 4.1.0: a credit approval is a conditional commitment, not money — it lapses
    # if financial close is not reached (Gevo 2026) and precedes close by months.
    "CREDIT_APPROVED": "Credit approved — conditional until financial close",
    "FINANCEABLE": "Committed — investment decision taken",
    "OPERATIONAL": "Delivering — certified product accepted by the buyer",
    "REFINANCING_ELIGIBLE": "Proven — refinancing possible",
}

# The structured fields each commitment card may carry. The platform validates
# writes against this; the engine reads what it needs and ignores the rest.
COMMITMENT_CARD_FIELDS: dict[str, dict[str, str]] = {
    "offtake": {
        # contracted_tonnes_per_year is the volume under offtake terms across all
        # buyers; planned_output_tonnes_per_year is the output it is measured
        # against (4.1.0 coverage). The counterparty fields describe the anchor buyer.
        "counterparty_name": "str", "counterparty_role": "enum:END_USER|OBLIGATED_SUPPLIER|TRADER|INTERMEDIARY|EQUITY_PARTNER",
        "planned_output_tonnes_per_year": "number",
        "buyer_investment_grade": "bool", "credit_support": "bool",
        "commitment_form": "enum:" + "|".join(COMMITMENT_FORMS), "take_or_pay_pct": "number",
        "contracted_tonnes_per_year": "number", "tenor_years": "number",
        "price_mechanism": "enum:FIXED|COST_PLUS|INDEX_PLUS_PREMIUM|FLOOR_CAP|OTHER",
        "cps_satisfied": "bool", "conditions_precedent": "list", "longstop_date": "date",
        "first_delivery_date": "date", "delay_ld_cap_eur": "number",
        "product_spec_standard": "str", "certification_scheme": "str", "compliance_regime": "list",
        "fm_definition_ref": "str", "change_in_law_allocated": "bool",
    },
    "epc": {
        "contractor_name": "str", "contracting_model": "enum:" + "|".join(CONTRACTING_MODELS),
        "contract_price_eur": "number", "guaranteed_completion_date": "date",
        "guaranteed_capacity_tonnes_per_year": "number", "expected_availability_pct": "number",
        "delay_ld_cap_eur": "number", "performance_ld_cap_eur": "number",
        "guaranteed_product_spec": "str", "contingency_eur": "number", "sponsor_support_eur": "number",
        "fm_definition_ref": "str", "counterparty_insolvent": "bool",
    },
    "schedule": {
        "permits_expected_date": "date", "appeal_period_months": "number", "fid_target_date": "date",
        "construction_months_p80": "number", "commissioning_allowance_months": "number",
        "forecast_cod_date": "date",
    },
    "supply": {
        "feedstock_required_tonnes_per_year": "number", "feedstock_contracted_tonnes_per_year": "number",
        "feedstock_tenor_years": "number", "power_required_mwh_per_year": "number",
        "power_contracted_mwh_per_year": "number", "power_tenor_years": "number",
        "power_meets_certification": "bool", "co2_source_eligible": "bool",
        "certification_scheme": "str", "fm_definition_ref": "str",
        "support_or_ppa_revoked": "bool", "certification_suspended": "bool",
    },
    "model": {
        "debt_tenor_years": "number", "model_contracted_tonnes_per_year": "number",
        "model_offtake_tenor_years": "number", "model_epc_price_eur": "number",
    },
}


def _verified(evidence_map: dict, key: str) -> bool:
    return (evidence_map.get(key) or {}).get("status") == "VERIFIED"


def _verified_at(evidence_map: dict, key: str, required: str) -> bool:
    ev = evidence_map.get(key) or {}
    return ev.get("status") == "VERIFIED" and maturity_meets(ev.get("maturity"), required)


def _declared(evidence_map: dict, key: str) -> Optional[str]:
    """Maturity of a VERIFIED item; None if unverified or undeclared."""
    ev = evidence_map.get(key) or {}
    m = ev.get("maturity")
    return m if ev.get("status") == "VERIFIED" and m in MATURITY_LEVELS else None


def level_meets(level: Optional[str], required: str) -> bool:
    """Ladder comparison for O- and E-levels. Unknown fails closed."""
    ladder = OFFTAKE_LEVELS if required.startswith("O") else EPC_LEVELS
    if level not in ladder or required not in ladder:
        return False
    return ladder.index(level) >= ladder.index(required)


def offtake_coverage(terms: Optional[dict]) -> tuple[Optional[float], Optional[str]]:
    """Share of output under offtake terms, and what it was measured against.

    Planned output from the offtake card; the EPC's guaranteed capacity when no
    planned output is recorded. (None, None) when either side is unknown — a
    coverage nobody can compute is not a coverage.
    """
    t = terms or {}
    card, epc = t.get("offtake") or {}, t.get("epc") or {}
    contracted = card.get("contracted_tonnes_per_year")
    if card.get("planned_output_tonnes_per_year"):
        basis, basis_name = card["planned_output_tonnes_per_year"], "PLANNED_OUTPUT"
    elif epc.get("guaranteed_capacity_tonnes_per_year"):
        basis, basis_name = epc["guaranteed_capacity_tonnes_per_year"], "GUARANTEED_CAPACITY"
    else:
        return None, None
    if contracted is None or not basis:
        return None, None
    return round(100.0 * contracted / basis, 1), basis_name


def derive_offtake_level(evidence_map: dict, terms: Optional[dict]) -> dict:
    """Grade the offtake on O0–O7 from the contract's verified maturity and the
    offtake card. Returns level, effectiveness and the reasons it is not higher."""
    card = (terms or {}).get("offtake") or {}
    model = (terms or {}).get("model") or {}
    m = _declared(evidence_map, "binding_offtake_contract_executed")
    coverage_pct, coverage_basis = offtake_coverage(terms)
    out = {"level": "O0", "effective": False, "reasons": [], "form": card.get("commitment_form"),
           "coverage_pct": coverage_pct, "coverage_basis": coverage_basis}
    if m is None:
        out["reasons"].append("No verified offtake document with a declared maturity.")
        return out
    if m == "INTENT":
        out.update(level="O1")
        out["reasons"].append("Letter of intent or MoU: nothing binds yet.")
        return out
    if m in ("INDICATIVE", "AGREED"):
        out.update(level="O2")
        out["reasons"].append(f"{m.title()} document: terms known, not signed.")
        return out
    effective = m == "EFFECTIVE" or bool(card.get("cps_satisfied"))
    out["effective"] = effective
    form = card.get("commitment_form")
    if form not in _BINDING_FORMS:
        out.update(level="O3")
        out["reasons"].append("Signed, but the offtake card records no binding commitment form "
                              "(take-or-pay, take-if-tendered, take-and-pay or take-if-delivered).")
        return out
    if not effective and not card.get("longstop_date"):
        out.update(level="O3")
        out["reasons"].append("Binding but conditional with no longstop date: a condition with no "
                              "deadline leaves the buyer an open option.")
        return out
    level = "O5" if effective else "O4"
    firm = form == "TAKE_IF_TENDERED" or (
        form == "TAKE_OR_PAY" and (card.get("take_or_pay_pct") or 0) >= TAKE_OR_PAY_FIRM_PCT)
    creditworthy = (bool(card.get("buyer_investment_grade")) or bool(card.get("credit_support"))
                    or _verified(evidence_map, "credit_support_package"))
    if not firm:
        out["reasons"].append(f"Not firm: take-or-pay below {TAKE_OR_PAY_FIRM_PCT:.0f}% of contract "
                              "quantity, or a take-and-pay / take-if-delivered form.")
    if not creditworthy:
        out["reasons"].append("Buyer neither investment-grade nor credit-supported.")
    if firm and creditworthy:
        level = "O6"
        missing = [k for k in ("assignment_rights", "step_in_rights", "termination_payment_formula")
                   if not _verified(evidence_map, k)]
        tenor, debt_tenor = card.get("tenor_years"), model.get("debt_tenor_years")
        tenor_ok = tenor is not None and debt_tenor is not None and tenor >= debt_tenor
        cil = bool(card.get("change_in_law_allocated"))
        if not missing and tenor_ok and cil:
            level = "O7"
        else:
            if missing:
                out["reasons"].append("Lender protections not verified: " + ", ".join(missing) + ".")
            if not tenor_ok:
                out["reasons"].append("Offtake tenor not shown to cover the debt tenor.")
            if not cil:
                out["reasons"].append("Change in law not allocated in the offtake.")
    if not effective:
        out["reasons"].append("Not yet effective: conditions precedent outstanding.")
    out["level"] = level
    return out


def derive_epc_level(evidence_map: dict, terms: Optional[dict]) -> dict:
    """Grade the EPC on E0–E6 from verified evidence maturity and the EPC card."""
    card = (terms or {}).get("epc") or {}
    m = _declared(evidence_map, "epc_contract_fixed_price_or_capped_gmp")
    reasons: list[str] = []
    level = "E0"
    while True:  # one pass; each step either advances or explains why not
        if card.get("contracting_model") not in CONTRACTING_MODELS and m is None:
            reasons.append("No contracting strategy recorded and no verified EPC document.")
            break
        level = "E1"
        if not _verified(evidence_map, "feed_complete_class3"):
            reasons.append("FEED not verified complete (AACE Class 3 or better).")
            break
        level = "E2"
        if not maturity_meets(m, "INDICATIVE"):
            reasons.append("No verified priced proposal on the FEED basis.")
            break
        level = "E3"
        gaps = []
        if not maturity_meets(m, "AGREED"):
            gaps.append("EPC contract not in agreed form")
        if not _verified_at(evidence_map, "technology_licence_process_guarantee", "AGREED"):
            gaps.append("licence and process guarantee not agreed")
        if not _verified_at(evidence_map, "epc_security_package", "AGREED"):
            gaps.append("security package not agreed")
        if not _verified(evidence_map, "liquidated_damages_schedule"):
            gaps.append("damages schedule not verified")
        if gaps:
            reasons.append("Not agreed form: " + "; ".join(gaps) + ".")
            break
        level = "E4"
        if not (maturity_meets(m, "EXECUTED") and _verified_at(evidence_map, "long_lead_items_reserved", "EXECUTED")):
            reasons.append("Not executed, or long-lead items not yet ordered.")
            break
        level = "E5"
        if not (m == "EFFECTIVE" and _verified_at(evidence_map, "epc_security_package", "EFFECTIVE")):
            reasons.append("No notice to proceed, or security not yet posted.")
            break
        level = "E6"
        break
    if card.get("counterparty_insolvent") and level_meets(level, "E4"):
        level = "E3"
        reasons.insert(0, "Contractor or key OEM reported insolvent: the agreed or executed "
                          "contract can no longer be relied on (trigger T3).")
    return {"level": level, "reasons": reasons, "contracting_model": card.get("contracting_model")}


# ── 4. Coherence checks and post-FID triggers ────────────────────────────────
# Each check compares two commitments GEX holds. PASS / FAIL decide; a FAIL
# blocks the gate the check belongs to. NOT_EVALUABLE (data missing) and
# NOT_APPLICABLE never block — they are shown so the gap is visible.
COHERENCE_CHECKS: list[dict] = [
    {"id": "C1", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_P, _O],
     "title": "First delivery after guaranteed completion plus commissioning allowance"},
    {"id": "C2", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_P, _O, _C],
     "title": "Contracted volume within guaranteed capacity × availability"},
    {"id": "C3", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_P, _O],
     "title": "Offtake specification guaranteed by the EPC or licensor"},
    {"id": "C4", "gate": "G5_EPC_RISK_PRICED", "lenses": [_P, _C],
     "title": "Offtake delay exposure backed by EPC damages, contingency and sponsor support"},
    {"id": "C5", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_P, _O, _C],
     "title": "Longstop covers permits, investment decision, construction and commissioning"},
    {"id": "C6", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_P, _C],
     "title": "Feedstock and power contracted for the offtake's volume and tenor"},
    {"id": "C7", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_X, _O],
     "title": "Power and CO2 sourcing meet the certification the offtake requires"},
    {"id": "C8", "gate": "G4_OFFTAKE_BANKABLE", "lenses": [_X, _O],
     "title": "Producer certifies under the scheme the offtake requires"},
    {"id": "C9", "gate": "G10_FINANCIAL_CLOSE_CP", "lenses": [_P, _O, _C],
     "title": "Force majeure aligned across offtake, EPC and supply contracts"},
    {"id": "C10", "gate": "G8_AUDIT_GRADE_MODEL", "lenses": [_C],
     "title": "Model inputs equal contract terms; offtake tenor covers debt"},
]
# Relative tolerance for "equal" numeric comparisons in C10 and the capacity
# ceiling in C2 — rounding in a model, not a margin for error.
COHERENCE_TOLERANCE: float = 0.01

REGRESSION_TRIGGERS: list[dict] = [
    {"id": "T1", "card": "supply", "field": "support_or_ppa_revoked",
     "gates": ["G1_GRID_UTILITIES_REALITY"],
     "title": "Power contract or public support terms revoked"},
    {"id": "T2", "card": "supply", "field": "certification_suspended",
     "gates": ["G2_CERTIFICATION_PATH_LOCKED", "G11_COD_STABILIZATION"],
     "title": "Certification suspended"},
    {"id": "T3", "card": "epc", "field": "counterparty_insolvent",
     "gates": ["G5_EPC_RISK_PRICED"],
     "title": "EPC contractor or key OEM insolvent"},
]


def _date(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _plus_months(d, months):
    months = int(round(float(months)))
    y, mth = divmod(d.month - 1 + months, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 and ((d.year + y) % 100 != 0 or (d.year + y) % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mth])
    return d.replace(year=d.year + y, month=mth + 1, day=day)


def _norm(s) -> str:
    return " ".join(str(s).upper().replace("-", " ").split()) if s is not None else ""


def compute_coherence(terms: Optional[dict], financing_model: Optional[str] = None) -> list[dict]:
    """Run C1–C10 over the commitment cards. Returns one result per check."""
    t = terms or {}
    off, epc, sch, sup, mdl = (t.get(k) or {} for k in ("offtake", "epc", "schedule", "supply", "model"))
    results = []

    def emit(cid, status, detail, documents, missing=None):
        spec = next(c for c in COHERENCE_CHECKS if c["id"] == cid)
        results.append({**spec, "status": status, "detail": detail, "documents": documents,
                        "missing": missing or []})

    def need(pairs):
        return [f"{card}.{field}" for card, field, value in pairs if value is None or value == ""]

    # C1 — delivery date vs completion
    fd, gc, allow = _date(off.get("first_delivery_date")), _date(epc.get("guaranteed_completion_date")), sch.get("commissioning_allowance_months")
    miss = need([("offtake", "first_delivery_date", fd), ("epc", "guaranteed_completion_date", gc),
                 ("schedule", "commissioning_allowance_months", allow)])
    if miss:
        emit("C1", "NOT_EVALUABLE", "Missing data.", ["offtake", "epc", "schedule"], miss)
    else:
        earliest = _plus_months(gc, allow)
        emit("C1", "PASS" if fd >= earliest else "FAIL",
             f"First delivery {fd} {'is on or after' if fd >= earliest else 'is before'} guaranteed completion "
             f"{gc} + {allow} months = {earliest}.", ["offtake", "epc", "schedule"])

    # C2 — volume vs capacity
    q, cap, av = off.get("contracted_tonnes_per_year"), epc.get("guaranteed_capacity_tonnes_per_year"), epc.get("expected_availability_pct")
    miss = need([("offtake", "contracted_tonnes_per_year", q), ("epc", "guaranteed_capacity_tonnes_per_year", cap),
                 ("epc", "expected_availability_pct", av)])
    if miss:
        emit("C2", "NOT_EVALUABLE", "Missing data.", ["offtake", "epc"], miss)
    else:
        ceiling = float(cap) * float(av) / 100.0
        ok = float(q) <= ceiling * (1 + COHERENCE_TOLERANCE)
        emit("C2", "PASS" if ok else "FAIL",
             f"Contracted {float(q):,.0f} t/yr against guaranteed capacity {float(cap):,.0f} t/yr × "
             f"{float(av):g}% availability = {ceiling:,.0f} t/yr.", ["offtake", "epc"])

    # C3 — specification
    spec, guaranteed = off.get("product_spec_standard"), epc.get("guaranteed_product_spec")
    miss = need([("offtake", "product_spec_standard", spec), ("epc", "guaranteed_product_spec", guaranteed)])
    if miss:
        emit("C3", "NOT_EVALUABLE", "Missing data.", ["offtake", "epc"], miss)
    else:
        allowed = {_norm(x) for x in str(guaranteed).split(",") if x.strip()}
        ok = _norm(spec) in allowed
        emit("C3", "PASS" if ok else "FAIL",
             f"Offtake requires '{spec}'; EPC/licensor guarantee{'s' if len(allowed) > 1 else ''} '{guaranteed}'.",
             ["offtake", "epc"])

    # C4 — delay exposure vs backstop
    exposure, ld = off.get("delay_ld_cap_eur"), epc.get("delay_ld_cap_eur")
    miss = need([("offtake", "delay_ld_cap_eur", exposure), ("epc", "delay_ld_cap_eur", ld)])
    if miss:
        emit("C4", "NOT_EVALUABLE", "Missing data.", ["offtake", "epc"], miss)
    else:
        backstop = float(ld) + float(epc.get("contingency_eur") or 0) + float(epc.get("sponsor_support_eur") or 0)
        ok = float(exposure) <= backstop
        emit("C4", "PASS" if ok else "FAIL",
             f"Delay exposure under the offtake €{float(exposure):,.0f} against EPC delay damages + contingency "
             f"+ sponsor support €{backstop:,.0f}.", ["offtake", "epc"])

    # C5 — longstop realism (and the post-FID forecast)
    if off.get("cps_satisfied"):
        emit("C5", "NOT_APPLICABLE", "Offtake is effective; no longstop is running.", ["offtake", "schedule"])
    else:
        longstop = _date(off.get("longstop_date"))
        permits, fid = _date(sch.get("permits_expected_date")), _date(sch.get("fid_target_date"))
        appeal, build, allow = sch.get("appeal_period_months"), sch.get("construction_months_p80"), sch.get("commissioning_allowance_months")
        miss = need([("offtake", "longstop_date", longstop), ("schedule", "permits_expected_date", permits),
                     ("schedule", "fid_target_date", fid), ("schedule", "construction_months_p80", build),
                     ("schedule", "commissioning_allowance_months", allow)])
        if miss:
            emit("C5", "NOT_EVALUABLE", "Missing data.", ["offtake", "schedule"], miss)
        else:
            start = max(_plus_months(permits, appeal or 0), fid)
            planned = _plus_months(_plus_months(start, build), allow)
            forecast = _date(sch.get("forecast_cod_date"))
            needed = max(planned, _plus_months(forecast, allow)) if forecast else planned
            ok = longstop >= needed
            basis = (f"forecast COD {forecast} + {allow} months" if forecast and needed != planned
                     else f"max(permits + appeal, FID) {start} + {build} months P80 + {allow} months")
            emit("C5", "PASS" if ok else "FAIL",
                 f"Longstop {longstop} against first delivery at {needed} ({basis}).", ["offtake", "schedule"])

    # C6 — supply covers the offtake
    fr, fc, ft, ot = (sup.get("feedstock_required_tonnes_per_year"), sup.get("feedstock_contracted_tonnes_per_year"),
                      sup.get("feedstock_tenor_years"), off.get("tenor_years"))
    miss = need([("supply", "feedstock_required_tonnes_per_year", fr), ("supply", "feedstock_contracted_tonnes_per_year", fc),
                 ("supply", "feedstock_tenor_years", ft), ("offtake", "tenor_years", ot)])
    if miss:
        emit("C6", "NOT_EVALUABLE", "Missing data.", ["supply", "offtake"], miss)
    else:
        gaps = []
        if float(fc) < float(fr):
            gaps.append(f"feedstock {float(fc):,.0f} of {float(fr):,.0f} t/yr contracted")
        if float(ft) < float(ot):
            gaps.append(f"feedstock tenor {float(ft):g} y shorter than offtake {float(ot):g} y")
        pr, pc, ptn = sup.get("power_required_mwh_per_year"), sup.get("power_contracted_mwh_per_year"), sup.get("power_tenor_years")
        if pr is not None and pc is not None and float(pc) < float(pr):
            gaps.append(f"power {float(pc):,.0f} of {float(pr):,.0f} MWh/yr contracted")
        if ptn is not None and float(ptn) < float(ot):
            gaps.append(f"power tenor {float(ptn):g} y shorter than offtake {float(ot):g} y")
        emit("C6", "FAIL" if gaps else "PASS",
             ("Supply shorter than sales: " + "; ".join(gaps) + ".") if gaps
             else "Contracted feedstock (and power, where recorded) cover the offtake's volume and tenor.",
             ["supply", "offtake"])

    # C7 — sourcing satisfies the certification the offtake requires
    if not off.get("compliance_regime"):
        emit("C7", "NOT_APPLICABLE", "The offtake records no compliance regime.", ["supply", "offtake"])
    else:
        pm, co2 = sup.get("power_meets_certification"), sup.get("co2_source_eligible")
        miss = need([("supply", "power_meets_certification", pm), ("supply", "co2_source_eligible", co2)])
        if miss:
            emit("C7", "NOT_EVALUABLE", "Missing data.", ["supply", "offtake"], miss)
        else:
            bad = [n for n, v in (("power sourcing", pm), ("CO2 source", co2)) if not v]
            emit("C7", "FAIL" if bad else "PASS",
                 ("Does not meet certification: " + ", ".join(bad) + ".") if bad
                 else "Power sourcing and CO2 source recorded as meeting the certification rules.",
                 ["supply", "offtake"])

    # C8 — scheme match
    req, prod = off.get("certification_scheme"), sup.get("certification_scheme")
    miss = need([("offtake", "certification_scheme", req), ("supply", "certification_scheme", prod)])
    if miss:
        emit("C8", "NOT_EVALUABLE", "Missing data.", ["offtake", "supply"], miss)
    else:
        ok = _norm(req) == _norm(prod)
        emit("C8", "PASS" if ok else "FAIL",
             f"Offtake requires '{req}'; producer certifies under '{prod}'.", ["offtake", "supply"])

    # C9 — force majeure alignment
    refs = {"offtake": off.get("fm_definition_ref"), "epc": epc.get("fm_definition_ref"), "supply": sup.get("fm_definition_ref")}
    miss = [f"{k}.fm_definition_ref" for k, v in refs.items() if not v]
    if miss:
        emit("C9", "NOT_EVALUABLE", "Missing data.", list(refs), miss)
    else:
        ok = len({_norm(v) for v in refs.values()}) == 1
        emit("C9", "PASS" if ok else "FAIL",
             "Force majeure definitions: " + ", ".join(f"{k} '{v}'" for k, v in refs.items()) + ".", list(refs))

    # C10 — model vs contracts (project finance only)
    if financing_model == "BALANCE_SHEET":
        emit("C10", "NOT_APPLICABLE", "No credit-committee model for balance-sheet funding.", ["model", "offtake", "epc"])
    else:
        pairs = [("contracted volume", mdl.get("model_contracted_tonnes_per_year"), off.get("contracted_tonnes_per_year")),
                 ("offtake tenor", mdl.get("model_offtake_tenor_years"), off.get("tenor_years")),
                 ("EPC price", mdl.get("model_epc_price_eur"), epc.get("contract_price_eur"))]
        compared, gaps = 0, []
        for name, a, b in pairs:
            if a is None or b is None:
                continue
            compared += 1
            if abs(float(a) - float(b)) > COHERENCE_TOLERANCE * max(abs(float(b)), 1.0):
                gaps.append(f"{name}: model {float(a):,.2f} vs contract {float(b):,.2f}")
        debt, tenor = mdl.get("debt_tenor_years"), off.get("tenor_years")
        if debt is not None and tenor is not None:
            compared += 1
            if float(tenor) < float(debt):
                gaps.append(f"offtake tenor {float(tenor):g} y shorter than debt {float(debt):g} y")
        if not compared:
            emit("C10", "NOT_EVALUABLE", "Missing data.", ["model", "offtake", "epc"],
                 ["model.model_contracted_tonnes_per_year", "model.model_offtake_tenor_years",
                  "model.model_epc_price_eur", "model.debt_tenor_years"])
        else:
            emit("C10", "FAIL" if gaps else "PASS",
                 ("Model disagrees with contracts: " + "; ".join(gaps) + ".") if gaps
                 else f"{compared} model input(s) match the contracts.", ["model", "offtake", "epc"])
    return results


def compute_triggers(terms: Optional[dict]) -> list[dict]:
    """Active post-FID triggers. Each blocks the gates it names."""
    t = terms or {}
    return [{**trig, "detail": f"{trig['card']}.{trig['field']} is set."}
            for trig in REGRESSION_TRIGGERS if (t.get(trig["card"]) or {}).get(trig["field"])]


# ═══════════════════════════════════════════════════════════════════════════════
# STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════════

STATE_ORDER = [
    "SPECULATIVE",
    "TECHNICALLY_PLAUSIBLE",
    "COMMERCIALLY_PLAUSIBLE",
    "BUILDABLE",
    "STRUCTURALLY_BANKABLE",
    "CREDIT_APPROVED",
    "FINANCEABLE",
    "OPERATIONAL",
    "REFINANCING_ELIGIBLE",
]

# Which gates must be complete to reach each state
STATE_REQUIREMENTS: dict[str, list[str]] = {
    "TECHNICALLY_PLAUSIBLE": ["G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY"],
    "COMMERCIALLY_PLAUSIBLE": ["G2_CERTIFICATION_PATH_LOCKED", "G3_INPUTS_SECURED"],
    "BUILDABLE": ["G4_OFFTAKE_BANKABLE", "G5_EPC_RISK_PRICED"],
    "STRUCTURALLY_BANKABLE": ["G6_IE_SIGNOFF", "G7_INSURANCE_BOUND"],
    "CREDIT_APPROVED": ["G8_AUDIT_GRADE_MODEL"],
    "FINANCEABLE": ["G9_PERMITS_SAFE", "G10_FINANCIAL_CLOSE_CP"],
    "OPERATIONAL": ["G11_COD_STABILIZATION"],
    "REFINANCING_ELIGIBLE": [],  # requires OPERATIONAL + time
}

# Persona scoping, DERIVED from each gate's own `personas` so the two can never
# disagree. EXECUTIVE sees everything. OFFTAKER joined in 4.0.0: the buyer sees
# the gates whose outcome it depends on (certification, offtake, EPC, permits,
# the investment decision, delivery).
PERSONAS: list[str] = ["PRODUCER", "FINANCE", "REGULATOR", "OFFTAKER", "EXECUTIVE"]
PERSONA_GATES: dict[str, list[str]] = {
    p: [g["gate_id"] for g in GATES if p in g["personas"]]
    for p in PERSONAS if p != "EXECUTIVE"
}
PERSONA_GATES["EXECUTIVE"] = [g["gate_id"] for g in GATES]

CAPITAL_TYPES = [
    "GRANTS_TA", "SEED_VC_ANGEL", "STRATEGIC_EQUITY", "PROJECT_EQUITY",
    "DFI_MEZZ_GUARANTEES", "SENIOR_DEBT_COMMITMENT", "DEBT_DRAWDOWN",
    "REFINANCE_BONDS_INFRA",
]

# What each capital decision is called on screen — the one source for labels.
# Identifiers stay stable (stored snapshots and fixtures carry them); labels say
# what the decision is. SENIOR_DEBT_COMMITMENT is a credit approval: lenders'
# commitments at that stage are conditional on documentation and financial close
# (Stegra 2022, Atome 2025, DOE conditional commitments), and money moves only
# at DEBT_DRAWDOWN.
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
# EVALUATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_gate(gate: dict, evidence: list[dict],
                   power_model: Optional[str] = None,
                   project_phase: Optional[str] = None,
                   financing_model: Optional[str] = None) -> dict:
    """
    Evaluate a single gate against provided evidence.

    Power-model-aware: items whose EVIDENCE_META.applies_to excludes the
    project's power model are reported with status NOT_APPLICABLE and are
    EXCLUDED from the denominator, blocking_items, and deal-killer checks.
    An off-grid project is never structurally capped by grid evidence it
    can never produce.

    Phase-aware: per-item severity escalates per EVIDENCE_META (warning →
    deal_killer once construction starts).
    """
    evidence_map = {e["key"]: e for e in evidence}
    detail = []
    verified = 0
    applicable_total = 0
    blocking = []
    deal_killers_blocked = []
    maturity_shortfalls = []

    excluded_by_financing = 0
    for ek in gate["required_evidence"]:
        meta = EVIDENCE_META.get(ek, {})
        fits_power = _evidence_applies(ek, power_model)
        fits_financing = _item_applies_financing(ek, financing_model)
        applicable = fits_power and fits_financing
        not_applicable_reason = None if applicable else ("POWER_MODEL" if not fits_power else "FINANCING_MODEL")
        if fits_power and not fits_financing:
            excluded_by_financing += 1
        severity = _effective_severity(ek, gate, project_phase)
        ev = evidence_map.get(ek, {"key": ek, "status": "NOT_STARTED"})
        status = "NOT_APPLICABLE" if not applicable else ev.get("status", "NOT_STARTED")
        required_maturity = REQUIRED_MATURITY.get(ek)
        declared_maturity = ev.get("maturity")
        if not required_maturity:
            maturity_status = "NOT_REQUIRED"
        elif declared_maturity not in MATURITY_LEVELS:
            maturity_status = "NOT_DECLARED"
        elif maturity_meets(declared_maturity, required_maturity):
            maturity_status = "MET"
        else:
            maturity_status = "BELOW_REQUIRED"

        detail.append({
            "key": ek,
            "status": status,
            "applicable": applicable,
            "severity": severity,
            "label": meta.get("label", ek.replace("_", " ").title()),
            "section": meta.get("section", "Z"),
            "section_label": meta.get("section_label", "Other"),
            "applies_to": meta.get("applies_to", ["ALL"]),
            "owner_function": meta.get("owner_function", "PROJECT"),
            "blocked_action": meta.get("blocked_action"),
            "route": meta.get("route"),
            "submitted_by": ev.get("submitted_by"),
            "verified_by": ev.get("verified_by"),
            "submitted_at": ev.get("submitted_at"),
            "verified_at": ev.get("verified_at"),
            "notes": ev.get("notes"),
            "required_maturity": required_maturity,
            "declared_maturity": declared_maturity,
            "maturity_status": maturity_status,
            "scope": evidence_scope(ek),
            "lenses": EVIDENCE_LENSES.get(ek, []),
            "not_applicable_reason": not_applicable_reason,
        })

        if not applicable:
            continue
        applicable_total += 1
        # An item counts only when it is VERIFIED *and* its instrument is mature
        # enough. Verification says the document is authentic; it does not make
        # a term sheet into a contract.
        is_verified = ev.get("status") == "VERIFIED"
        if is_verified and maturity_status in ("NOT_REQUIRED", "MET"):
            verified += 1
        else:
            blocking.append(ek)
            if is_verified:
                maturity_shortfalls.append({
                    "key": ek,
                    "required_maturity": required_maturity,
                    "declared_maturity": declared_maturity,
                    "maturity_status": maturity_status,
                })
            if severity == "deal_killer":
                deal_killers_blocked.append(ek)

    pct = (verified / applicable_total * 100) if applicable_total > 0 else 0.0

    # Premise check: a gate with power-model-scoped evidence cannot be
    # meaningfully judged without a declared power model. An undeclared
    # premise is a FINDING, not a neutral default — silently scoring the
    # full superset would let old records pass without forcing correction.
    premise_findings = []
    has_scoped_evidence = any(
        "ALL" not in EVIDENCE_META.get(ek, {}).get("applies_to", ["ALL"])
        for ek in gate["required_evidence"]
    )
    if has_scoped_evidence and not power_model:
        premise_severity = (
            "deal_killer" if project_phase in _ESCALATION_PHASES else "warning"
        )
        premise_findings.append({
            "code": "UNKNOWN_POWER_MODEL",
            "severity": premise_severity,
            "message": (
                "No power model declared (OFF_GRID_BTM / GRID_CONNECTED / HYBRID). "
                "The production premise is missing — evidence scope, OPEX structure "
                "and certification pathway cannot be determined. Gate scored against "
                "the full superset until declared."
            ),
            "blocked_action": "Bankability scoring confidence; IC pack export; lender submission",
            "route": "/projects/{project_id}/edit",
        })

    has_dk_block = len(deal_killers_blocked) > 0 or any(
        f["severity"] == "deal_killer" for f in premise_findings
    )

    # What this gate means for each party — the same items, filtered by lens.
    lens_readouts = {}
    for lens in LENSES:
        mine = [d for d in detail if d["applicable"] and lens in d["lenses"]]
        lens_readouts[lens] = {
            "applicable": len(mine),
            "verified": sum(1 for d in mine if d["key"] not in blocking),
            "blocking": [d["key"] for d in mine if d["key"] in blocking],
        }

    return {
        "gate_id": gate["gate_id"],
        "gate_name": gate["gate_name"],
        "owners": gate["owners"],
        "total_evidence": applicable_total,
        "verified_count": verified,
        "completion_pct": round(pct, 1),
        "is_complete": verified == applicable_total and applicable_total > 0,
        "power_model": power_model,
        "project_phase": project_phase,
        "premise_findings": premise_findings,
        "evidence_detail": detail,
        "unlocks_capital": gate["unlocks_capital"],
        "unlocks_state": gate.get("unlocks_state"),
        "blocking_items": blocking,
        "deal_killers": [d["key"] for d in detail if d["applicable"] and d["severity"] == "deal_killer"],
        "deal_killers_blocked": deal_killers_blocked,
        "has_deal_killer_block": has_dk_block,
        # VERIFIED items that still do not count because the instrument is not
        # mature enough, or its maturity was never declared.
        "maturity_shortfalls": maturity_shortfalls,
        "lens_readouts": lens_readouts,
        # Every applicable-by-power item was lender protection and the project
        # is balance-sheet funded: the gate is waived, not failed.
        "waived_by_financing": applicable_total == 0 and excluded_by_financing > 0,
    }


def _financing_key(financing_model: Optional[str]) -> str:
    return "BALANCE_SHEET" if financing_model == "BALANCE_SHEET" else "PROJECT_FINANCE"


def _commitment_shortfalls(state: str, financing_model: Optional[str],
                           offtake: dict, epc: dict) -> list[dict]:
    """What a state needs on the commitment ladders that the project does not have."""
    req = STATE_COMMITMENT_REQUIREMENTS.get(state, {}).get(_financing_key(financing_model), {})
    out = []
    if "offtake" in req and not level_meets(offtake["level"], req["offtake"]):
        out.append({"kind": "offtake", "gate": "G4_OFFTAKE_BANKABLE", "required": req["offtake"],
                    "actual": offtake["level"],
                    "message": f"{state} needs offtake {req['offtake']}; the project has {offtake['level']}."})
    if "offtake_coverage_pct" in req:
        need, cov = req["offtake_coverage_pct"], offtake.get("coverage_pct")
        if cov is None:
            out.append({"kind": "offtake_coverage", "gate": "G4_OFFTAKE_BANKABLE", "required": f"{need:.0f}%",
                        "actual": "unknown",
                        "message": f"{state} needs offtake terms for at least {need:.0f}% of output; record the "
                                   "contracted volume and the planned output on the offtake card."})
        elif cov < need:
            out.append({"kind": "offtake_coverage", "gate": "G4_OFFTAKE_BANKABLE", "required": f"{need:.0f}%",
                        "actual": f"{cov:g}%",
                        "message": f"{state} needs offtake terms for at least {need:.0f}% of output; "
                                   f"{cov:g}% is covered."})
    if req.get("offtake_effective") and not offtake["effective"]:
        out.append({"kind": "offtake_effective", "gate": "G4_OFFTAKE_BANKABLE", "required": "effective",
                    "actual": "conditional",
                    "message": f"{state} needs the offtake effective (conditions precedent satisfied)."})
    if "epc" in req and not level_meets(epc["level"], req["epc"]):
        out.append({"kind": "epc", "gate": "G5_EPC_RISK_PRICED", "required": req["epc"], "actual": epc["level"],
                    "message": f"{state} needs EPC {req['epc']}; the project has {epc['level']}."})
    return out


def _compute_state(gate_evals: list[dict], waived_gates: set[str] | None = None,
                   financing_model: Optional[str] = None,
                   offtake: Optional[dict] = None, epc: Optional[dict] = None) -> str:
    """
    Highest state whose gates are complete AND whose commitment requirements
    are met, climbing strictly in order. Gates waived by financing model count
    as satisfied for the climb; they are never presented as satisfied evidence.
    """
    waived = waived_gates or set()
    offtake = offtake or {"level": "O0", "effective": False}
    epc = epc or {"level": "E0"}
    complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]} | waived
    achieved = "SPECULATIVE"
    for state in STATE_ORDER[1:]:
        reqs = STATE_REQUIREMENTS.get(state, [])
        if not reqs:
            continue
        if achieved != STATE_ORDER[STATE_ORDER.index(state) - 1]:
            break
        if all(g in complete_gates for g in reqs) and not _commitment_shortfalls(state, financing_model, offtake, epc):
            achieved = state
        else:
            break
    return achieved


def _compute_capital_unlocks(gate_evals: list[dict], waived_gates: set[str] | None = None,
                             financing_model: Optional[str] = None) -> list[dict]:
    """
    Determine which capital decisions the evidence now supports.

    WHAT THIS DOES NOT DO: it does not commit, release or draw capital, and it
    cannot. A software rule has no authority to create a lender commitment or
    move cash — that decision belongs to the bank, investor, DFI, grant
    authority or sponsor, and COMMITTED / DRAWABLE / DRAWN are separate
    authorised capital events recorded elsewhere. A satisfied gate means only
    that the evidence conditions for that capital provider's decision are met.

    `decision_eligible` states that precisely. `is_unlocked` carries the same
    value and is kept only so existing consumers keep working; new code should
    read `decision_eligible`, and no screen should call the result "unlocked".

    Out of scope (financing_applicable = false, never eligible-by-waiver): debt
    capital for a balance-sheet project (CAPITAL_SCOPE), and capital gated only
    by financing-waived gates.
    """
    waived = waived_gates or set()
    gate_map = {g["gate_id"]: g for g in gate_evals}
    unlocks = []
    for ct in CAPITAL_TYPES:
        gating_gates = [g["gate_id"] for g in GATES if ct in g["unlocks_capital"]]
        applicable_gating = [gid for gid in gating_gates if gid not in waived]
        in_scope = not (financing_model == "BALANCE_SHEET" and CAPITAL_SCOPE.get(ct) == "PROJECT_FINANCE")
        financing_applicable = in_scope and (len(gating_gates) == 0 or len(applicable_gating) > 0)
        is_unlocked = financing_applicable and all(
            gate_map.get(gid, {}).get("is_complete", False) for gid in applicable_gating
        )
        best_pct = max(
            (gate_map.get(gid, {}).get("completion_pct", 0) for gid in gating_gates),
            default=0,
        )
        unlocks.append({
            "capital_type": ct,
            "label": CAPITAL_TYPE_LABELS[ct],
            "decision_eligible": is_unlocked,
            "is_unlocked": is_unlocked,  # deprecated alias — see docstring
            "financing_applicable": financing_applicable,
            "gating_gates": gating_gates,
            "best_progress_pct": best_pct,
        })
    return unlocks


def _find_next_state(current: str) -> Optional[str]:
    """Find the next state after current."""
    idx = STATE_ORDER.index(current)
    if idx < len(STATE_ORDER) - 1:
        return STATE_ORDER[idx + 1]
    return None


def _find_blocking_gates(current: str, gate_evals: list[dict]) -> list[str]:
    """Find which gates block the next state transition."""
    next_state = _find_next_state(current)
    if not next_state:
        return []
    reqs = STATE_REQUIREMENTS.get(next_state, [])
    complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]}
    return [g for g in reqs if g not in complete_gates]


def _check_regression(current: str, previous: Optional[str], gate_evals: list[dict],
                      waived_gates: set[str] | None = None, financing_model: Optional[str] = None,
                      offtake: Optional[dict] = None, epc: Optional[dict] = None) -> Optional[dict]:
    """Check if state has regressed from previous evaluation, and name why."""
    if not previous:
        return None
    prev_idx = STATE_ORDER.index(previous) if previous in STATE_ORDER else -1
    curr_idx = STATE_ORDER.index(current) if current in STATE_ORDER else -1
    if curr_idx >= prev_idx:
        return None
    complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]} | (waived_gates or set())
    trigger, reason = "unknown", f"Evidence no longer meets requirements for {previous}"
    for state in STATE_ORDER[curr_idx + 1: prev_idx + 1]:
        missing = [g for g in STATE_REQUIREMENTS.get(state, []) if g not in complete_gates]
        if missing:
            trigger = missing[0]
            gate = next((g for g in gate_evals if g["gate_id"] == trigger), {})
            why = gate.get("blocked_reasons") or []
            if why:
                reason = why[0]
            break
        shortfalls = _commitment_shortfalls(state, financing_model, offtake or {"level": "O0", "effective": False},
                                            epc or {"level": "E0"})
        if shortfalls:
            trigger, reason = shortfalls[0]["gate"], shortfalls[0]["message"]
            break
    return {"from_state": previous, "to_state": current, "trigger_gate": trigger, "reason": reason}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate(project_id: str, evidence: list[dict],
             previous_state: Optional[str] = None,
             power_model: Optional[str] = None,
             project_phase: Optional[str] = None,
             financing_model: Optional[str] = None,
             terms: Optional[dict] = None) -> dict:
    """
    Full bankability evaluation.

    Args:
        project_id: Project identifier
        evidence: List of evidence dicts with 'key', 'status' and 'maturity'
        previous_state: Last known state (for regression detection)
        power_model: OFF_GRID_BTM | GRID_CONNECTED | HYBRID — scopes which
            evidence items are applicable (None = score everything, legacy)
        project_phase: development | construction | commissioning | operating
            — drives severity escalation on missing evidence
        financing_model: PROJECT_FINANCE | BALANCE_SHEET — scopes which ITEMS
            apply; lender-protection items drop out for balance-sheet projects
            (None = legacy, everything applies)
        terms: commitment cards {offtake, epc, schedule, supply, model}; see
            COMMITMENT_CARD_FIELDS. Drive the O/E ladders, coherence checks
            and post-FID triggers.

    Returns:
        ProjectBankabilitySnapshot dict
    """
    evidence_map = {e["key"]: e for e in evidence}
    offtake = derive_offtake_level(evidence_map, terms)
    epc = derive_epc_level(evidence_map, terms)
    levels = {"offtake": offtake, "epc": epc}
    coherence = compute_coherence(terms, financing_model)
    triggers = compute_triggers(terms)

    waived_gates: set[str] = set()
    gate_evals = []
    for g in GATES:
        gid = g["gate_id"]
        ev = _evaluate_gate(g, evidence, power_model, project_phase, financing_model)
        if ev["waived_by_financing"]:
            waived_gates.add(gid)
        ev["financing_applicable"] = gid not in waived_gates

        checks = []
        if gid in GATE_COMMITMENT_REQUIREMENTS:
            kind, required = GATE_COMMITMENT_REQUIREMENTS[gid]
            actual = levels[kind]["level"]
            checks.append({
                "kind": kind, "required": required, "actual": actual,
                "met": level_meets(actual, required),
                "reasons": levels[kind]["reasons"],
            })
        ev["commitment_checks"] = checks
        ev["coherence_checks"] = [c for c in coherence if c["gate"] == gid]
        ev["triggers"] = [t for t in triggers if gid in t["gates"]]

        blocked_reasons = (
            [f"{c['kind'].upper()} {c['actual']} below the {c['required']} this gate needs"
             for c in checks if not c["met"]]
            + [f"{c['id']} failed: {c['detail']}" for c in ev["coherence_checks"] if c["status"] == "FAIL"]
            + [f"{t['id']} {t['title']}" for t in ev["triggers"]]
        )
        # 4.2.0: a cross-contract check that cannot run for lack of data is not a
        # pass. It holds the gate UNRESOLVED and names what is missing — the
        # gate used to read SATISFIED with every check unevaluated.
        unresolved = [c for c in ev["coherence_checks"] if c["status"] == "NOT_EVALUABLE"]
        ev["unresolved_reasons"] = [
            f"{c['id']} cannot be checked: missing {', '.join(c.get('missing') or ['data'])}" for c in unresolved]
        ev["items_complete"] = ev["is_complete"]
        ev["is_complete"] = (ev["is_complete"] and not blocked_reasons and not unresolved
                             and gid not in waived_gates)
        ev["blocked_reasons"] = blocked_reasons
        # One explicit outcome per gate. A waived gate counts toward the ladder
        # but is never presented as satisfied by evidence: WAIVED is its own
        # answer. A failed commitment check, coherence check or trigger is
        # decisive, so it BLOCKS rather than leaving the gate merely INCOMPLETE.
        if gid in waived_gates:
            ev["determination"] = "WAIVED"
        elif ev["is_complete"]:
            ev["determination"] = "SATISFIED"
        elif ev["has_deal_killer_block"] or blocked_reasons:
            ev["determination"] = "BLOCKED"
        elif ev["items_complete"] and unresolved:
            ev["determination"] = "UNRESOLVED"
        else:
            ev["determination"] = "INCOMPLETE"
        gate_evals.append(ev)

    current_state = _compute_state(gate_evals, waived_gates, financing_model, offtake, epc)
    capital_unlocks = _compute_capital_unlocks(gate_evals, waived_gates, financing_model)
    regression = _check_regression(current_state, previous_state, gate_evals, waived_gates,
                                   financing_model, offtake, epc)

    # Overall totals over financing-applicable gates only — a balance-sheet
    # project's completion is not diluted by lender evidence it will never file.
    applicable_evals = [g for g in gate_evals if g["financing_applicable"]]
    total_evidence = sum(g["total_evidence"] for g in applicable_evals)
    total_verified = sum(g["verified_count"] for g in applicable_evals)
    overall_pct = (total_verified / total_evidence * 100) if total_evidence > 0 else 0.0

    # Three-band risk classification derived from current state
    _BANKABLE_STATES = {"CREDIT_APPROVED", "FINANCEABLE", "OPERATIONAL", "REFINANCING_ELIGIBLE"}
    _DEVELOPABLE_STATES = {"BUILDABLE", "STRUCTURALLY_BANKABLE"}
    if current_state in _BANKABLE_STATES:
        risk_classification = "BANKABLE"
    elif current_state in _DEVELOPABLE_STATES:
        risk_classification = "DEVELOPABLE"
    else:
        risk_classification = "SPECULATIVE"

    next_state = _find_next_state(current_state)
    commitment_requirements = {
        state: {
            "requirements": STATE_COMMITMENT_REQUIREMENTS.get(state, {}).get(_financing_key(financing_model), {}),
            "shortfalls": _commitment_shortfalls(state, financing_model, offtake, epc),
        }
        for state in STATE_COMMITMENT_REQUIREMENTS
    }

    return {
        "project_id": project_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": EVIDENCE_RULES_VERSION,
        "power_model": power_model,
        "project_phase": project_phase,
        "financing_model": financing_model,
        "financing_waived_gates": sorted(waived_gates),
        "current_state": current_state,
        "state_label": STATE_COMMITMENT_LABELS.get(current_state),
        "previous_state": previous_state,
        "regression": regression,
        "gate_evaluations": gate_evals,
        "capital_unlocks": capital_unlocks,
        "total_evidence": total_evidence,
        "total_verified": total_verified,
        "overall_completion_pct": round(overall_pct, 1),
        "risk_classification": risk_classification,
        "next_state": next_state,
        "next_state_label": STATE_COMMITMENT_LABELS.get(next_state) if next_state else None,
        "gates_blocking_next_state": [
            gid for gid in _find_blocking_gates(current_state, gate_evals)
            if gid not in waived_gates
        ],
        "commitments_blocking_next_state": (
            _commitment_shortfalls(next_state, financing_model, offtake, epc) if next_state else []
        ),
        "offtake": offtake,
        "epc": epc,
        "commitment_requirements": commitment_requirements,
        "coherence_checks": coherence,
        "regression_triggers": triggers,
    }


def evaluate_for_persona(project_id: str, evidence: list[dict],
                         persona: str,
                         previous_state: Optional[str] = None,
                         power_model: Optional[str] = None,
                         project_phase: Optional[str] = None,
                         financing_model: Optional[str] = None,
                         terms: Optional[dict] = None) -> dict:
    """Persona-scoped evaluation — only gates relevant to the persona.

    State, capital and overall completion are still computed across all twelve
    gates; a persona sees a subset of gates beside a figure that covers all."""
    full = evaluate(project_id, evidence, previous_state, power_model, project_phase, financing_model, terms)
    visible_gates = set(PERSONA_GATES.get(persona, []))
    full["gate_evaluations"] = [
        g for g in full["gate_evaluations"] if g["gate_id"] in visible_gates
    ]
    full["persona"] = persona
    return full


def get_gates() -> list[dict]:
    """Return gate definitions enriched with per-evidence policy metadata."""
    enriched = []
    for g in GATES:
        enriched.append({
            **g,
            "evidence_meta": {
                ek: {
                    **EVIDENCE_META.get(ek, {
                        "label": ek.replace("_", " ").title(),
                        "section": "Z", "section_label": "Other",
                        "applies_to": ["ALL"], "severity": "warning",
                        "escalates_at_construction": False,
                        "owner_function": "PROJECT", "blocked_action": None, "route": None,
                    }),
                    "scope": evidence_scope(ek),
                    "lenses": EVIDENCE_LENSES.get(ek, []),
                    "required_maturity": REQUIRED_MATURITY.get(ek),
                }
                for ek in g["required_evidence"]
            },
            "commitment_requirement": GATE_COMMITMENT_REQUIREMENTS.get(g["gate_id"]),
            "lender_only": g["gate_id"] in LENDER_ONLY_GATES,
        })
    return enriched


def get_rules() -> dict:
    """Return state machine rules, including the evidence bar and its history."""
    return {
        "rules_version": EVIDENCE_RULES_VERSION,
        "state_order": STATE_ORDER,
        "state_requirements": STATE_REQUIREMENTS,
        "state_commitment_labels": STATE_COMMITMENT_LABELS,
        "state_commitment_requirements": STATE_COMMITMENT_REQUIREMENTS,
        "gate_commitment_requirements": {k: list(v) for k, v in GATE_COMMITMENT_REQUIREMENTS.items()},
        "persona_gates": PERSONA_GATES,
        "capital_types": CAPITAL_TYPES,
        "capital_type_labels": CAPITAL_TYPE_LABELS,
        "offtake_coverage_min_pct": OFFTAKE_COVERAGE_MIN_PCT,
        "capital_scope": CAPITAL_SCOPE,
        "capital_semantics": (
            "A satisfied gate makes a project eligible for the named capital "
            "provider's decision. GEX does not commit, release or draw capital."
        ),
        "maturity_levels": MATURITY_LEVELS,
        "maturity_definitions": MATURITY_DEFINITIONS,
        "required_maturity": REQUIRED_MATURITY,
        "retired_evidence": RETIRED_EVIDENCE,
        "evidence_scope": EVIDENCE_SCOPE,
        "lender_only_gates": sorted(LENDER_ONLY_GATES),
        "lenses": LENSES,
        "lens_definitions": LENS_DEFINITIONS,
        "evidence_lenses": EVIDENCE_LENSES,
        "offtake_levels": OFFTAKE_LEVELS,
        "offtake_level_definitions": OFFTAKE_LEVEL_DEFINITIONS,
        "take_or_pay_firm_pct": TAKE_OR_PAY_FIRM_PCT,
        "epc_levels": EPC_LEVELS,
        "epc_level_definitions": EPC_LEVEL_DEFINITIONS,
        "commitment_card_fields": COMMITMENT_CARD_FIELDS,
        "coherence_checks": COHERENCE_CHECKS,
        "coherence_tolerance": COHERENCE_TOLERANCE,
        "regression_triggers": REGRESSION_TRIGGERS,
    }
