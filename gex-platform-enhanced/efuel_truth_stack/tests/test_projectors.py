"""Projectors: claim folding (transitions enforced) and node rollup (worst-of)."""

from datetime import date

import pytest

from efuel_truth_stack.enums import ClaimState, EntryType
from efuel_truth_stack.ledger import Ledger, new_entry, utc
from efuel_truth_stack.projectors import (
    ProjectionError, fold_claims, node_is_green, rollup_nodes,
)


def _claim_row(led, *, claim_id, to_state, node="insurance", ct="car_dsu_current",
               recorded, value=True, supersedes=None, valid_to=None):
    """v0.3: terminal-valid states are not expressible on a fact row ('verified'
    emits fact + explicit approval_decision). v0.3.1: demoting states are not
    either — lapse is modelled by narrowing valid_to. Only non-terminal
    progression (submitted) remains payload-expressible on a fact row."""
    fact_payload = {"claim_id": claim_id, "claim_type": ct, "subject_node": node,
                    "value_type": "boolean", "value": value}
    if to_state not in ("verified", None):
        fact_payload["to_state"] = to_state
    entry = led.append(new_entry(
        project_id="P", entry_type=EntryType.CONTRACT, produced_by="insurer",
        verified_by="lenders_market_adviser", valid_from=date(2030, 1, 1),
        valid_to=valid_to, recorded_at=recorded,
        supersedes=supersedes,
        payload=fact_payload,
    ))
    if to_state == "verified":
        led.append(new_entry(
            project_id="P", entry_type=EntryType.APPROVAL_DECISION,
            produced_by="independent_engineer", valid_from=date(2030, 1, 1),
            recorded_at=recorded, entry_id=f"{entry.id}_appr",
            payload={"claim_id": claim_id, "outcome": "approve"},
        ))
    return entry


def test_fold_drives_claim_to_verified():
    led = Ledger()
    _claim_row(led, claim_id="c", to_state="verified", recorded=utc(2030, 3, 1))
    claims = fold_claims(led)
    assert claims["c"].state == ClaimState.VERIFIED
    assert claims["c"].evidence_refs and claims["c"].evidence_refs[0].evidence_hash


def test_illegal_transition_raises():
    led = Ledger()
    _claim_row(led, claim_id="c", to_state="verified", recorded=utc(2030, 3, 1))
    _claim_row(led, claim_id="c", to_state="submitted", recorded=utc(2030, 3, 2))  # verified->submitted illegal
    with pytest.raises(ProjectionError):
        fold_claims(led)


def test_node_green_then_not_green_when_expired():
    led = Ledger()
    _claim_row(led, claim_id="c", to_state="verified", recorded=utc(2030, 3, 1))
    nodes = rollup_nodes(fold_claims(led), valid_time=date(2030, 3, 1))
    assert node_is_green(nodes["insurance"])

    # v0.3.1: lapse = validity-narrowing correction (state stays VERIFIED but the
    # claim is no longer valid at vt) — not a fact-driven state demotion.
    _claim_row(led, claim_id="c", to_state=None, valid_to=date(2030, 2, 1),
               recorded=utc(2030, 3, 5))
    nodes2 = rollup_nodes(fold_claims(led), valid_time=date(2030, 3, 1))
    assert not node_is_green(nodes2["insurance"])


def test_node_not_green_when_required_claim_missing():
    led = Ledger()
    # permits_core needs 5 claims; supply only one -> node has missing claims
    _claim_row(led, claim_id="c", to_state="verified", node="permits_core", ct="env_permit",
               recorded=utc(2030, 3, 1))
    nodes = rollup_nodes(fold_claims(led), valid_time=date(2030, 3, 1))
    assert not node_is_green(nodes["permits_core"])
    assert "construction_permit" in nodes["permits_core"].missing_claims
