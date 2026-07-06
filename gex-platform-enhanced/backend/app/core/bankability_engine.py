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
    StakeholderPersona.EXECUTIVE: set(Department),  # sees everything
}

# Which gates each persona has primary interest in
# (Executives see all gates; others see their operational subset)
PERSONA_GATES: dict[StakeholderPersona, list[str]] = {
    StakeholderPersona.PRODUCER: [
        "G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY",
        "G3_INPUTS_SECURED", "G5_EPC_RISK_PRICED",
        "G9_PERMITS_SAFE", "G11_COD_STABILIZATION",
    ],
    StakeholderPersona.FINANCE: [
        "G4_OFFTAKE_BANKABLE", "G6_IE_SIGNOFF",
        "G8_AUDIT_GRADE_MODEL", "G10_FINANCIAL_CLOSE_CP",
        "G7_INSURANCE_BOUND",
    ],
    StakeholderPersona.REGULATOR: [
        "G2_CERTIFICATION_PATH_LOCKED", "G6_IE_SIGNOFF",
        "G7_INSURANCE_BOUND", "G9_PERMITS_SAFE",
    ],
    StakeholderPersona.EXECUTIVE: [],  # empty = all gates
}


# ═══════════════════════════════════════════════════════════════════════════════
# GATE DEFINITIONS (from gates JSON)
# ═══════════════════════════════════════════════════════════════════════════════

class GateDefinition(BaseModel):
    id: str
    name: str
    required_evidence: list[str]
    owners: list[Department]
    unlocks_capital: list[CapitalType]
    unlocks_state: Optional[BankabilityState] = None


GATE_REGISTRY: list[GateDefinition] = [
    GateDefinition(
        id="G0_SITE_RIGHTS", name="Site & Rights Secured",
        required_evidence=["land_option_or_lease_executed", "zoning_compatibility_memo", "stakeholder_map_v1"],
        owners=[Department.PROJECT, Department.LEGAL],
        unlocks_capital=[CapitalType.GRANTS_TA, CapitalType.SEED_VC_ANGEL],
        unlocks_state=BankabilityState.TECHNICALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G1_GRID_UTILITIES_REALITY", name="Power, Water & Critical Utility Access",
        # Superset across power models — mirrors the RUNTIME registry in
        # gex_pf_engine/backend/app/core/bankability_engine.py (EVIDENCE_META
        # there scopes items per power_model and escalates severity by phase).
        # This vendored copy serves routes_gate_registry only; keep in sync.
        required_evidence=[
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
            # C. Curtailment & Dispatch (ALL power models)
            "curtailment_assessment",
            "dispatch_load_factor_production_impact",
            # D. Water Supply & Permitting (ALL power models)
            "water_source_plan",
            "water_permit_pathway_memo",
            # E. BTM Generation (OFF_GRID_BTM / HYBRID)
            "btm_generation_asset_evidence",
            "generation_yield_study",
            "grid_independence_note",
            "backup_construction_power_plan",
        ],
        owners=[Department.ENGINEERING, Department.PROJECT, Department.FINANCE],
        unlocks_capital=[CapitalType.SEED_VC_ANGEL],
    ),
    GateDefinition(
        id="G2_CERTIFICATION_PATH_LOCKED", name="Certification Path Locked (RFNBO/GoO/ISCC)",
        required_evidence=["certification_route_definition", "power_sourcing_alignment_note", "mrv_plan_v1"],
        owners=[Department.ENGINEERING, Department.LEGAL],
        unlocks_capital=[CapitalType.SEED_VC_ANGEL],
    ),
    GateDefinition(
        id="G3_INPUTS_SECURED", name="Key Inputs Secured",
        required_evidence=["power_supply_structure_defined", "co2_or_biomass_supply_strategy", "logistics_concept_note"],
        owners=[Department.ENGINEERING, Department.PROJECT, Department.FINANCE],
        unlocks_capital=[CapitalType.SEED_VC_ANGEL],
    ),
    GateDefinition(
        id="G4_OFFTAKE_BANKABLE", name="Offtake Bankable",
        required_evidence=["binding_offtake_contract_executed", "assignment_rights", "step_in_rights", "take_or_pay_floor", "termination_payment_formula", "credit_support_package", "hedgeable_pricing_index"],
        owners=[Department.SALES, Department.LEGAL, Department.FINANCE],
        unlocks_capital=[CapitalType.STRATEGIC_EQUITY, CapitalType.PROJECT_EQUITY],
        unlocks_state=BankabilityState.COMMERCIALLY_PLAUSIBLE,
    ),
    GateDefinition(
        id="G5_EPC_RISK_PRICED", name="EPC Risk Priced & Transferred",
        required_evidence=["epc_contract_fixed_price_or_capped_gmp", "date_certain_schedule", "liquidated_damages_schedule", "performance_test_protocol", "interface_matrix", "oem_warranties"],
        owners=[Department.PROJECT, Department.ENGINEERING, Department.LEGAL],
        unlocks_capital=[CapitalType.PROJECT_EQUITY, CapitalType.DFI_MEZZ_GUARANTEES],
        unlocks_state=BankabilityState.BUILDABLE,
    ),
    GateDefinition(
        id="G6_IE_SIGNOFF", name="Independent Engineer Sign-off",
        required_evidence=["ie_report_issued", "energy_balance_verified", "capex_opinion_reasonableness", "opex_opinion_reasonableness", "completion_test_definitions"],
        owners=[Department.INDEPENDENT_ENGINEER, Department.LENDERS],
        unlocks_capital=[CapitalType.DFI_MEZZ_GUARANTEES, CapitalType.SENIOR_DEBT_COMMITMENT],
        unlocks_state=BankabilityState.STRUCTURALLY_BANKABLE,
    ),
    GateDefinition(
        id="G7_INSURANCE_BOUND", name="Insurance Bound (CAR/EAR + DSU/BI + Liability)",
        required_evidence=["car_ear_bound", "dsu_bi_bound", "liability_bound", "lenders_loss_payee", "deductibles_accepted", "exclusions_register_reviewed"],
        owners=[Department.TREASURY, Department.LEGAL, Department.LENDERS],
        unlocks_capital=[CapitalType.SENIOR_DEBT_COMMITMENT],
        unlocks_state=BankabilityState.CREDIT_APPROVED,
    ),
    GateDefinition(
        id="G8_AUDIT_GRADE_MODEL", name="Audit-Grade Model Signed Off",
        required_evidence=["base_case_model", "downside_cases", "covenant_suite_defined", "dsra_maintenance_reserve_logic", "hedging_plan", "model_consistency_with_ie"],
        owners=[Department.FINANCE, Department.LENDERS],
        unlocks_capital=[CapitalType.SENIOR_DEBT_COMMITMENT],
        unlocks_state=BankabilityState.CREDIT_APPROVED,
    ),
    GateDefinition(
        id="G9_PERMITS_SAFE", name="Permits Complete + Appeal Risk Managed",
        required_evidence=["eia_permit_granted", "ancillary_permits_granted", "legal_opinion_on_appeal_risk", "stakeholder_management_plan_v2"],
        owners=[Department.PROJECT, Department.LEGAL],
        unlocks_capital=[CapitalType.SENIOR_DEBT_COMMITMENT],
        unlocks_state=BankabilityState.CREDIT_APPROVED,
    ),
    GateDefinition(
        id="G10_FINANCIAL_CLOSE_CP", name="Financial Close (CP Checklist Satisfied)",
        required_evidence=["cp_checklist_completed", "equity_injected", "dsra_funded", "security_package_perfected", "insurance_certificates_delivered", "all_major_contracts_executed"],
        owners=[Department.LENDERS, Department.LEGAL, Department.TREASURY, Department.FINANCE],
        unlocks_capital=[CapitalType.DEBT_DRAWDOWN],
        unlocks_state=BankabilityState.FINANCEABLE,
    ),
    GateDefinition(
        id="G11_COD_STABILIZATION", name="COD + Stabilization",
        required_evidence=["cod_certificate", "performance_tests_passed", "six_to_twelve_months_stable_ops", "mrv_reporting_live"],
        owners=[Department.PROJECT, Department.ENGINEERING, Department.FINANCE],
        unlocks_capital=[CapitalType.REFINANCE_BONDS_INFRA],
        unlocks_state=BankabilityState.REFINANCING_ELIGIBLE,
    ),
]

GATE_INDEX: dict[str, GateDefinition] = {g.id: g for g in GATE_REGISTRY}


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
