"""Models: kind/entry_type invariant, content hash, transitions, subtypes, immutability."""

from datetime import date

import pytest
from pydantic import ValidationError

from efuel_truth_stack.enums import (
    ClaimState, CommitmentSubtype, EntryType, FundingSourceType, LedgerKind, can_transition,
)
from efuel_truth_stack.ledger import utc
from efuel_truth_stack.models import (
    CanonicalLedgerEntry, DebtCommitment, GrantCommitment, compute_entry_hash,
)


def _entry(**kw):
    base = dict(id="e1", project_id="P", kind=LedgerKind.FACT, entry_type=EntryType.MEASUREMENT,
                produced_by="metering_mrv_actor", valid_from=date(2030, 1, 1), recorded_at=utc(2030, 1, 2),
                payload={"value": 1})
    base.update(kw)
    return CanonicalLedgerEntry(**base)


def test_kind_must_admit_entry_type():
    with pytest.raises(ValidationError):
        _entry(kind=LedgerKind.FACT, entry_type=EntryType.APPROVAL_DECISION)  # decision type, fact kind
    # valid mapping is accepted
    e = _entry(kind=LedgerKind.DECISION, entry_type=EntryType.APPROVAL_DECISION, produced_by="facility_agent")
    assert e.entry_type == EntryType.APPROVAL_DECISION


def test_hash_autocomputed_and_content_sensitive():
    e1 = _entry(payload={"value": 1})
    e2 = _entry(id="e2", payload={"value": 2})
    assert e1.hash and len(e1.hash) == 64
    assert e1.hash != e2.hash  # different payload -> different version hash
    # recorded_at is NOT part of the hash (re-recording must not invalidate approvals)
    same = _entry(id="e3", recorded_at=utc(2031, 5, 5), payload={"value": 1})
    assert same.hash == e1.hash


def test_ledger_row_is_immutable():
    e = _entry()
    with pytest.raises(ValidationError):
        e.payload = {"value": 99}  # frozen


def test_claim_state_transitions():
    assert can_transition(ClaimState.ASSERTED, ClaimState.SUBMITTED)
    assert can_transition(ClaimState.SUBMITTED, ClaimState.VERIFIED)
    assert can_transition(ClaimState.VERIFIED, ClaimState.SUPERSEDED)
    assert not can_transition(ClaimState.ASSERTED, ClaimState.VERIFIED)   # no skipping
    assert not can_transition(ClaimState.SUPERSEDED, ClaimState.VERIFIED)  # terminal sink


def test_funding_commitment_subtyped():
    d = DebtCommitment(id="d", source_type=FundingSourceType.SENIOR_DEBT, currency="EUR",
                       committed_amount=1.0, drawable_amount=1.0, margin=0.025)
    g = GrantCommitment(id="g", source_type=FundingSourceType.GRANT, currency="EUR",
                        committed_amount=1.0, drawable_amount=1.0, reimbursement_basis="milestone")
    assert d.subtype == CommitmentSubtype.DEBT and d.margin == 0.025
    assert g.subtype == CommitmentSubtype.GRANT and g.reimbursement_basis == "milestone"
