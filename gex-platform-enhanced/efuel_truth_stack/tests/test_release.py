"""Release predicate: clean drawdown releasable; flipping each check flips it."""

from datetime import date

from efuel_truth_stack.enums import EntryType, FundingSourceType
from efuel_truth_stack.ledger import new_entry, utc
from efuel_truth_stack.models import Allocation, DebtCommitment
from efuel_truth_stack.release import evaluate_release_predicate

T1 = utc(2030, 3, 11)
VF = date(2030, 1, 1)


def _check(res, name):
    return next(c for c in res.checks if c.check == name)


def _expire_claim(led, claim_id):
    """v0.3.1: a lapse is a FACT about validity, not a state demotion — modelled
    as a correction row narrowing valid_to (fact-driven to_state demotion is now
    a ToStateViolation; it was a griefing vector)."""
    led.append(new_entry(project_id="PRJ1", entry_type=EntryType.CONTRACT, produced_by="projectco_cfo",
                         valid_from=VF, valid_to=date(2030, 2, 28), recorded_at=T1,
                         payload={"claim_id": claim_id,
                                  "reason": "coverage lapsed — validity narrowed"}))


def test_clean_drawdown_is_releasable(clean):
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments)
    assert res.releasable, [(c.check, c.reason) for c in res.failed]
    assert len(res.checks) == 9 and all(c.passed for c in res.checks)


def test_flip_initial_cps(clean):
    _expire_claim(clean.ledger, "clm_permits_core_env_permit")
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "initial_cps_satisfied").passed


def test_flip_ongoing_cps(clean):
    _expire_claim(clean.ledger, "clm_independent_engineer_ie_certificate")
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "ongoing_cps_satisfied").passed


def test_flip_approvals_fresh_bogus_hash(clean):
    clean.ledger.append(new_entry(project_id="PRJ1", entry_type=EntryType.APPROVAL_DECISION,
                                  produced_by="facility_agent", valid_from=VF, recorded_at=T1,
                                  payload={"check_id": "x", "outcome": "approve",
                                           "approved_evidence_hashes": ["deadbeef" * 8]}))
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "approvals_fresh").passed


def test_flip_evidence_backed(clean):
    cl = clean.drawdown.cost_lines[0].model_copy(update={"cost_line_id": "cl_missing"})
    dd = clean.drawdown.model_copy(update={"cost_lines": [cl]})
    res = evaluate_release_predicate(dd, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "evidence_backed").passed


def test_flip_eligible_cost_balanced(clean):
    cl = clean.drawdown.cost_lines[0].model_copy(
        update={"allocations": [Allocation(source=FundingSourceType.SENIOR_DEBT, amount=500_000.0)]})
    dd = clean.drawdown.model_copy(update={"cost_lines": [cl]})
    res = evaluate_release_predicate(dd, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "eligible_cost_balanced").passed


def test_flip_funding_ratio(clean):
    small = {FundingSourceType.SENIOR_DEBT: DebtCommitment(
        id="c", source_type=FundingSourceType.SENIOR_DEBT, currency="EUR",
        committed_amount=100_000.0, drawable_amount=100_000.0)}
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, small)
    assert not res.releasable and not _check(res, "funding_ratio_respected").passed


def test_flip_reconciles(clean):
    dd = clean.drawdown.model_copy(update={"amount_by_source": {FundingSourceType.SENIOR_DEBT: 950_000.0}})
    res = evaluate_release_predicate(dd, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "reconciles").passed


def test_flip_no_open_blocking_event(clean):
    clean.ledger.append(new_entry(project_id="PRJ1", entry_type=EntryType.AUDIT_EVENT,
                                  produced_by="system", valid_from=VF, recorded_at=T1,
                                  payload={"event_type": "drawstop", "open": True}))
    res = evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments)
    assert not res.releasable and not _check(res, "no_open_blocking_event").passed


def test_flip_account_release(make_scenario):
    sc = make_scenario(include_release=False)
    res = evaluate_release_predicate(sc.drawdown, sc.ledger, sc.commitments)
    assert not res.releasable and not _check(res, "account_release_authorised").passed


def test_approval_goes_stale_when_evidence_superseded(clean):
    """Required: an approval bound to a fact's hash fails approvals_fresh once that fact is superseded."""
    led, dd, coms = clean.ledger, clean.drawdown, clean.commitments
    fact = new_entry(entry_id="offtake_v1", project_id="PRJ1", entry_type=EntryType.OFFTAKE_PROOF,
                     produced_by="offtaker", valid_from=VF, recorded_at=utc(2030, 3, 10),
                     payload={"doc": "offtake_schedule_v1"})
    led.append(fact)
    led.append(new_entry(project_id="PRJ1", entry_type=EntryType.APPROVAL_DECISION,
                         produced_by="facility_agent", valid_from=VF, recorded_at=utc(2030, 3, 10),
                         payload={"check_id": "cp_offtake", "outcome": "approve",
                                  "approved_evidence_hashes": [fact.hash]}))
    # fresh: the approved hash is still current
    assert evaluate_release_predicate(dd, led, coms).releasable

    # supersede the approved evidence with a new version -> old hash no longer current
    led.append(new_entry(project_id="PRJ1", entry_type=EntryType.OFFTAKE_PROOF, produced_by="offtaker",
                         valid_from=VF, recorded_at=utc(2030, 4, 1), supersedes="offtake_v1",
                         payload={"doc": "offtake_schedule_v2"}))
    res = evaluate_release_predicate(dd, led, coms)
    assert not res.releasable and not _check(res, "approvals_fresh").passed
