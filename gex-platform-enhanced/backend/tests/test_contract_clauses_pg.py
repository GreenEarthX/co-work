"""
Typed clauses on a real order-book trade, on PostgreSQL (Phase 2 Step 3, sub-step 1; alembic 104).

An order carrying delivery (CIF + shipment point), title and payment clauses is accepted; the
contract's frozen terms read back the three records. 104 admits the `title` clause type and the
database still refuses an unknown one. Throwaway database (pg_store).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from test_contract_clauses import DELIVERY, PAYMENT, TITLE, _terms

SELLER, BUYER = "test_cl_seller", "test_cl_buyer"


def _superuser(pg_url: str):
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


@pytest.fixture(scope="module")
def world(pg_store):
    conn = _superuser(pg_store)
    try:
        cur = conn.cursor()
        for c in (SELLER, BUYER):
            cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                        "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (c, f"TEST {c}"))
        conn.commit()
    finally:
        conn.close()
    return pg_store


def test_an_order_book_trade_carries_the_three_clauses(world):
    from app.core import market_engine as me
    from app.core import order_book as ob
    from app.trading_book import clauses, record

    seller = me.Party(business_function="COMMERCIAL", user_id="u_cl_s", company_id=SELLER)
    buyer = me.Party(business_function="COMMERCIAL", user_id="u_cl_b", company_id=BUYER)
    until = datetime.now(timezone.utc) + timedelta(days=5)
    oid = ob.create_order(seller, _terms(DELIVERY, TITLE, PAYMENT), side="sell", valid_until=until)["id"]
    ob.open_order(seller, oid)
    cid = ob.accept_order(buyer, oid)["contract_id"]
    conn = me._conn()
    try:
        v = record.current_version(conn, cid)
        c = clauses.for_terms(conn, str(v["terms_id"]), None)
    finally:
        conn.close()
    assert (c["risk"]["incoterm"], c["risk"]["shipment_point"]) == ("CIF", "Port of loading, BR")
    assert c["title"]["passes"] == "ON_ACCEPTANCE"
    assert (c["payment"]["trigger"], c["payment"]["quantity_basis"]) == ("ON_INSPECTOR_CERTIFICATE", "OUTTURN_QTY")
    b = clauses.bases(c)
    assert not any(x.startswith("MISSING") for x in b.values()), b


def test_an_invalid_typed_clause_is_refused_on_order_creation(world):
    from app.core import market_engine as me
    from app.core import order_book as ob

    seller = me.Party(business_function="COMMERCIAL", user_id="u_cl_s", company_id=SELLER)
    with pytest.raises(me.MarketRefused) as exc:
        ob.create_order(seller, _terms({"clause_type": "title", "attrs": {"passes": "ON_DELIVERY"}}), side="sell",
                        valid_until=datetime.now(timezone.utc) + timedelta(days=5))
    assert "V15" in str(exc.value)


def test_the_database_admits_title_and_still_refuses_an_unknown_clause_type(world):
    conn = _superuser(world)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conname = 'tb_clause_clause_type_check'")
        d = cur.fetchone()["d"]
        assert "'title'" in d and "'retention'" not in d
        cur.execute("SELECT id FROM tb_terms LIMIT 1")
        t = cur.fetchone()
        if t is None:
            pytest.skip("no terms row to attach a clause to")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO tb_clause (terms_id, clause_type, seq, attrs) VALUES (%s, 'retention', 999, '{}')",
                        (t["id"],))
    finally:
        conn.rollback()
        conn.close()
