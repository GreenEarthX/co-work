"""
GEX Bankability Engine — Core Logic
=====================================
12 stage gates, 9 bankability states, 8 capital unlock types.
Stateless evaluator: receives evidence + previous_state, returns snapshot.

Install in: gex_pf_engine/backend/app/core/bankability_engine.py
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


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
        "unlocks_capital": ["GRANTS_TA"],
        "unlocks_state": "TECHNICALLY_PLAUSIBLE",
    },
    {
        "gate_id": "G1_GRID_WATER",
        "gate_name": "Grid Connection & Water/Utilities",
        "owners": ["PRODUCER"],
        "required_evidence": [
            "grid_interconnection_study",
            "queue_position_evidence",
            "curtailment_assessment",
            "water_source_plan",
            "water_permit_pathway_memo",
        ],
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
    "REGULATOR": ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G7_INSURANCE", "G9_PERMITS"],
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

def _evaluate_gate(gate: dict, evidence: list[dict]) -> dict:
    """Evaluate a single gate against provided evidence."""
    evidence_map = {e["key"]: e for e in evidence}
    detail = []
    verified = 0

    for ek in gate["required_evidence"]:
        ev = evidence_map.get(ek, {"key": ek, "status": "NOT_STARTED"})
        detail.append({
            "key": ek,
            "status": ev.get("status", "NOT_STARTED"),
            "submitted_by": ev.get("submitted_by"),
            "verified_by": ev.get("verified_by"),
            "submitted_at": ev.get("submitted_at"),
            "verified_at": ev.get("verified_at"),
            "notes": ev.get("notes"),
        })
        if ev.get("status") == "VERIFIED":
            verified += 1

    total = len(gate["required_evidence"])
    pct = (verified / total * 100) if total > 0 else 0.0

    return {
        "gate_id": gate["gate_id"],
        "gate_name": gate["gate_name"],
        "owners": gate["owners"],
        "total_evidence": total,
        "verified_count": verified,
        "completion_pct": round(pct, 1),
        "is_complete": verified == total,
        "evidence_detail": detail,
        "unlocks_capital": gate["unlocks_capital"],
        "unlocks_state": gate.get("unlocks_state"),
        "blocking_items": [d["key"] for d in detail if d["status"] != "VERIFIED"],
    }


def _compute_state(gate_evals: list[dict]) -> str:
    """Determine highest achievable state based on gate completion."""
    complete_gates = {g["gate_id"] for g in gate_evals if g["is_complete"]}
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


def _compute_capital_unlocks(gate_evals: list[dict]) -> list[dict]:
    """Determine which capital types are unlocked."""
    gate_map = {g["gate_id"]: g for g in gate_evals}
    unlocks = []

    for ct in CAPITAL_TYPES:
        gating_gates = [g["gate_id"] for g in GATES if ct in g["unlocks_capital"]]
        is_unlocked = all(gate_map.get(gid, {}).get("is_complete", False) for gid in gating_gates)
        best_pct = max(
            (gate_map.get(gid, {}).get("completion_pct", 0) for gid in gating_gates),
            default=0,
        )
        unlocks.append({
            "capital_type": ct,
            "is_unlocked": is_unlocked,
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
             previous_state: Optional[str] = None) -> dict:
    """
    Full bankability evaluation.

    Args:
        project_id: Project identifier
        evidence: List of evidence dicts with 'key' and 'status' fields
        previous_state: Last known state (for regression detection)

    Returns:
        ProjectBankabilitySnapshot dict
    """
    gate_evals = [_evaluate_gate(g, evidence) for g in GATES]
    current_state = _compute_state(gate_evals)
    capital_unlocks = _compute_capital_unlocks(gate_evals)
    regression = _check_regression(current_state, previous_state, gate_evals)

    total_evidence = sum(g["total_evidence"] for g in gate_evals)
    total_verified = sum(g["verified_count"] for g in gate_evals)
    overall_pct = (total_verified / total_evidence * 100) if total_evidence > 0 else 0.0

    return {
        "project_id": project_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "current_state": current_state,
        "previous_state": previous_state,
        "regression": regression,
        "gate_evaluations": gate_evals,
        "capital_unlocks": capital_unlocks,
        "total_evidence": total_evidence,
        "total_verified": total_verified,
        "overall_completion_pct": round(overall_pct, 1),
        "next_state": _find_next_state(current_state),
        "gates_blocking_next_state": _find_blocking_gates(current_state, gate_evals),
    }


def evaluate_for_persona(project_id: str, evidence: list[dict],
                         persona: str,
                         previous_state: Optional[str] = None) -> dict:
    """Persona-scoped evaluation — only gates relevant to the persona."""
    full = evaluate(project_id, evidence, previous_state)

    visible_gates = set(PERSONA_GATES.get(persona, []))
    full["gate_evaluations"] = [
        g for g in full["gate_evaluations"] if g["gate_id"] in visible_gates
    ]
    full["persona"] = persona
    return full


def get_gates() -> list[dict]:
    """Return gate definitions."""
    return GATES


def get_rules() -> dict:
    """Return state machine rules."""
    return {
        "state_order": STATE_ORDER,
        "state_requirements": STATE_REQUIREMENTS,
        "persona_gates": PERSONA_GATES,
        "capital_types": CAPITAL_TYPES,
    }
