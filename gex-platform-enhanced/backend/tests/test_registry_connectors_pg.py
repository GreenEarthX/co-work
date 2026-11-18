"""
Registry and scheme connectors, export only (GreenMesh Phase 2 Step 6; D5, D6; alembic 111).

Pinned (the brief's list): the payload is built ONLY from VERIFIED items; a refusal names what is
missing; the outbox is append-only; no network call happens under `none`, the only backend.
On real flows (custody token, order-book trade, inspector, title). Throwaway database (pg_store).
"""
from __future__ import annotations

import hashlib
import json
import socket

import psycopg2
import pytest

from test_contract_clauses import PAYMENT
from test_delivery_inspection_pg import (GOOD, OFF, _accounts, _appoint, _certify, _confirm, _doc,  # noqa: F401
                                         _docs_dir, _inspection, _party, inspectors)
from test_delivery_record_pg import _parties, _refused, world  # noqa: F401
from test_delivery_title_pg import _title
from test_evidence_pack_pg import _superuser, client, seeded  # noqa: F401
from test_order_book_token_pg import DELIVERY_CIF, custody_token  # noqa: F401

CLAUSES = (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT)


@pytest.fixture(autouse=True)
def _exports(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "REGISTRY_EXPORT_DIR", str(tmp_path / "exports"))


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a network call was attempted under REGISTRY_CONNECTOR_BACKEND=none")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _export(party, cid):
    """As the exporting company's own RLS connection, as the route does."""
    from app.core import registry_connectors as rc
    from app.core.db_backend import domain_connection

    conn = domain_connection(company_id=party.company_id)
    try:
        return rc.export(party, cid, conn=conn)
    finally:
        conn.close()


def _delivered(custody_token, measured=GOOD):
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))
    _certify(d, measured)
    return d


def test_a_complete_pack_exports_verified_items_only_and_sends_nothing(custody_token, no_network):
    seller, _ = _parties()
    d = _delivered(custody_token)
    out = _export(seller, d["contract_id"])
    assert (out["backend"], out["sent"]) == ("none", False)
    body = open(out["exported_path"], "rb").read()
    assert hashlib.sha256(body).hexdigest() == out["payload_sha256"]
    payload = json.loads(body)
    assert payload["format"] == "gex_export_v1" and "not a registry" in payload["format_note"]
    every = [i for items in payload["verified"].values() for i in items]
    assert every and {i["label"] for i in every} == {"VERIFIED"}, "only VERIFIED items are carried"
    assert {"declared_characteristics", "custody"} <= set(payload["not_carried"]), payload["not_carried"]
    row = _row(custody_token["url"], "SELECT * FROM registry_outbox WHERE payload_sha256 = %s", (out["payload_sha256"],))
    assert (row["backend"], row["status"], row["connector"]) == ("none", "EXPORTED", "gex_export_v1")
    assert row["pack_sha256"] == out["pack_sha256"]


def test_a_refusal_names_every_item_that_is_not_verified(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _delivered(custody_token, OFF)
    di.propose_waiver(seller, d["id"], _doc(seller, d, "WAIVER"))
    _confirm(d, "WAIVER_CONFIRMED", buyer, _party("g_buyer2", buyer.company_id))
    e = _refused(lambda: _export(seller, d["contract_id"]), status=409, code="REGISTRY_EXPORT_NOT_VERIFIED")
    assert f"delivery {d['id']}.quality: DECLARED FAIL" in e.message
    assert _row(custody_token["url"], "SELECT count(*) AS n FROM registry_outbox WHERE contract_id = %s",
                (d["contract_id"],))["n"] == 0, "a refused export writes nothing"


def test_a_delivery_without_a_certificate_blocks_the_export(custody_token):
    seller, _ = _parties()
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))
    e = _refused(lambda: _export(seller, d["contract_id"]), status=409, code="REGISTRY_EXPORT_NOT_VERIFIED")
    assert ".quality: MISSING" in e.message


def test_only_the_seller_exports(custody_token):
    from app.core import market_engine as me

    _, buyer = _parties()
    d = _delivered(custody_token)
    _refused(lambda: _export(buyer, d["contract_id"]), status=403, code="REGISTRY_EXPORT_BY_SELLER")
    _refused(lambda: _export(me.Party(business_function="COMMERCIAL", user_id="u_x", company_id="test_pack_other"), d["contract_id"]), status=404)
    _refused(lambda: _export(me.Party(business_function="COMMERCIAL", user_id="u_gex", company_id="greenearthx", is_admin=True), d["contract_id"]),
             status=403, code="GEX_DOES_NOT_TRADE")


def test_the_outbox_is_append_only(custody_token):
    seller, _ = _parties()
    d = _delivered(custody_token)
    out = _export(seller, d["contract_id"])
    for sql in ("UPDATE registry_outbox SET status = 'EXPORTED' WHERE payload_sha256 = %s",
                "DELETE FROM registry_outbox WHERE payload_sha256 = %s"):
        conn = _superuser(custody_token["url"])
        try:
            with pytest.raises(psycopg2.Error, match="REGISTRY_OUTBOX_APPEND_ONLY"):
                conn.cursor().execute(sql, (out["payload_sha256"],))
        finally:
            conn.rollback()
            conn.close()


def test_none_is_the_only_backend():
    from pydantic import ValidationError

    from app.core.config import Settings

    for value in ("certifhy", "iscc_live", "udb_production"):
        with pytest.raises(ValidationError, match="export only"):
            Settings(REGISTRY_CONNECTOR_BACKEND=value)


def _row(url, sql, params=()):
    conn = _superuser(url)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()
