"""
Title transfer and the token split (GreenMesh Phase 2 Step 3, sub-step 5; alembic 109; B1, B2,
B5; rulings R2, R3; T1 open). Stops before SETTLED.

Real confirmed order-book trades (G-25) on a custody-backed token (1000 kg allocated from a
closed RFNBO period), each with the title clause under test. B5's invariants, one test each
where they are new here: (1) children sum exactly to the parent; (2) one holder per quantity,
a SPLIT parent frozen; (3) no holder change before ACCEPTED or the title trigger; (4) title
before risk labelled, not refused; (6) a child keeps the parent's lineage and RFNBO result;
(7) the buyer reads no more of the seller's remainder than of the parent; (8) title before
acceptance and settlement before title refused. Throwaway database (pg_store).
"""
from __future__ import annotations

from decimal import Decimal

import psycopg2
import pytest

from test_contract_clauses import PAYMENT
from test_delivery_inspection_pg import (GOOD, _accounts, _appoint, _certify, _doc, _docs_dir,  # noqa: F401
                                         _inspection, _party, inspectors)
from test_delivery_record_pg import JAN, NOW, _parties, _refused, world  # noqa: F401
from test_delivery_record_pg import _row as _row_su
from test_evidence_pack_pg import _superuser, client, seeded  # noqa: F401
from test_order_book_token_pg import DELIVERY_CIF, confirmed_order_book_trade, custody_token  # noqa: F401

FOB = {"clause_type": "delivery", "attrs": {"incoterm": "FOB", "named_place": "Port of loading, BR"}}


def _title(passes):
    return {"clause_type": "title", "attrs": {"passes": passes}}


def _tok(url, token_id):
    return _row_su(url, "SELECT * FROM tokens WHERE id = %s", (token_id,))


def _accepted(custody_token, clauses, kg):
    """A delivery accepted on a PASS certificate from the agreed inspector."""
    d = _appoint(_inspection(custody_token, kg=kg, clauses=clauses))
    _certify(d, GOOD)
    from app.core import delivery_record as dr

    return dr.get_delivery(_parties()[0], d["id"])


def _children(url, parent):
    conn = _superuser(url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM token_split WHERE parent_token_id = %s ORDER BY kg", (parent,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def test_the_whole_token_moves_its_holder_and_settles_without_a_split(custody_token):
    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=1000, clauses=(DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT)))
    assert _tok(url, token)["holder_company_id"] is None, "invariant 3: no holder change before ACCEPTED"
    _certify(d, GOOD)
    from app.core import delivery_record as dr
    d = dr.get_delivery(seller, d["id"])
    assert d["status"] == "TITLE_TRANSFERRED" and d["title"]["transferred"] is True
    t = _tok(url, token)
    assert (t["holder_company_id"], t["lifecycle_state"]) == (buyer.company_id, "SETTLED")
    assert _children(url, token) == []
    title = [e for e in d["events"] if e["event_type"] == "DELIVERY_TITLE_TRANSFERRED"]
    assert len(title) == 1 and (title[0]["company_id"], title[0]["actor"]) == (None, "system:title")


def test_a_partial_title_splits_the_token_exactly_and_the_children_keep_its_lineage(custody_token):
    from app.core import delivery_title as dt
    from app.core import market_engine as me
    from app.core import order_book as ob

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    parent_before = _tok(url, token)
    d = _accepted(custody_token, (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT), kg=400)
    assert d["status"] == "TITLE_TRANSFERRED"
    kids = _children(url, token)
    assert [Decimal(k["kg"]) for k in kids] == [Decimal(400), Decimal(600)]
    assert sum(Decimal(k["kg"]) for k in kids) == Decimal(1000), "invariant 1: exactly the parent's kg"
    assert {k["holder_company_id"] for k in kids} == {buyer.company_id, seller.company_id}
    title_hash = next(e["event_hash"] for e in d["events"] if e["event_type"] == "DELIVERY_TITLE_TRANSFERRED")
    assert {k["event_hash"] for k in kids} == {title_hash}, "the split is the one title event's"
    parent = _tok(url, token)
    assert parent["lifecycle_state"] == "SPLIT" and parent["holder_company_id"] is None
    to_buyer = _tok(url, next(k["child_token_id"] for k in kids if k["holder_company_id"] == buyer.company_id))
    rest = _tok(url, next(k["child_token_id"] for k in kids if k["holder_company_id"] == seller.company_id))
    assert (to_buyer["lifecycle_state"], rest["lifecycle_state"]) == ("SETTLED", "MATCHED")
    for child in (to_buyer, rest):                                   # invariant 6 + the certificate (R3)
        assert child["parent_token_id"] == token
        for col in ("compliance_certifications", "certification_pathway", "carbon_intensity_gco2e_mj",
                    "mass_balance_lot_id", "molecule", "capacity_id"):
            assert child[col] == parent_before[col], col
    conn = me._conn()
    try:
        lp, lc = dt.lineage(conn, token), dt.lineage(conn, to_buyer["id"])
        assert lc == lp and lp["rfnbo"] == "PASS" and lp["period_status"] == "CLOSED"
        assert dt.token_kg(conn, to_buyer["id"]) + dt.token_kg(conn, rest["id"]) == dt.token_kg(conn, token)
    finally:
        conn.close()
    assert ob.get_contract(seller, d["contract_id"])["chain_intact"] is True


def test_a_second_delivery_takes_title_from_the_sellers_remainder(custody_token):
    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    first = _accepted(custody_token, (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT), kg=400)
    rest = next(k for k in _children(url, token) if k["holder_company_id"] == seller.company_id)["child_token_id"]
    from app.core import delivery_record as dr
    d = dr.schedule(seller, first["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": token, "kg": 600}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": "SHIP",
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})
    dr.dispatch(seller, d["id"], 600, NOW())
    dr.receive(buyer, d["id"], 600, NOW())
    d = _appoint(dr.request_inspection(buyer, d["id"]))
    _certify(d, GOOD)
    t = _tok(url, rest)
    assert (t["holder_company_id"], t["lifecycle_state"]) == (buyer.company_id, "SETTLED"), "the whole remainder moved"
    assert _children(url, rest) == []


def test_with_no_title_clause_title_never_passes(custody_token):
    seller, _ = _parties()
    d = _accepted(custody_token, (DELIVERY_CIF, PAYMENT), kg=100)
    assert d["status"] == "ACCEPTED" and d["title"]["transferred"] is False
    assert "no title clause" in d["title"]["waiting_for"]
    with pytest.raises(psycopg2.Error, match="DELIVERY_TITLE_NO_CLAUSE"):
        _force(d, "DELIVERY_TITLE_TRANSFERRED")


def test_on_payment_in_full_waits_for_settlement_which_is_after_step_3(custody_token):
    d = _accepted(custody_token, (DELIVERY_CIF, _title("ON_PAYMENT_IN_FULL"), PAYMENT), kg=100)
    assert d["status"] == "ACCEPTED" and d["title"]["waiting_for"].startswith("ON_PAYMENT_IN_FULL")
    with pytest.raises(psycopg2.Error, match="DELIVERY_TITLE_ON_PAYMENT_NOT_BUILT"):
        _force(d, "DELIVERY_TITLE_TRANSFERRED")


def test_on_risk_under_fob_legal_title_precedes_acceptance_and_the_token_waits_t1(custody_token):
    url, token = custody_token["url"], custody_token["token"]
    d = _appoint(_inspection(custody_token, kg=1000, clauses=(FOB, _title("ON_RISK"), PAYMENT)))
    assert d["risk"]["passed"] is True and _tok(url, token)["holder_company_id"] is None   # held until ACCEPTED
    _certify(d, GOOD)
    from app.core import delivery_record as dr
    d = dr.get_delivery(_parties()[0], d["id"])
    assert d["status"] == "TITLE_TRANSFERRED"
    assert "legal title clause precedes acceptance; token held until ACCEPTED" in d["title"]["labels"]


def test_on_document_transfer_title_waits_for_the_buyers_acknowledgement(custody_token):
    from app.core import delivery_title as dt

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    d = _accepted(custody_token, (DELIVERY_CIF, _title("ON_DOCUMENT_TRANSFER"), PAYMENT), kg=1000)
    assert d["status"] == "ACCEPTED" and _tok(url, token)["holder_company_id"] is None
    bl = _doc(seller, d, "BILL_OF_LADING")
    _refused(lambda: dt.acknowledge_documents(seller, d["id"], bl), status=403, code="DELIVERY_WRONG_PARTY")
    _refused(lambda: dt.acknowledge_documents(buyer, d["id"], "0" * 64), status=422)
    d = dt.acknowledge_documents(buyer, d["id"], bl)
    assert d["status"] == "TITLE_TRANSFERRED" and _tok(url, token)["holder_company_id"] == buyer.company_id
    assert d["title"]["labels"] == [], "acknowledged after acceptance: no T1 label"


def test_title_recorded_before_risk_is_labelled_not_refused(custody_token):
    d = _accepted(custody_token, (_title("ON_ACCEPTANCE"), PAYMENT), kg=100)       # no Incoterm: risk never passes
    assert d["status"] == "TITLE_TRANSFERRED" and d["risk"]["passed"] is False
    assert "title recorded before risk has passed" in d["title"]["labels"]


def test_a_split_parent_is_frozen_and_the_holder_changes_only_on_the_operator_connection(custody_token):
    from pg_support import connect_dsn

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    _accepted(custody_token, (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT), kg=400)
    kids = {k["holder_company_id"]: k["child_token_id"] for k in _children(url, token)}

    def as_company(company, sql, params):
        conn = connect_dsn(url)
        try:
            cur = conn.cursor()
            cur.execute("SET app.current_company_id = %s", (company,))
            cur.execute(sql, params)
            return cur.rowcount
        finally:
            conn.rollback()
            conn.close()

    with pytest.raises(psycopg2.Error, match="TOKEN_SPLIT_FROZEN"):
        as_company("PLATFORM_ADMIN", "UPDATE tokens SET lifecycle_state = 'MATCHED' WHERE id = %s", (token,))
    with pytest.raises(psycopg2.Error, match="TOKEN_HOLDER_OPERATOR_ONLY"):
        as_company(seller.company_id, "UPDATE tokens SET holder_company_id = %s WHERE id = %s",
                   (buyer.company_id, kids[seller.company_id]))
    # The capacity owner holds no write on the buyer's part any more (109's write rule).
    assert as_company(seller.company_id, "UPDATE tokens SET verification_state = 'SUBMITTED' WHERE id = %s",
                      (kids[buyer.company_id],)) == 0
    assert as_company(buyer.company_id, "UPDATE tokens SET verification_state = 'SUBMITTED' WHERE id = %s",
                      (kids[buyer.company_id],)) == 1
    with pytest.raises(psycopg2.Error, match="TOKEN_SPLIT_UNBALANCED|TOKEN_SPLIT_APPEND_ONLY"):
        conn = _superuser(url)
        try:
            conn.cursor().execute("UPDATE token_split SET kg = kg + 1 WHERE child_token_id = %s", (kids[buyer.company_id],))
        finally:
            conn.rollback()
            conn.close()


def test_the_buyer_reads_no_more_of_the_remainder_than_of_the_parent(custody_token):
    from pg_support import connect_dsn

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    _accepted(custody_token, (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT), kg=400)
    kids = {k["holder_company_id"]: k["child_token_id"] for k in _children(url, token)}
    conn = connect_dsn(url)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (buyer.company_id,))
        seen = {}
        for name, tid in (("parent", token), ("rest", kids[seller.company_id]), ("mine", kids[buyer.company_id])):
            cur.execute("SELECT count(*) AS n FROM tokens WHERE id = %s", (tid,))
            seen[name] = cur.fetchone()["n"]
    finally:
        conn.close()
    assert seen["mine"] == 1 and seen["rest"] == seen["parent"], seen


def test_title_before_acceptance_and_settlement_before_title_are_refused(custody_token):
    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=100, clauses=(DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT)))
    with pytest.raises(psycopg2.Error, match="DELIVERY_STATE_ORDER"):
        _force(d, "DELIVERY_TITLE_TRANSFERRED")                    # still QUALITY_VERIFICATION
    with pytest.raises(psycopg2.Error, match="DELIVERY_STEP_NOT_BUILT|DELIVERY_STATE_ORDER"):
        _force(d, "DELIVERY_SETTLED")
    _certify(d, GOOD)
    with pytest.raises(psycopg2.Error, match="DELIVERY_STEP_NOT_BUILT"):
        _force(d, "DELIVERY_SETTLED")                               # TITLE_TRANSFERRED: stop before SETTLED


def test_r2_a_market_settlement_moves_no_holder_on_a_contract_with_deliveries(custody_token):
    from app.core import market_engine as me

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=100, clauses=(DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT)))
    with _accounts():
        stl = me.create_settlement(buyer, d["contract_id"], settlement_type="SPOT", volume_kg=100)["settlement_id"]
        me.confirm_settlement(seller, stl, payment_reference="TEST-R2")
    t = _tok(url, token)
    assert (t["holder_company_id"], t["lifecycle_state"]) == (None, "MATCHED"), "R2: only the delivery record moves it"


def _force(d, event, company=None):
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record

    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        record.append_event(shim, d["contract_id"], event, "test", company, delivery_id=d["id"])
    finally:
        shim.rollback()
        shim.close()
