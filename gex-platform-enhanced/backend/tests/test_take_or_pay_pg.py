"""
Take-or-pay shortfall per contract year (GreenMesh Phase 2 Step 4; core/take_or_pay.py).

On REAL confirmed order-book trades (G-25) with two contract years of 1 t each (Jan 2027,
Jan 2028) and a typed commitment clause: the shortfall arithmetic, an amount only with a
stated price, no figure for a missing term, a waiver counted DECLARED, and the parties-only read.
Plus V15's checks on the commitment clause (pure). Throwaway database (pg_store).
"""
from __future__ import annotations

from datetime import date

import pytest

from test_contract_clauses import PAYMENT, _terms
from test_delivery_inspection_pg import (GOOD, OFF, _accounts, _appoint, _certify, _confirm, _doc,  # noqa: F401
                                         _docs_dir, _inspection, _party, inspectors)
from test_delivery_record_pg import _parties, _refused, world  # noqa: F401
from test_evidence_pack_pg import client, seeded  # noqa: F401
from test_order_book_token_pg import DELIVERY_CIF, confirmed_order_book_trade, custody_token  # noqa: F401

LATER = date(2029, 6, 1)


def _top(pct="80", price=None, form="TAKE_OR_PAY"):
    attrs = {"commitment_form": form}
    if pct is not None:
        attrs["take_or_pay_pct"] = pct
    if price is not None:
        attrs["shortfall_price"] = price
    return {"clause_type": "commitment", "attrs": attrs}


def _report(contract_id, as_of=LATER):
    from app.core import take_or_pay as top

    return top.for_party(_parties()[0], contract_id, as_of)


def test_the_shortfall_per_contract_year_and_its_amount_at_the_stated_price(custody_token):
    d = _appoint(_inspection(custody_token, kg=400, clauses=(DELIVERY_CIF, _top(price="100"), PAYMENT),
                             extra_year=True))
    _certify(d, GOOD)                                                     # 400 kg accepted, VERIFIED
    r = _report(d["contract_id"])
    assert r["computed"] is True and r["take_or_pay_pct"] == "80"
    y1, y2 = r["years"]
    assert (y1["start"], y1["end"], y2["start"]) == ("2027-01-01", "2028-01-01", "2028-01-01")
    assert (y1["contracted_t"], y1["required_t"], y1["accepted_t"], y1["shortfall_t"]) == ("1", "0.8", "0.4", "0.4")
    assert (y1["amount"], y1["currency"], y1["label"]) == ("40.00", "EUR", "VERIFIED")
    assert (y2["accepted_t"], y2["shortfall_t"], y2["amount"]) == ("0", "0.8", "80.00")
    assert y1["deliveries"] == [d["id"]] and y1["provisional"] is False
    assert r["availability"]["computed"] is False, "no guarantee in the terms: no availability, no penalty"
    assert _report(d["contract_id"], date(2027, 6, 1))["years"][0]["provisional"] is True


def test_a_missing_term_gives_no_figure(custody_token):
    from app.core import market_engine as me
    from app.core import take_or_pay as top

    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"], clauses=(DELIVERY_CIF, PAYMENT))
    r = _report(t["contract_id"])
    assert r["computed"] is False and r["reason"].startswith("MISSING") and "commitment" in r["reason"]
    conn = me._conn()
    try:
        # The clause read from terms carrying another form, without touching the trade: compute()'s own branch.
        from app.trading_book import clauses as cl
        assert cl.read([{"sub_leg_id": None, **_top(pct=None, form="TAKE_AND_PAY")}], None)["commitment"]["commitment_form"] \
            == "TAKE_AND_PAY"
        assert top.compute(conn, "00000000-0000-4000-8000-000000000000")["computed"] is False
    finally:
        conn.close()


def test_without_a_stated_price_there_is_a_shortfall_but_no_amount(custody_token):
    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"], clauses=(DELIVERY_CIF, _top(), PAYMENT))
    y1 = _report(t["contract_id"])["years"][0]
    assert (y1["shortfall_t"], y1["amount"]) == ("0.8", None) and "no shortfall price" in y1["amount_reason"]


def test_a_framework_commitment_has_no_shortfall(custody_token):
    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"],
                                   clauses=(DELIVERY_CIF, _top(pct=None, form="FRAMEWORK"), PAYMENT))
    r = _report(t["contract_id"])
    assert r["computed"] is False and "FRAMEWORK" in r["reason"]


def test_a_waiver_accepted_delivery_counts_declared(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=400, clauses=(DELIVERY_CIF, _top(), PAYMENT)))
    _certify(d, OFF)
    di.propose_waiver(seller, d["id"], _doc(seller, d, "WAIVER"))
    _confirm(d, "WAIVER_CONFIRMED", buyer, _party("g_buyer2", buyer.company_id))
    y1 = _report(d["contract_id"])["years"][0]
    assert (y1["accepted_declared_t"], y1["accepted_verified_t"], y1["label"]) == ("0.4", "0", "DECLARED")
    assert y1["shortfall_t"] == "0.4"


def test_only_the_parties_read_it_and_gex_reads_no_amounts(custody_token):
    from app.core import market_engine as me
    from app.core import take_or_pay as top

    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"], clauses=(DELIVERY_CIF, _top(), PAYMENT))
    _refused(lambda: top.for_party(me.Party(business_function="COMMERCIAL", user_id="u_x", company_id="test_pack_other"), t["contract_id"]), status=404)
    _refused(lambda: top.for_party(me.Party(business_function="COMMERCIAL", user_id="u_gex", company_id="greenearthx", is_admin=True), t["contract_id"]),
             status=403, code="GEX_READS_NO_TERMS")
    assert top.for_party(_parties()[1], t["contract_id"], LATER)["computed"] is True      # the buyer reads it too


@pytest.mark.parametrize("attrs", [
    {"commitment_form": "TAKE_OR_PAY"},                                   # no percentage
    {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": "120"},
    {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": "0"},
    {"commitment_form": "TAKE_AND_PAY", "take_or_pay_pct": "80"},         # a percentage without take-or-pay
    {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": "80", "shortfall_price": "-1"},
    {"commitment_form": "ALWAYS"},
], ids=["no-pct", "over-100", "zero", "pct-without-top", "negative-price", "unknown-form"])
def test_v15_refuses_a_malformed_commitment_clause(attrs):
    from app.trading_book import validation

    assert "V15" in validation.validate(_terms({"clause_type": "commitment", "attrs": attrs}), "order")


def test_g11_the_acceptance_record_is_filed_for_the_reviewer_and_verifies_nothing(custody_token, tmp_path, monkeypatch):
    import hashlib
    import json

    from app.core import take_or_pay as top
    from test_delivery_record_pg import _row as _row_su

    monkeypatch.setenv("GEX_EVIDENCE_DOCS_DIR", str(tmp_path))
    url = custody_token["url"]
    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=400, clauses=(DELIVERY_CIF, _top(), PAYMENT)))
    _refused(lambda: top.attach_g11_evidence(seller, d["id"]), status=409, code="DELIVERY_NOT_ACCEPTED")
    _certify(d, GOOD)
    _refused(lambda: top.attach_g11_evidence(buyer, d["id"]), status=403, code="DELIVERY_WRONG_PARTY")
    before = _row_su(url, "SELECT count(*) AS n FROM bankability_evidence")["n"]
    out = top.attach_g11_evidence(seller, d["id"])
    again = top.attach_g11_evidence(seller, d["id"])
    rows = _row_su(url, "SELECT count(*) AS n FROM evidence_documents WHERE evidence_key = %s AND sha256 = %s",
                   (top.G11_KEY, out["sha256"]))["n"]
    assert rows == 1 and again["sha256"] == out["sha256"], "idempotent"
    body = json.dumps(out["record"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(body).hexdigest() == out["sha256"]
    assert out["record"]["certificate"]["result"] == "PASS" and out["record"]["acceptance"]["label"] == "VERIFIED"
    assert "NOT VERIFIED BY GEX" in out["record"]["verification"]
    assert _row_su(url, "SELECT count(*) AS n FROM bankability_evidence")["n"] == before, "no evidence status is set"
