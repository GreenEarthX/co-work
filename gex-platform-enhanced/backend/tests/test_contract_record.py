"""
The contract record's pure core (Phase 1 of "One contract record", 2026-11-06).

Sub-legs (one per buyer), clauses, the three hashes and the Merkle root
(trading_book/canonical.py), V01 per sub-leg and V14 (validation.py), and the
scheme-2 event hash (record.py). No database.
"""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.trading_book import canonical, record, validation
from app.trading_book.terms import CLAUSE_TYPES, TermsIn

S, B1, B2 = ("00000000-0000-4000-8000-0000000083a1", "00000000-0000-4000-8000-0000000083b1",
             "00000000-0000-4000-8000-0000000083b2")


def _sub_leg(n: int, buyer: str, qty: str, price: str) -> list[dict]:
    first = 2 * n - 1
    return [
        {"seq": first, "sub_leg": n, "leg_role": "product", "payer": S, "receiver": buyer, "flows": [
            {"seq": 1, "flow_type": "physical", "period_start": "2027-01-01", "period_end": "2027-01-31",
             "settle_date": "2027-01-31", "quantity": qty, "unit": "t"}]},
        {"seq": first + 1, "sub_leg": n, "leg_role": "payment", "payer": buyer, "receiver": S, "flows": [
            {"seq": 1, "flow_type": "fixed_cash", "period_start": "2027-01-01", "period_end": "2027-01-31",
             "settle_date": "2027-02-28", "quantity": qty, "unit": "t", "unit_price": price,
             "quantity_basis": "delivered", "quantity_source_flow": f"{first}.1"}]},
    ]


def frame() -> dict:
    """One plant, two offtakers: shared terms + a sub-leg per buyer (Q2)."""
    return {"settlement": "physical", "commodity": "EMEOH", "currency": "EUR",
            "quality_spec": {"certification": "RFNBO"},
            "legs": _sub_leg(1, B1, "600", "900") + _sub_leg(2, B2, "400", "910"),
            "clauses": [{"seq": 1, "clause_type": "force_majeure", "attrs": {"ref": "TEST FM-1"}},
                        {"seq": 2, "clause_type": "commitment", "sub_leg": 1, "attrs": {"take_or_pay_pct": 80}}]}


def _hashes(payload: dict) -> dict:
    return canonical.hashes(TermsIn.model_validate(payload))


def test_a_frame_with_two_buyers_validates_as_a_contract():
    assert validation.validate(TermsIn.model_validate(frame()), "contract") == []


def test_v01_is_two_legs_per_sub_leg():
    p = frame()
    p["legs"] = [leg for leg in p["legs"] if not (leg["sub_leg"] == 2 and leg["leg_role"] == "payment")]
    assert "V01" in validation.validate(TermsIn.model_validate(p), "contract")


def test_v07_is_checked_in_each_sub_leg():
    p = frame()
    p["legs"][3]["payer"], p["legs"][3]["receiver"] = S, B2          # buyer 2's payment runs the wrong way
    assert "V07" in validation.validate(TermsIn.model_validate(p), "contract")


@pytest.mark.parametrize("breaks", [
    lambda p: p["clauses"].append({"seq": 3, "clause_type": "not_a_clause", "attrs": {}}),
    lambda p: p["clauses"].append({"seq": 4, "clause_type": "damages", "sub_leg": 9, "attrs": {}}),
    lambda p: p["clauses"].append({"seq": 1, "clause_type": "damages", "attrs": {}}),     # seq taken
    lambda p: p["legs"][3].update(seq=1),                                                  # leg seq taken
    lambda p: p.setdefault("sub_legs", []).append({"seq": 7, "rank": 1}),
])
def test_v14_structure(breaks):
    p = frame()
    breaks(p)
    assert "V14" in validation.validate(TermsIn.model_validate(p), "contract")


def test_changing_one_buyers_part_leaves_the_other_buyers_hash_and_the_shared_hash():
    """The basis of Q2: only the buyers whose part changed re-confirm."""
    before = _hashes(frame())
    p = frame()
    p["legs"][3]["flows"][0]["unit_price"] = "915"                  # buyer 2's price
    after = _hashes(p)
    assert after["sub_legs"][1] == before["sub_legs"][1]
    assert after["shared_hash"] == before["shared_hash"]
    assert after["sub_legs"][2] != before["sub_legs"][2]
    assert after["terms_hash"] != before["terms_hash"]


def test_changing_a_shared_term_moves_the_shared_hash_only():
    before = _hashes(frame())
    p = frame()
    p["clauses"][0]["attrs"]["ref"] = "TEST FM-2"
    after = _hashes(p)
    assert after["sub_legs"] == before["sub_legs"] and after["shared_hash"] != before["shared_hash"]


def test_a_buyers_clause_belongs_to_its_sub_leg():
    before = _hashes(frame())
    p = frame()
    p["clauses"][1]["attrs"]["take_or_pay_pct"] = 70
    after = _hashes(p)
    assert after["sub_legs"][2] == before["sub_legs"][2] and after["sub_legs"][1] != before["sub_legs"][1]


def test_the_root_is_the_merkle_root_and_each_buyer_can_prove_its_part():
    h = _hashes(frame())
    leaves = [h["shared_hash"], h["sub_legs"][1], h["sub_legs"][2]]
    assert h["terms_hash"] == canonical.merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        proof = canonical.merkle_proof(leaves, i)
        assert canonical.verify_proof(leaf, proof, h["terms_hash"])
        assert not canonical.verify_proof("0" * 64, proof, h["terms_hash"])


def test_a_bilateral_trade_keeps_the_spec_canonical_shape():
    p = frame()
    p["legs"], p["clauses"] = _sub_leg(1, B1, "600", "900"), []
    c = canonical.canonical_dict(TermsIn.model_validate(p))
    assert set(c) == {"settlement", "commodity", "quality_spec", "currency", "legs"}
    assert all("sub_leg" not in leg for leg in c["legs"])


def test_order_of_legs_and_clauses_does_not_move_any_hash():
    p = copy.deepcopy(frame())
    p["legs"].reverse()
    p["clauses"].reverse()
    assert _hashes(p) == _hashes(frame())


def test_the_clause_types_are_the_migrations():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "alembic/versions/083_contract_record_core.py").read_text())
    found = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(getattr(t, "id", None) == "CLAUSE_TYPES" for t in node.targets))
    assert tuple(ast.literal_eval(found)) == CLAUSE_TYPES


def test_the_event_hash_covers_its_timestamp():
    """078's chain left `at` outside the hash; scheme 2 does not."""
    base = dict(contract_ref="GEX-TB-2026-000001", seq=1, event_type="CREATED_FROM_MATCH", version=1,
                sub_leg=None, terms_hash="a" * 64, actor="u_test", company="test_co", note=None, prev=None)
    t = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    assert record.event_hash(**base, at=t) != record.event_hash(**base, at=t.replace(second=1))
    assert record.event_hash(**base, at=t) == record.event_hash(**base, at=t.isoformat())
