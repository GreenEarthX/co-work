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

EVIDENCE_RULES_VERSION = "2.1.1"

# Financing models. PROJECT_FINANCE = SPV with external debt — the original
# GEX worldview, all 12 gates apply. BALANCE_SHEET = corporate / prosumer
# funding from own balance sheet — lender-protection gates are out of scope.
FINANCING_MODELS = ("PROJECT_FINANCE", "BALANCE_SHEET")

# Gates that exist purely to protect external capital providers.
_LENDER_GATES = {
    "G4_OFFTAKE",          # third-party bankable offtake (a prosumer self-offtakes)
    "G6_IE_SIGNOFF",       # independent engineer for lenders
    "G7_INSURANCE",        # lender-mandated insurance package
    "G8_MODEL_AUDIT",      # audit-grade model for credit committee
    "G10_FINANCIAL_CLOSE", # CP satisfaction / security package
}


def _gate_applies_financing(gate_id: str, financing_model: Optional[str]) -> bool:
    """Lender gates apply only to PROJECT_FINANCE. Unknown financing = legacy, all apply."""
    if not financing_model or financing_model == "PROJECT_FINANCE":
        return True
    return gate_id not in _LENDER_GATES


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
        "required_evidence": [
            "land_option_or_lease_executed",
            "zoning_compatibility_memo",
            "stakeholder_map_v1",
        ],
        "deal_killers": ["land_option_or_lease_executed"],
        "unlocks_capital": ["GRANTS_TA"],
        "unlocks_state": "TECHNICALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G1_GRID_WATER",
        "gate_name": "Power, Water & Critical Utility Access",
        "owners": ["PRODUCER"],
        # Superset across power models. EVIDENCE_META.applies_to filters which
        # items are scored for a given project — OFF_GRID_BTM is never asked
        # for a grid study or a PPA; GRID_CONNECTED is never asked for a BTM
        # yield study. Gate id stays G1_GRID_WATER (state machine, ABAC, and
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
        ],
        # Static fallback only — effective deal killers come from EVIDENCE_META
        # severity + phase escalation, scoped to applicable items.
        "deal_killers": ["grid_interconnection_study", "water_source_plan", "btm_generation_asset_evidence"],
        "unlocks_capital": ["SEED_VC_ANGEL"],
        "unlocks_state": "TECHNICALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G2_CERTIFICATION",
        "gate_name": "Green Certification Pathway",
        "owners": ["REGULATOR"],
        "required_evidence": [
            "certification_scheme_selection",
            "additionality_evidence",
            "ghg_methodology_memo",
        ],
        "deal_killers": ["certification_scheme_selection", "additionality_evidence"],
        "unlocks_capital": [],
        "unlocks_state": "COMMERCIALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G3_FEEDSTOCK_LOGISTICS",
        "gate_name": "Feedstock & Logistics",
        "owners": ["PRODUCER"],
        "required_evidence": [
            "feedstock_supply_loi",
            "transport_logistics_study",
            "storage_plan",
        ],
        "deal_killers": ["feedstock_supply_loi"],
        "unlocks_capital": ["STRATEGIC_EQUITY"],
        "unlocks_state": "COMMERCIALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G4_OFFTAKE",
        "gate_name": "Binding Offtake",
        "owners": ["FINANCE"],
        "required_evidence": [
            "binding_offtake_term_sheet",
            "offtake_credit_assessment",
            "price_review_mechanism_memo",
        ],
        "deal_killers": ["binding_offtake_term_sheet", "offtake_credit_assessment"],
        "unlocks_capital": ["PROJECT_EQUITY"],
        "unlocks_state": "BUILDABLE",
    },
    {
        "gate_id": "G5_EPC",
        "gate_name": "EPC & Construction",
        "owners": ["PRODUCER", "EXECUTIVE"],
        "required_evidence": [
            "epc_contract_heads_of_terms",
            "performance_guarantees_draft",
            "epc_contractor_dd",
        ],
        "deal_killers": ["epc_contract_heads_of_terms", "performance_guarantees_draft"],
        "unlocks_capital": [],
        "unlocks_state": "BUILDABLE",
    },
    {
        "gate_id": "G6_IE_SIGNOFF",
        "gate_name": "Independent Engineer Signoff",
        "owners": ["FINANCE", "REGULATOR"],
        "required_evidence": [
            "ie_appointment_letter",
            "ie_technical_model_review",
            "ie_site_visit_report",
        ],
        "deal_killers": ["ie_technical_model_review", "ie_site_visit_report"],
        "unlocks_capital": ["DFI_MEZZ_GUARANTEES"],
        "unlocks_state": "STRUCTURALLY_BANKABLE",
    },
    {
        "gate_id": "G7_INSURANCE",
        "gate_name": "Insurance Package",
        "owners": ["FINANCE"],
        "required_evidence": [
            "insurance_broker_mandate",
            "insurance_market_report",
            "insurance_term_sheet",
        ],
        "deal_killers": ["insurance_term_sheet"],
        "unlocks_capital": [],
        "unlocks_state": "STRUCTURALLY_BANKABLE",
    },
    {
        "gate_id": "G8_MODEL_AUDIT",
        "gate_name": "Audit-Grade Financial Model",
        "owners": ["FINANCE"],
        "required_evidence": [
            "financial_model_v1",
            "model_audit_engagement",
            "sensitivity_analysis",
        ],
        "deal_killers": ["financial_model_v1", "model_audit_engagement"],
        "unlocks_capital": ["SENIOR_DEBT_COMMITMENT"],
        "unlocks_state": "CREDIT_APPROVED",
    },
    {
        "gate_id": "G9_PERMITS",
        "gate_name": "Permits & Approvals",
        "owners": ["PRODUCER", "REGULATOR"],
        "required_evidence": [
            "eia_submission",
            "construction_permit_application",
            "operating_permit_pathway",
        ],
        "deal_killers": ["eia_submission", "construction_permit_application"],
        "unlocks_capital": [],
        "unlocks_state": "FINANCEABLE",
    },
    {
        "gate_id": "G10_FINANCIAL_CLOSE",
        "gate_name": "Financial Close",
        "owners": ["FINANCE"],
        "required_evidence": [
            "cp_checklist_draft",
            "legal_opinions_draft",
            "security_package_structure",
        ],
        "deal_killers": ["cp_checklist_draft", "legal_opinions_draft", "security_package_structure"],
        "unlocks_capital": ["DEBT_DRAWDOWN"],
        "unlocks_state": "FINANCEABLE",
    },
    {
        "gate_id": "G11_COD",
        "gate_name": "Commercial Operations Date",
        "owners": ["PRODUCER", "EXECUTIVE"],
        "required_evidence": [
            "commissioning_plan",
            "performance_test_protocol",
            "handover_documentation_plan",
        ],
        "deal_killers": ["commissioning_plan", "performance_test_protocol"],
        "unlocks_capital": ["REFINANCE_BONDS_INFRA"],
        "unlocks_state": "OPERATIONAL",
    },
]


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
    "TECHNICALLY_PLAUSIBLE": ["G0_SITE_RIGHTS", "G1_GRID_WATER"],
    "COMMERCIALLY_PLAUSIBLE": ["G2_CERTIFICATION", "G3_FEEDSTOCK_LOGISTICS"],
    "BUILDABLE": ["G4_OFFTAKE", "G5_EPC"],
    "STRUCTURALLY_BANKABLE": ["G6_IE_SIGNOFF", "G7_INSURANCE"],
    "CREDIT_APPROVED": ["G8_MODEL_AUDIT"],
    "FINANCEABLE": ["G9_PERMITS", "G10_FINANCIAL_CLOSE"],
    "OPERATIONAL": ["G11_COD"],
    "REFINANCING_ELIGIBLE": [],  # requires OPERATIONAL + time
}

# Persona scoping
PERSONA_GATES: dict[str, list[str]] = {
    "PRODUCER": ["G0_SITE_RIGHTS", "G1_GRID_WATER", "G3_FEEDSTOCK_LOGISTICS",
                 "G5_EPC", "G9_PERMITS", "G11_COD"],
    "FINANCE": ["G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
                "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE"],
    "REGULATOR": ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
    "EXECUTIVE": list({g["gate_id"] for g in GATES}),  # all gates
}

CAPITAL_TYPES = [
    "GRANTS_TA", "SEED_VC_ANGEL", "STRATEGIC_EQUITY", "PROJECT_EQUITY",
    "DFI_MEZZ_GUARANTEES", "SENIOR_DEBT_COMMITMENT", "DEBT_DRAWDOWN",
    "REFINANCE_BONDS_INFRA",
]


# ═══════════════════════════════════════════════════════════════════════════════
# EVALUATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_gate(gate: dict, evidence: list[dict],
                   power_model: Optional[str] = None,
                   project_phase: Optional[str] = None) -> dict:
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

    for ek in gate["required_evidence"]:
        meta = EVIDENCE_META.get(ek, {})
        applicable = _evidence_applies(ek, power_model)
        severity = _effective_severity(ek, gate, project_phase)
        ev = evidence_map.get(ek, {"key": ek, "status": "NOT_STARTED"})
        status = "NOT_APPLICABLE" if not applicable else ev.get("status", "NOT_STARTED")

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
        })

        if not applicable:
            continue
        applicable_total += 1
        if ev.get("status") == "VERIFIED":
            verified += 1
        else:
            blocking.append(ek)
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
    }


def _compute_state(gate_evals: list[dict], waived_gates: set[str] | None = None) -> str:
    """
    Determine highest achievable state based on gate completion.
    Gates waived by financing model count as satisfied for state transitions —
    a balance-sheet project is not held at BUILDABLE for lacking a lender's
    insurance package it will never procure.
    """
    waived = waived_gates or set()
    complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]} | waived
    achieved = "SPECULATIVE"

    for state in STATE_ORDER[1:]:
        reqs = STATE_REQUIREMENTS.get(state, [])
        if not reqs:
            continue
        # Must have all prerequisite states AND this state's gates
        prev_idx = STATE_ORDER.index(state) - 1
        prev_state = STATE_ORDER[prev_idx]
        if achieved != prev_state:
            break
        if all(g in complete_gates for g in reqs):
            achieved = state
        else:
            break

    return achieved


def _compute_capital_unlocks(gate_evals: list[dict], waived_gates: set[str] | None = None) -> list[dict]:
    """
    Determine which capital types are unlocked.
    Capital gated ONLY by financing-waived gates is itself out of scope
    (a balance-sheet project does not "unlock senior debt" — it never sought
    it) and is reported financing_applicable = false, never unlocked-by-waiver.
    """
    waived = waived_gates or set()
    gate_map = {g["gate_id"]: g for g in gate_evals}
    unlocks = []

    for ct in CAPITAL_TYPES:
        gating_gates = [g["gate_id"] for g in GATES if ct in g["unlocks_capital"]]
        applicable_gating = [gid for gid in gating_gates if gid not in waived]
        # Out of scope only when EVERY gating gate is financing-waived;
        # partially-waived capital unlocks on the applicable remainder.
        financing_applicable = len(gating_gates) == 0 or len(applicable_gating) > 0
        is_unlocked = financing_applicable and all(
            gate_map.get(gid, {}).get("is_complete", False) for gid in applicable_gating
        )
        best_pct = max(
            (gate_map.get(gid, {}).get("completion_pct", 0) for gid in gating_gates),
            default=0,
        )
        unlocks.append({
            "capital_type": ct,
            "is_unlocked": is_unlocked,
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


def _check_regression(current: str, previous: Optional[str], gate_evals: list[dict]) -> Optional[dict]:
    """Check if state has regressed from previous evaluation."""
    if not previous:
        return None
    prev_idx = STATE_ORDER.index(previous) if previous in STATE_ORDER else -1
    curr_idx = STATE_ORDER.index(current) if current in STATE_ORDER else -1
    if curr_idx < prev_idx:
        # Find which gate caused regression
        complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]}
        trigger = "unknown"
        for state in STATE_ORDER[curr_idx + 1: prev_idx + 1]:
            reqs = STATE_REQUIREMENTS.get(state, [])
            for g in reqs:
                if g not in complete_gates:
                    trigger = g
                    break
        return {
            "from_state": previous,
            "to_state": current,
            "trigger_gate": trigger,
            "reason": f"Evidence no longer meets requirements for {previous}",
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate(project_id: str, evidence: list[dict],
             previous_state: Optional[str] = None,
             power_model: Optional[str] = None,
             project_phase: Optional[str] = None,
             financing_model: Optional[str] = None) -> dict:
    """
    Full bankability evaluation.

    Args:
        project_id: Project identifier
        evidence: List of evidence dicts with 'key' and 'status' fields
        previous_state: Last known state (for regression detection)
        power_model: OFF_GRID_BTM | GRID_CONNECTED | HYBRID — scopes which
            evidence items are applicable (None = score everything, legacy)
        project_phase: development | construction | commissioning | operating
            — drives severity escalation on missing evidence
        financing_model: PROJECT_FINANCE | BALANCE_SHEET — scopes which GATES
            apply; lender gates are waived for balance-sheet projects
            (None = legacy, all gates apply)

    Returns:
        ProjectBankabilitySnapshot dict
    """
    waived_gates = {
        g["gate_id"] for g in GATES
        if not _gate_applies_financing(g["gate_id"], financing_model)
    }
    gate_evals = []
    for g in GATES:
        ev = _evaluate_gate(g, evidence, power_model, project_phase)
        ev["financing_applicable"] = g["gate_id"] not in waived_gates
        gate_evals.append(ev)
    current_state = _compute_state(gate_evals, waived_gates)
    capital_unlocks = _compute_capital_unlocks(gate_evals, waived_gates)
    regression = _check_regression(current_state, previous_state, gate_evals)

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

    return {
        "project_id": project_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": EVIDENCE_RULES_VERSION,
        "power_model": power_model,
        "project_phase": project_phase,
        "financing_model": financing_model,
        "financing_waived_gates": sorted(waived_gates),
        "current_state": current_state,
        "previous_state": previous_state,
        "regression": regression,
        "gate_evaluations": gate_evals,
        "capital_unlocks": capital_unlocks,
        "total_evidence": total_evidence,
        "total_verified": total_verified,
        "overall_completion_pct": round(overall_pct, 1),
        "risk_classification": risk_classification,
        "next_state": _find_next_state(current_state),
        "gates_blocking_next_state": [
            gid for gid in _find_blocking_gates(current_state, gate_evals)
            if gid not in waived_gates
        ],
    }


def evaluate_for_persona(project_id: str, evidence: list[dict],
                         persona: str,
                         previous_state: Optional[str] = None,
                         power_model: Optional[str] = None,
                         project_phase: Optional[str] = None,
                         financing_model: Optional[str] = None) -> dict:
    """Persona-scoped evaluation — only gates relevant to the persona."""
    full = evaluate(project_id, evidence, previous_state, power_model, project_phase, financing_model)

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
                ek: EVIDENCE_META.get(ek, {
                    "label": ek.replace("_", " ").title(),
                    "section": "Z", "section_label": "Other",
                    "applies_to": ["ALL"], "severity": "warning",
                    "escalates_at_construction": False,
                    "owner_function": "PROJECT", "blocked_action": None, "route": None,
                })
                for ek in g["required_evidence"]
            },
        })
    return enriched


def get_rules() -> dict:
    """Return state machine rules."""
    return {
        "rules_version": EVIDENCE_RULES_VERSION,
        "state_order": STATE_ORDER,
        "state_requirements": STATE_REQUIREMENTS,
        "persona_gates": PERSONA_GATES,
        "capital_types": CAPITAL_TYPES,
    }
