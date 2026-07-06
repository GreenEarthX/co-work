"""
enums.py — the controlled vocabularies of the e-fuel truth stack.

Faithful, hand-written transcription of `enums` in efuel_truth_stack_v0_2.json.
A spec-consistency test (tests/test_spec_consistency.py) asserts these match the
JSON exactly, so they cannot silently drift from the source of truth.

Per the guardrail: do not change any enum value here without changing the JSON
spec first (and the spec is reviewed). These are inputs, not implementation
conveniences.
"""

from __future__ import annotations

from enum import Enum


class LedgerKind(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    DERIVED = "derived"


class EntryType(str, Enum):
    # kind = fact
    MEASUREMENT = "measurement"
    CONTRACT = "contract"
    COST_INVOICE = "cost_invoice"
    CASH_MOVEMENT = "cash_movement"
    CERTIFICATE = "certificate"
    PERMIT = "permit"
    INSURANCE_DOC = "insurance_doc"
    OFFTAKE_PROOF = "offtake_proof"
    # kind = decision
    APPROVAL_DECISION = "approval_decision"
    WAIVER = "waiver"
    REJECTION = "rejection"
    RELEASE_DECISION = "release_decision"
    DRAWSTOP = "drawstop"
    CLAWBACK_NOTICE = "clawback_notice"
    # kind = derived
    RECONCILIATION_RESULT = "reconciliation_result"
    VALIDATION_RESULT = "validation_result"
    PROJECTION_SNAPSHOT = "projection_snapshot"
    AUDIT_EVENT = "audit_event"


# kind -> the entry_types it admits. Enforced on every CanonicalLedgerEntry.
ENTRY_TYPES_BY_KIND: dict[LedgerKind, frozenset[EntryType]] = {
    LedgerKind.FACT: frozenset({
        EntryType.MEASUREMENT, EntryType.CONTRACT, EntryType.COST_INVOICE,
        EntryType.CASH_MOVEMENT, EntryType.CERTIFICATE, EntryType.PERMIT,
        EntryType.INSURANCE_DOC, EntryType.OFFTAKE_PROOF,
    }),
    LedgerKind.DECISION: frozenset({
        EntryType.APPROVAL_DECISION, EntryType.WAIVER, EntryType.REJECTION,
        EntryType.RELEASE_DECISION, EntryType.DRAWSTOP, EntryType.CLAWBACK_NOTICE,
    }),
    LedgerKind.DERIVED: frozenset({
        EntryType.RECONCILIATION_RESULT, EntryType.VALIDATION_RESULT,
        EntryType.PROJECTION_SNAPSHOT, EntryType.AUDIT_EVENT,
    }),
}

KIND_OF_ENTRY_TYPE: dict[EntryType, LedgerKind] = {
    et: kind for kind, ets in ENTRY_TYPES_BY_KIND.items() for et in ets
}


class ClaimState(str, Enum):
    ASSERTED = "asserted"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    SATISFIED = "satisfied"
    WAIVED = "waived"
    EXPIRED = "expired"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"


TERMINAL_VALID: frozenset[ClaimState] = frozenset({
    ClaimState.VERIFIED, ClaimState.SATISFIED, ClaimState.WAIVED,
})
TERMINAL_INVALID: frozenset[ClaimState] = frozenset({
    ClaimState.EXPIRED, ClaimState.REJECTED, ClaimState.FAILED, ClaimState.SUPERSEDED,
})

# Legal forward transitions (claim_state.transitions in the spec).
CLAIM_STATE_TRANSITIONS: dict[ClaimState, frozenset[ClaimState]] = {
    ClaimState.ASSERTED: frozenset({ClaimState.SUBMITTED, ClaimState.FAILED}),
    ClaimState.SUBMITTED: frozenset({ClaimState.VERIFIED, ClaimState.REJECTED}),
    ClaimState.VERIFIED: frozenset({ClaimState.SATISFIED, ClaimState.EXPIRED, ClaimState.SUPERSEDED}),
    ClaimState.SATISFIED: frozenset({ClaimState.EXPIRED, ClaimState.FAILED, ClaimState.SUPERSEDED}),
    ClaimState.WAIVED: frozenset({ClaimState.EXPIRED, ClaimState.FAILED, ClaimState.SUPERSEDED}),
    ClaimState.REJECTED: frozenset({ClaimState.SUBMITTED}),
    ClaimState.EXPIRED: frozenset({ClaimState.SUBMITTED}),
    ClaimState.FAILED: frozenset({ClaimState.SUBMITTED}),
    ClaimState.SUPERSEDED: frozenset(),  # terminal-invalid sink; spec lists no exit
}


def is_terminal_valid(state: ClaimState) -> bool:
    return state in TERMINAL_VALID


def can_transition(src: ClaimState, dst: ClaimState) -> bool:
    """True iff src -> dst is in the spec's transition table."""
    return dst in CLAIM_STATE_TRANSITIONS.get(src, frozenset())


class ValueType(str, Enum):
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    DOC_REF = "doc_ref"


class Layer(str, Enum):
    MOLECULE = "molecule"
    CERTIFICATION = "certification"
    ENGINEERING = "engineering"
    COMMERCIAL = "commercial"
    FINANCIAL = "financial"
    ACCOUNTS = "accounts"
    CAPITAL = "capital"
    PUBLIC_CONTROLS = "public_controls"


class CPClass(str, Enum):
    INITIAL = "initial"
    SUBSEQUENT = "subsequent"
    ONGOING = "ongoing"


class FundingSourceType(str, Enum):
    EQUITY = "equity"
    SENIOR_DEBT = "senior_debt"
    MEZZANINE = "mezzanine"
    DFI_ECA = "dfi_eca"
    GRANT = "grant"


class CommitmentSubtype(str, Enum):
    DEBT = "DebtCommitment"
    GRANT = "GrantCommitment"
    EQUITY = "EquityCommitment"


class AccountType(str, Enum):
    EQUITY_PROCEEDS = "equity_proceeds"
    DEBT_PROCEEDS = "debt_proceeds"
    GRANT_DESIGNATED = "grant_designated"
    CONSTRUCTION_DISBURSEMENT = "construction_disbursement"
    WORKING_CAPITAL = "working_capital"
    REVENUE_COLLECTION = "revenue_collection"
    TAX_RESERVE = "tax_reserve"
    OPERATING = "operating"
    DSRA = "dsra"
    MMRA = "mmra"
    STACK_REPLACEMENT_RESERVE = "stack_replacement_reserve"
    RAMP_UP_RESERVE = "ramp_up_reserve"
    INSURANCE_PROCEEDS = "insurance_proceeds"
    DISTRIBUTION_LOCKUP = "distribution_lockup"


class EventType(str, Enum):
    DRAWDOWN_REQUEST = "drawdown_request"
    DRAWSTOP = "drawstop"
    DEFAULT = "default"
    MATERIAL_ADVERSE_EFFECT = "material_adverse_effect"
    CERTIFICATION_FAILURE = "certification_failure"
    RETROACTIVE_DECERTIFICATION = "retroactive_decertification"
    ELIGIBILITY_BREACH = "eligibility_breach"
    COST_OVERRUN = "cost_overrun"
    DELAY = "delay"
    CLAWBACK = "clawback"
    CURE = "cure"
    WAIVER = "waiver"


# Events that, while open, block a release (release_predicate.no_open_blocking_event).
BLOCKING_EVENTS: frozenset[EventType] = frozenset({
    EventType.DRAWSTOP, EventType.DEFAULT, EventType.CERTIFICATION_FAILURE,
    EventType.ELIGIBILITY_BREACH, EventType.RETROACTIVE_DECERTIFICATION,
})


class ApprovalOutcome(str, Enum):
    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ApprovalThreshold(str, Enum):
    SINGLE = "single"
    MAJORITY = "majority"
    SUPER_MAJORITY = "super_majority"
    UNANIMOUS = "unanimous"


class ReconciliationOp(str, Enum):
    EXACT = "exact"
    TOLERANCE_PCT = "tolerance_pct"
    SETTLEMENT_LAG = "settlement_lag"
    ACCRUAL_AWARE = "accrual_aware"
    FX_NORMALISED = "fx_normalised"
    NET_OF_RETENTION = "net_of_retention"
    NET_OF_VAT = "net_of_vat"
    THRESHOLD = "threshold"        # value <= limit (e.g. ghg_pass); resolved in review
