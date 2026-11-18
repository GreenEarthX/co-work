"""
Risk passes by the Incoterm (GreenMesh Phase 2 Step 3, sub-step 2; alembic 106).

Each case is a REAL confirmed order-book trade (G-25) on a custody-backed token, with its
delivery clause chosen per test. Risk is derived, never a party's act: the delivery record
writes DELIVERY_FACT_RISK_PASSED with the act that passes it, and 106's trigger refuses it
anywhere else. A fact never moves the state. Throwaway database (pg_store).
"""
from __future__ import annotations

import os

import psycopg2
import pytest

from test_contract_clauses import PAYMENT, TITLE
from test_delivery_record_pg import JAN, NOW, _parties, _refused, world  # noqa: F401
from test_delivery_record_pg import _row as _row_su
from test_evidence_pack_pg import client, seeded  # noqa: F401
from test_order_book_token_pg import confirmed_order_book_trade, custody_token  # noqa: F401


def _clause(incoterm, place="Rotterdam, NL", shipment_point=None):
    attrs = {"incoterm": incoterm, "named_place": place}
    if shipment_point:
        attrs["shipment_point"] = shipment_point
    return {"clause_type": "delivery", "attrs": attrs}


def _delivery(custody_token, delivery_clause, mode="SHIP", kg=100):
    from app.core import delivery_record as dr

    clauses = (TITLE, PAYMENT) if delivery_clause is None else (delivery_clause, TITLE, PAYMENT)
    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"], clauses=clauses)
    seller, _ = _parties()
    return dr.schedule(seller, t["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": custody_token["token"], "kg": kg}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": mode,
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})


def _types(d):
    return [e["event_type"] for e in d["events"]]


def _force_fact(contract_id, delivery_id, fact, company=None):
    """Write a fact past the application, on the operator connection: 106's trigger decides."""
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record

    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        record.append_event(shim, contract_id, f"DELIVERY_FACT_{fact}", "test", company, delivery_id=delivery_id)
        shim.commit()
    finally:
        shim.rollback()
        shim.close()


def test_under_cif_with_a_shipment_point_risk_passes_at_dispatch(custody_token):
    from app.core import delivery_record as dr
    from app.core import order_book as ob

    seller, buyer = _parties()
    d = _delivery(custody_token, _clause("CIF", shipment_point="Port of loading, BR"))
    assert d["risk"]["passed"] is False
    d = dr.dispatch(seller, d["id"], 100, NOW())
    assert _types(d)[-2:] == ["DELIVERY_IN_TRANSIT", "DELIVERY_FACT_RISK_PASSED"]
    risk = d["events"][-1]
    assert (risk["company_id"], risk["actor"]) == (None, "system:incoterm"), "derived, no party act"
    assert d["status"] == "IN_TRANSIT", "a fact does not move the state"
    assert d["risk"]["passed"] is True and d["risk"]["at_state"] == "IN_TRANSIT"
    assert "Port of loading, BR" in d["risk"]["note"]
    assert dr.receive(buyer, d["id"], 100, NOW())["status"] == "ARRIVED"      # the state machine goes on
    assert ob.get_contract(seller, d["contract_id"])["chain_intact"] is True


def test_a_c_term_without_its_shipment_point_never_passes_risk(custody_token):
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _delivery(custody_token, _clause("CFR"))
    assert "shipment point" in d["risk_basis"]
    d = dr.dispatch(seller, d["id"], 100, NOW())
    assert "DELIVERY_FACT_RISK_PASSED" not in _types(d) and d["risk"]["passed"] is False
    with pytest.raises(psycopg2.Error, match="DELIVERY_RISK_NO_SHIPMENT_POINT"):
        _force_fact(d["contract_id"], d["id"], "RISK_PASSED")


def test_under_dap_risk_passes_on_arrival_not_at_dispatch(custody_token):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _delivery(custody_token, _clause("DAP"), mode="TRUCK")
    d = dr.dispatch(seller, d["id"], 100, NOW())
    assert d["risk"]["passed"] is False
    with pytest.raises(psycopg2.Error, match="DELIVERY_RISK_ORDER"):
        _force_fact(d["contract_id"], d["id"], "RISK_PASSED")             # not at dispatch under DAP
    d = dr.receive(buyer, d["id"], 100, NOW())
    assert d["risk"]["passed"] is True and d["risk"]["at_state"] == "ARRIVED"


def test_under_dpu_risk_waits_for_the_buyers_unloading_record(custody_token, tmp_path, monkeypatch):
    from app.core import delivery_documents as docs
    from app.core import delivery_record as dr

    monkeypatch.setenv("GEX_DELIVERY_DOCS_DIR", str(tmp_path))
    seller, buyer = _parties()
    d = _delivery(custody_token, _clause("DPU"), mode="TRUCK")
    dr.dispatch(seller, d["id"], 100, NOW())
    d = dr.receive(buyer, d["id"], 100, NOW())
    assert d["risk"]["passed"] is False, "arrival alone does not pass risk under DPU"
    _refused(lambda: dr.record_unloading(buyer, d["id"], "0" * 64, NOW()), status=422,
             code="DELIVERY_DOCUMENT_NOT_ON_FILE")
    _refused(lambda: docs.file_document(seller, d["id"], "UNLOADING_RECORD", "u.pdf", b"x"), status=403,
             code="DELIVERY_WRONG_PARTY")
    doc = docs.file_document(buyer, d["id"], "UNLOADING_RECORD", "unloading.pdf", b"TEST unloading record")
    _refused(lambda: dr.record_unloading(seller, d["id"], doc["sha256"], NOW()), status=403,
             code="DELIVERY_WRONG_PARTY")
    d = dr.record_unloading(buyer, d["id"], doc["sha256"], NOW())
    assert _types(d)[-2:] == ["DELIVERY_FACT_UNLOADED", "DELIVERY_FACT_RISK_PASSED"]
    assert d["risk"]["passed"] is True and d["status"] == "ARRIVED"
    _refused(lambda: dr.record_unloading(buyer, d["id"], doc["sha256"], NOW()), status=409)   # once


def test_with_no_incoterm_risk_never_passes(custody_token):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _delivery(custody_token, None)
    assert d["risk_basis"].startswith("MISSING")
    dr.dispatch(seller, d["id"], 100, NOW())
    d = dr.receive(buyer, d["id"], 100, NOW())
    assert d["risk"]["passed"] is False
    with pytest.raises(psycopg2.Error, match="DELIVERY_RISK_NO_INCOTERM"):
        _force_fact(d["contract_id"], d["id"], "RISK_PASSED")


def test_risk_is_derived_once_and_never_a_partys_act(custody_token):
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _delivery(custody_token, _clause("FOB", place="Port of loading, BR"))
    with pytest.raises(psycopg2.Error, match="DELIVERY_RISK_ORDER"):
        _force_fact(d["contract_id"], d["id"], "RISK_PASSED")             # FOB, still SCHEDULED
    d = dr.dispatch(seller, d["id"], 100, NOW())
    with pytest.raises(psycopg2.Error, match="DELIVERY_FACT_ONCE"):
        _force_fact(d["contract_id"], d["id"], "RISK_PASSED")


def test_a_party_cannot_record_risk_itself(custody_token):
    seller, _ = _parties()
    other = _delivery(custody_token, _clause("FOB", place="Port of loading, BR"))
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record

    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        record.append_event(shim, other["contract_id"], "DELIVERY_IN_TRANSIT", "g_seller", seller.company_id,
                            delivery_id=other["id"])
        with pytest.raises(psycopg2.Error, match="DELIVERY_RISK_DERIVED"):
            record.append_event(shim, other["contract_id"], "DELIVERY_FACT_RISK_PASSED", "g_seller",
                                seller.company_id, delivery_id=other["id"])
    finally:
        shim.rollback()
        shim.close()


def test_documents_on_file_are_hashed_by_gex_and_append_only(custody_token, tmp_path, monkeypatch):
    from app.core import delivery_documents as docs

    monkeypatch.setenv("GEX_DELIVERY_DOCS_DIR", str(tmp_path))
    _, buyer = _parties()
    d = _delivery(custody_token, _clause("DPU"), mode="TRUCK")
    a = docs.file_document(buyer, d["id"], "UNLOADING_RECORD", "../../etc/u.pdf", b"TEST bytes")
    import hashlib

    assert a["sha256"] == hashlib.sha256(b"TEST bytes").hexdigest() and a["filename"] == "u.pdf"
    assert docs.file_document(buyer, d["id"], "UNLOADING_RECORD", "again.pdf", b"TEST bytes")["id"] == a["id"]
    from test_evidence_pack_pg import _superuser

    for sql in ("UPDATE delivery_document SET filename = 'x' WHERE id = %s", "DELETE FROM delivery_document WHERE id = %s"):
        conn = _superuser(custody_token["url"])
        try:
            with pytest.raises(psycopg2.Error, match="DELIVERY_APPEND_ONLY"):
                conn.cursor().execute(sql, (a["id"],))
        finally:
            conn.rollback()
            conn.close()
    assert _row_su(custody_token["url"], "SELECT count(*) AS n FROM delivery_document WHERE delivery_id = %s",
                   (d["id"],))["n"] == 1
    assert os.path.exists(next(iter(tmp_path.rglob("*u.pdf"))))
