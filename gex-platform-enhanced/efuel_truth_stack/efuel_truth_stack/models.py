"""
models.py — Pydantic v2 models for every entity + supporting types.

Design rules enforced here (from the spec's non-negotiables):
  - CanonicalLedgerEntry is frozen (immutable after write) and validates the
    kind -> entry_type mapping. It carries NO claim_state: state is a projection.
  - The content `hash` binds approvals to an exact version; a correction is a new
    row (supersedes) with a different payload and therefore a different hash.
  - FundingCommitment is subtyped (Debt/Grant/Equity), never a flat 'source'.
  - Claim / Node are projection models (rebuilt by folding), not stored truth.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AccountType, ApprovalOutcome, ApprovalThreshold, ClaimState, CommitmentSubtype,
    ENTRY_TYPES_BY_KIND, EntryType, EventType, FundingSourceType, Layer, LedgerKind,
    ReconciliationOp, ValueType,
)


def compute_entry_hash(*, entry_type: str, produced_by: str, valid_from: Any,
                       valid_to: Any, payload: dict) -> str:
    """
    Deterministic content hash. Covers the fields whose change makes a fact a
    *different version* (so an approval bound to the old hash goes stale): the
    asserting actor, the valid-time window, the entry type, and the payload.
    transaction-time (recorded_at) is deliberately excluded — re-recording the
    same fact must not invalidate approvals.
    """
    body = {
        "entry_type": str(entry_type),
        "produced_by": produced_by,
        "valid_from": str(valid_from),
        "valid_to": str(valid_to),
        "payload": payload,
    }
    blob = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class CanonicalLedgerEntry(BaseModel):
    """Append-only, immutable, bitemporal project-truth row."""
    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str
    kind: LedgerKind
    entry_type: EntryType
    produced_by: str
    verified_by: Optional[str] = None
    valid_from: date                       # valid-time start (truth in the world)
    valid_to: Optional[date] = None        # valid-time end (None = open)
    recorded_at: datetime                  # transaction-time (when we recorded it)
    regulatory_cliff: Optional[date] = None
    payload: dict = Field(default_factory=dict)
    hash: str = ""
    version: int = 1
    supersedes: Optional[str] = None
    reconciliation_group_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _fill_hash(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("hash"):
            data = dict(data)
            data["hash"] = compute_entry_hash(
                entry_type=data.get("entry_type"),
                produced_by=data.get("produced_by"),
                valid_from=data.get("valid_from"),
                valid_to=data.get("valid_to"),
                payload=data.get("payload", {}),
            )
        return data

    @model_validator(mode="after")
    def _kind_admits_entry_type(self) -> "CanonicalLedgerEntry":
        admitted = ENTRY_TYPES_BY_KIND[self.kind]
        if self.entry_type not in admitted:
            raise ValueError(
                f"entry_type '{self.entry_type.value}' is not valid for kind "
                f"'{self.kind.value}' (allowed: {sorted(e.value for e in admitted)})"
            )
        return self

    def is_valid_at(self, valid_time: date) -> bool:
        if valid_time < self.valid_from:
            return False
        return self.valid_to is None or valid_time < self.valid_to


class EvidenceLink(BaseModel):
    """Evidence is a relationship, not a type: a hash-pinned backing link.

    v0.3: also the row shape of the `evidence_links` relation (spec
    §evidence_links) — many-to-many claim↔entry links (one certificate may back
    N claims); link_type ∈ supports | supersedes_basis | approval_basis.
    evidence_hash is the entry's content hash frozen at link time."""
    ledger_entry_id: str
    evidence_hash: str
    claim_id: Optional[str] = None
    approval_id: Optional[str] = None
    link_type: Optional[str] = None


class Claim(BaseModel):
    """Projection: the primary unit of truth, folded from the ledger."""
    id: str
    subject_node: str
    claim_type: str
    value_type: ValueType
    value: Any = None
    unit: Optional[str] = None
    state: ClaimState
    period: Optional[str] = None
    valid_from: date
    valid_to: Optional[date] = None
    evidence_refs: list[EvidenceLink] = Field(default_factory=list)
    authority_rule: str = ""
    superseded_by: Optional[str] = None

    def is_terminal_valid_at(self, valid_time: date) -> bool:
        from .enums import is_terminal_valid
        if not is_terminal_valid(self.state):
            return False
        if valid_time < self.valid_from:
            return False
        return self.valid_to is None or valid_time < self.valid_to


class Node(BaseModel):
    """Projection: rollup over required claims (worst-of)."""
    id: str
    layer: Layer
    label: str = ""
    depends_on: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    rolled_up_state: Optional[ClaimState] = None
    missing_claims: list[str] = Field(default_factory=list)


class ApprovalRequirement(BaseModel):
    check_id: str
    required_actor: str
    approval_threshold: ApprovalThreshold = ApprovalThreshold.SINGLE
    waivable: bool = True
    waiver_actor: Optional[str] = None
    waiver_scope: Optional[str] = None        # one_off | standing | None
    veto_right: bool = False
    drawstop_right: bool = False


class ApprovalDecision(BaseModel):
    """A decision row's structured view. Stale if any approved hash is no longer current."""
    id: str
    check_id: str
    actor: str
    outcome: ApprovalOutcome
    conditions: list[str] = Field(default_factory=list)
    approved_evidence_hashes: list[str] = Field(default_factory=list)
    valid_until: Optional[date] = None
    ledger_entry_id: str


# ── Funding commitments (subtyped) ───────────────────────────────────────────
class Tranche(BaseModel):
    tranche_id: str
    amount: float
    currency: str
    margin: Optional[float] = None
    availability_from: Optional[date] = None
    availability_to: Optional[date] = None
    maturity: Optional[date] = None


class FundingCommitment(BaseModel):
    """Base commitment. Subtype it — 'senior debt' is a commitment, not a source."""
    id: str
    subtype: CommitmentSubtype
    source_type: FundingSourceType
    currency: str
    committed_amount: float
    drawable_amount: float
    drawn_amount: float = 0.0
    cancelled_amount: float = 0.0
    repaid_amount: float = 0.0
    availability_from: Optional[date] = None
    availability_to: Optional[date] = None
    tranches: list[Tranche] = Field(default_factory=list)
    eligible_cost_categories: list[str] = Field(default_factory=list)
    conditions_precedent: list[str] = Field(default_factory=list)
    draw_order_rule: str = "pari_passu"       # equity_first | pro_rata | pari_passu
    pro_rata_group: Optional[str] = None
    cancellation_events: list[EventType] = Field(default_factory=list)


class DebtCommitment(FundingCommitment):
    subtype: CommitmentSubtype = CommitmentSubtype.DEBT
    margin: Optional[float] = None
    step_ups: list[float] = Field(default_factory=list)
    undrawn_fee: Optional[float] = None
    ticking_fee: Optional[float] = None
    security_rank: Optional[int] = None
    intercreditor_ref: Optional[str] = None
    final_maturity: Optional[date] = None


class GrantCommitment(FundingCommitment):
    subtype: CommitmentSubtype = CommitmentSubtype.GRANT
    reimbursement_basis: Optional[str] = None   # actual_cost | milestone
    clawback_conditions: list[str] = Field(default_factory=list)
    state_aid_reference: Optional[str] = None
    disbursement_ratio: Optional[float] = None


class EquityCommitment(FundingCommitment):
    subtype: CommitmentSubtype = CommitmentSubtype.EQUITY
    contingent_equity: Optional[float] = None
    completion_support: bool = False
    equity_first_flag: bool = False


# ── Eligible-cost matrix + drawdown ──────────────────────────────────────────
class Allocation(BaseModel):
    source: FundingSourceType
    amount: float
    eligible: bool = True
    eligibility_basis: str = ""


class EligibleCostLine(BaseModel):
    cost_line_id: str
    cost_category_id: str
    total_amount: float
    currency: str = "EUR"
    retention_pct: float = 0.0
    vat_treatment: str = "net"                  # gross | net
    required_evidence_type: EntryType = EntryType.COST_INVOICE
    allocations: list[Allocation] = Field(default_factory=list)

    def allocation_sum(self) -> float:
        return sum(a.amount for a in self.allocations)

    def eligible_sum(self) -> float:
        return sum(a.amount for a in self.allocations if a.eligible)


class DrawdownRequest(BaseModel):
    id: str
    project_id: str
    period: str
    cost_lines: list[EligibleCostLine] = Field(default_factory=list)
    amount_by_source: dict[FundingSourceType, float] = Field(default_factory=dict)
    evidence_refs: list[EvidenceLink] = Field(default_factory=list)


# ── Release + reconciliation result views ────────────────────────────────────
class CheckResult(BaseModel):
    check: str
    passed: bool
    reason: str
    approver: str = ""


class ReleaseResult(BaseModel):
    drawdown_id: str
    releasable: bool
    checks: list[CheckResult] = Field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


class ReconciliationResult(BaseModel):
    """Payload of a derived `reconciliation_result` ledger row."""
    constraint_id: str
    op: ReconciliationOp
    passed: bool
    reason: str
    detail: dict = Field(default_factory=dict)
    event_raised: Optional[EventType] = None
    period: Optional[str] = None
