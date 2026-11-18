"""
The delivery record (GreenMesh Phase 2, Step 2; alembic 103; core/delivery_record.py).

Every delivery here sits on a REAL trade: custody lot -> token allocated -> listing -> RFQ ->
proposal -> both accept -> four-eye confirmations (the Phase 1 gate's market flow, reused from
test_evidence_pack_pg). Throwaway database (pg_store), never the development store.

Pinned: the state order; who records what; over-allocation and over-nomination refused; no
dispatch into a closed custody period; acceptance, title and settlement refused until Step 3;
the row and its events cannot diverge (checked at commit); the delivery id is inside the event
hash; flows.py prices a delivered-basis payment from the buyer's receipt.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from test_evidence_pack_pg import (GBUYER, GCAP, GPROJECT, GSELLER, _gtoken, _market_flow, _su,  # noqa: F401
                                   _superuser, client, scenario, seeded)

NOW = lambda: datetime.now(timezone.utc).replace(microsecond=0)  # noqa: E731
JAN = ("2027-01-05T00:00:00+00:00", "2027-01-08T00:00:00+00:00")


def _parties():
    from app.core import market_engine as me
    from app.core import project_registry as reg

    s, b = reg.company_slug(GSELLER), reg.company_slug(GBUYER)
    return (me.Party(business_function="COMMERCIAL", user_id="g_seller", company_id=s, company_name=GSELLER),
            me.Party(business_function="COMMERCIAL", user_id="g_buyer", company_id=b, company_name=GBUYER))


def _refused(fn, *args, status=None, code=None):
    from app.core import market_engine as me

    with pytest.raises(me.MarketRefused) as exc:
        fn(*args)
    if status is not None:
        assert exc.value.status == status, exc.value
    if code is not None:
        assert exc.value.code == code, exc.value
    return exc.value


@pytest.fixture(scope="module")
def world(seeded):
    from app.core import project_registry as reg

    seller = reg.company_slug(GSELLER)
    for company in (GSELLER, GBUYER):
        _su(seeded, "INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (reg.company_slug(company), company))
    _su(seeded, "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST pack gate plant', %s, 'H2') ON CONFLICT DO NOTHING", (GPROJECT, seller))
    _su(seeded, "INSERT INTO capacities (id, project_name, molecule, capacity_mtpd, project_id) VALUES "
                "(%s, 'TEST', 'H2', 100000, %s) ON CONFLICT DO NOTHING", (GCAP, GPROJECT))   # 115: room for every scenario's 50 MTPD token
    return seeded


@pytest.fixture
def trade(world, client, monkeypatch):
    """A confirmed trade on a token with 1000 kg allocated from a closed February 2026 period."""
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GSELLER)})
    try:
        s = scenario(client, world, project=GPROJECT, capacity=GCAP, synthetic=False)
    finally:
        client.headers.pop("x-test-company", None)
    flow = _market_flow(world, s["token"], monkeypatch, rfq_mtpd=50)       # the whole token: 1000 kg
    fac = _row(world, "SELECT facility_id FROM coc_period WHERE period_id = %s", (s["period"],))["facility_id"]
    return {"contract_id": flow["contract_id"], "token": s["token"], "facility": fac, "period": s["period"],
            "url": world}


def _row(url, sql, params=()):
    conn = _superuser(url)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _body(t, *, kg=400, flow=(1, 1), window=JAN, mode="SHIP", origin=None, destination=None, draws=None):
    return {"flow": {"leg_seq": flow[0], "flow_seq": flow[1]},
            "draws": draws or [{"token_id": t["token"], "kg": kg}],
            "window_start": window[0], "window_end": window[1], "transport_mode": mode,
            "origin": origin or {"facility_id": t["facility"]}, "destination": destination or {"locode": "NLRTM"}}


def _schedule(t, **kw):
    from app.core import delivery_record as dr

    return dr.schedule(_parties()[0], t["contract_id"], _body(t, **kw))


# ── the path, on the contract chain ─────────────────────────────────────────

def test_a_delivery_runs_from_scheduled_to_inspection_on_the_contract_chain(trade):
    from app.core import delivery_record as dr
    from app.core import order_book as ob

    seller, buyer = _parties()
    d = _schedule(trade)
    assert (d["status"], d["nominated_kg"], d["seller_company_id"], d["buyer_company_id"]) == (
        "SCHEDULED", "400", seller.company_id, buyer.company_id)
    assert d["draws"] == [{"token_id": trade["token"], "kg": "400"}]
    # The market's clauses are free text: no Incoterm (so no risk basis), no title clause, no
    # typed payment clause. Three records, three bases (Step 3 amendment B1, ruling R1).
    assert d["incoterm"] is None
    assert [d[k].split(":")[0] for k in ("risk_basis", "title_basis", "payment_basis")] == ["MISSING"] * 3
    assert "Incoterm" in d["risk_basis"] and "title clause" in d["title_basis"]
    d = dr.dispatch(seller, d["id"], 400, NOW() - timedelta(hours=2))
    assert (d["status"], d["dispatched_kg"]) == ("IN_TRANSIT", "400")
    d = dr.receive(buyer, d["id"], Decimal("398.5"), NOW())
    assert (d["status"], d["delivered_kg"], d["volume_mt"]) == ("ARRIVED", "398.5", 0.3985)
    d = dr.request_inspection(buyer, d["id"], "TEST: inspector to be agreed")
    assert d["status"] == "QUALITY_VERIFICATION"
    assert [e["event_type"] for e in d["events"]] == ["DELIVERY_SCHEDULED", "DELIVERY_IN_TRANSIT",
                                                      "DELIVERY_ARRIVED", "DELIVERY_QUALITY_VERIFICATION"]
    assert [e["company_id"] for e in d["events"]] == [seller.company_id, seller.company_id,
                                                      buyer.company_id, buyer.company_id]
    record = ob.get_contract(seller, trade["contract_id"])
    assert record["chain_intact"] is True
    assert {e["event_hash"] for e in d["events"]} <= {e["event_hash"] for e in record["events"]}
    assert _row(trade["url"], "SELECT count(*) AS n FROM ledger_anchor_outbox WHERE event_hash = %s",
                (d["events"][-1]["event_hash"],))["n"] == 1, "a delivery event is anchored like any contract event"


def test_the_state_order_is_enforced(trade):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _schedule(trade, kg=100)
    _refused(dr.receive, buyer, d["id"], 100, NOW(), status=409, code="DELIVERY_STATE_ORDER")
    _refused(dr.request_inspection, buyer, d["id"], None, status=409, code="DELIVERY_STATE_ORDER")
    dr.dispatch(seller, d["id"], 100, NOW())
    _refused(dr.dispatch, seller, d["id"], 100, NOW(), status=409, code="DELIVERY_STATE_ORDER")
    d = dr.dispute(buyer, d["id"], "TEST: damaged seal")
    assert d["status"] == "DISPUTED"
    _refused(dr.receive, buyer, d["id"], 100, NOW(), status=409, code="DELIVERY_STATE_ORDER")


def test_each_act_belongs_to_one_party(trade):
    from app.core import delivery_record as dr
    from app.core import market_engine as me

    seller, buyer = _parties()
    _refused(dr.schedule, buyer, trade["contract_id"], _body(trade), status=403, code="DELIVERY_WRONG_PARTY")
    d = _schedule(trade, kg=100)
    _refused(dr.dispatch, buyer, d["id"], 100, NOW(), status=403, code="DELIVERY_WRONG_PARTY")
    dr.dispatch(seller, d["id"], 100, NOW())
    _refused(dr.receive, seller, d["id"], 100, NOW(), status=403, code="DELIVERY_WRONG_PARTY")
    gex = me.Party(business_function="COMMERCIAL", user_id="u_gex", company_id="greenearthx", is_admin=True)
    _refused(dr.receive, gex, d["id"], 100, NOW(), status=403, code="GEX_DOES_NOT_TRADE")
    stranger = me.Party(business_function="COMMERCIAL", user_id="u_x", company_id="test_pack_other")
    _refused(dr.receive, stranger, d["id"], 100, NOW(), status=404)
    _refused(dr.get_delivery, stranger, d["id"], status=404)           # 103's RLS: not a party, no access
    assert dr.get_delivery(gex, d["id"])["status"] == "IN_TRANSIT"     # GEX reads state


def test_no_delivery_beyond_what_custody_allocated_to_the_tokens(trade):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    _refused(lambda: _schedule(trade, kg=1000.5), status=409, code="DELIVERY_OVER_ALLOCATION")
    d = _schedule(trade, kg=700)
    _refused(lambda: _schedule(trade, kg=301), status=409, code="DELIVERY_OVER_ALLOCATION")    # 700 + 301 > 1000
    assert _schedule(trade, kg=300)["nominated_kg"] == "300"                       # exactly the rest
    _refused(dr.dispatch, seller, d["id"], 700.001, NOW(), status=409, code="DELIVERY_OVER_NOMINATION")
    dr.dispatch(seller, d["id"], 700, NOW())
    _refused(dr.receive, buyer, d["id"], 701, NOW(), status=409, code="DELIVERY_OVER_NOMINATION")
    other = f"TKN-NOT-ON-CONTRACT-{uuid.uuid4().hex[:6]}"
    _su(trade["url"], "INSERT INTO tokens (id, capacity_id, molecule, lifecycle_state) VALUES "
                      "(%s, %s, 'H2', 'MINTED')", (other, GCAP))
    _refused(lambda: _schedule(trade, draws=[{"token_id": other, "kg": 1}]), status=422,
             code="DELIVERY_TOKEN_NOT_ON_CONTRACT")


def test_the_database_refuses_an_over_draw_even_from_the_operator(trade):
    """103's draw trigger, below the application: a token's draws never exceed its allocation."""
    import psycopg2

    from pg_support import connect_dsn

    d = _schedule(trade, kg=1000)
    conn = connect_dsn(trade["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        raw = f"DLV-RAW-{uuid.uuid4().hex[:8]}"           # a second delivery, written past the application
        cur.execute("INSERT INTO deliveries (id, project_id, contract_id, flow_id, terms_hash, seller_company_id, "
                    "buyer_company_id, molecule, status, window_start, window_end, nominated_kg, transport_mode, "
                    "origin_facility_id, destination_locode, created_by) SELECT %s, project_id, contract_id, flow_id, "
                    "terms_hash, seller_company_id, buyer_company_id, molecule, 'SCHEDULED', window_start, window_end, "
                    "1, transport_mode, origin_facility_id, destination_locode, 'raw' FROM deliveries WHERE id = %s",
                    (raw, d["id"]))
        with pytest.raises(psycopg2.Error, match="DELIVERY_OVER_ALLOCATION"):
            cur.execute("INSERT INTO delivery_draw (delivery_id, token_id, kg) VALUES (%s, %s, 1)",
                        (raw, trade["token"]))
    finally:
        conn.rollback()
        conn.close()


def test_nothing_is_dispatched_into_a_closed_custody_period(trade):
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _schedule(trade, kg=50)
    e = _refused(dr.dispatch, seller, d["id"], 50, "2026-02-15T08:00:00+00:00", status=409, code="COC_PERIOD_CLOSED")
    assert trade["period"] in e.message
    assert dr.dispatch(seller, d["id"], 50, NOW())["status"] == "IN_TRANSIT"


def test_no_party_accepts_and_title_and_settlement_still_wait(trade):
    """Since 107 ACCEPTED is built, but DERIVED: no party records it (application and trigger),
    and none follows without a certificate. TITLE_TRANSFERRED (109) never precedes ACCEPTED, and
    SETTLED stays refused by both (stop before SETTLED). (Step 2 pinned all four as not built.)"""
    import psycopg2

    from app.core import delivery_record as dr
    from app.trading_book import record
    from pg_support import connect_dsn

    seller, buyer = _parties()
    d = _schedule(trade, kg=10)
    dr.dispatch(seller, d["id"], 10, NOW())
    dr.receive(buyer, d["id"], 10, NOW())
    dr.request_inspection(seller, d["id"])
    conn = connect_dsn(trade["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SELECT * FROM deliveries WHERE id = %s", (d["id"],))
        row = dict(cur.fetchone())
    finally:
        conn.close()
    _refused(dr._transition, None, row, "ACCEPTED", buyer.company_id, "g_buyer", {}, status=403,
             code="DELIVERY_WRONG_PARTY")
    _refused(dr._transition, None, row, "SETTLED", buyer.company_id, "g_buyer", {}, status=409,
             code="DELIVERY_STEP_NOT_BUILT")
    _refused(dr._transition, None, row, "TITLE_TRANSFERRED", None, "system:title", {}, status=409,
             code="DELIVERY_STATE_ORDER")             # built since 109, but never before ACCEPTED
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    for event, company, refusal in (("DELIVERY_ACCEPTED", buyer.company_id, "DELIVERY_ACCEPTANCE_DERIVED"),
                                    ("DELIVERY_ACCEPTED", None, "DELIVERY_NOT_ACCEPTABLE"),
                                    ("DELIVERY_REJECTED", buyer.company_id, "DELIVERY_NOT_REJECTABLE"),
                                    ("DELIVERY_TITLE_TRANSFERRED", None, "DELIVERY_STATE_ORDER")):
        shim = market_connection(company_id=PLATFORM_ADMIN)
        try:
            with pytest.raises(psycopg2.Error, match=refusal):
                record.append_event(shim, trade["contract_id"], event, "test", company, delivery_id=d["id"])
        finally:
            shim.rollback()
            shim.close()


def test_the_row_and_its_events_cannot_diverge(trade):
    """Checked at COMMIT from both sides: a row moved without its event, or an event without
    the row, is refused; a recorded fact never changes; nothing is deleted."""
    import psycopg2

    from app.trading_book import record
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from pg_support import connect_dsn

    seller, _ = _parties()
    d = _schedule(trade, kg=10)

    def as_operator(sql, params, match):
        conn = connect_dsn(trade["url"])
        try:
            cur = conn.cursor()
            cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
            with pytest.raises(psycopg2.Error, match=match):
                cur.execute(sql, params)
                conn.commit()
        finally:
            conn.rollback()
            conn.close()

    as_operator("UPDATE deliveries SET status = 'IN_TRANSIT', dispatched_kg = 10, dispatched_at = now() "
                "WHERE id = %s", (d["id"],), "DELIVERY_STATE_MISMATCH")
    as_operator("UPDATE deliveries SET nominated_kg = 5 WHERE id = %s", (d["id"],), "DELIVERY_FIXED")
    as_operator("DELETE FROM deliveries WHERE id = %s", (d["id"],), "permission denied")
    as_operator("DELETE FROM delivery_draw WHERE delivery_id = %s", (d["id"],), "permission denied")
    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        record.append_event(shim, trade["contract_id"], "DELIVERY_IN_TRANSIT", "g_seller", seller.company_id,
                            delivery_id=d["id"])                     # the event alone, the row left behind
        with pytest.raises(psycopg2.Error, match="DELIVERY_STATE_MISMATCH"):
            shim.commit()
    finally:
        shim.rollback()
        shim.close()
    assert _row(trade["url"], "SELECT status FROM deliveries WHERE id = %s", (d["id"],))["status"] == "SCHEDULED"


def test_the_delivery_id_is_inside_the_event_hash(trade):
    from app.trading_book import record
    from app.core.db_backend import PLATFORM_ADMIN, market_connection

    d = _schedule(trade, kg=10)
    other = _schedule(trade, kg=10)
    conn = _superuser(trade["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET session_replication_role = replica")        # tamper below the append-only trigger
        cur.execute("UPDATE tb_contract_event SET delivery_id = %s WHERE event_hash = %s",
                    (other["id"], d["events"][0]["event_hash"]))
        shim = market_connection(company_id=PLATFORM_ADMIN)
        try:
            # The tampered row is visible only inside this transaction; recompute from it.
            cur.execute("SELECT contract_ref FROM tb_contract WHERE id = %s", (trade["contract_id"],))
            ref = cur.fetchone()["contract_ref"]
            cur.execute("SELECT e.*, v.version, s.seq AS sub_leg_seq FROM tb_contract_event e LEFT JOIN "
                        "tb_contract_version v ON v.id = e.version_id LEFT JOIN tb_sub_leg s ON s.id = e.sub_leg_id "
                        "WHERE e.contract_id = %s ORDER BY e.seq", (trade["contract_id"],))
            evs = [dict(r) for r in cur.fetchall()]
            assert record.chain_intact_events(ref, evs) is False
            assert record.chain_intact(shim, trade["contract_id"]) is True    # the committed chain holds
        finally:
            shim.close()
    finally:
        conn.rollback()
        conn.close()


def test_a_delivered_basis_payment_is_priced_from_the_buyers_receipt(trade):
    from app.core import delivery_record as dr
    from app.core import order_book as ob

    seller, buyer = _parties()

    def payment():
        lines = ob.contract_cashflows(seller, trade["contract_id"])["lines"]
        return next(ln for ln in lines if (ln["leg_seq"], ln["flow_seq"]) == (2, 1))

    before = payment()
    assert before["status"] == "projected"
    d = _schedule(trade, kg=400)
    dr.dispatch(seller, d["id"], 400, NOW())
    assert payment()["status"] == "projected", "a dispatch is not a receipt"
    dr.receive(buyer, d["id"], 400, NOW())
    after = payment()
    assert Decimal(after["quantity"]) == Decimal("0.4")              # tonnes, from 400 kg received
    assert Decimal(after["amount"]) == (Decimal("0.4") * Decimal(after["price"])).quantize(Decimal("0.01"))
    assert after["status"] != "projected"


def test_the_route_records_and_reads_a_delivery(trade, monkeypatch):
    """Through /api/v1/trading-book with the ABAC middleware and real tokens."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import routes_order_book
    from app.core import abac_middleware as mw
    from app.core import project_registry as reg
    from app.core.abac_middleware import ABACMiddleware
    from app.core.config import settings

    profile = reg.ProjectAccessProfile(project_id=GPROJECT, project_name="TEST pack gate plant",
                                       owner_company_name=GSELLER, associated_company_names=(), jurisdiction="DE")
    look = lambda pid: profile if reg.normalize_project_id(pid) == GPROJECT else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", look)
    monkeypatch.setattr(reg, "get_project_profile", look)
    api = FastAPI()
    api.include_router(routes_order_book.router, prefix="/api/v1/trading-book")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    tc = TestClient(api)
    h = lambda uid: {"Authorization": f"Bearer {_gtoken(uid)}"}  # noqa: E731
    base = "/api/v1/trading-book"
    r = tc.post(f"{base}/records/{trade['contract_id']}/deliveries", headers=h("g_seller"), json=_body(trade, kg=20))
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = tc.post(f"{base}/deliveries/{did}/receipt", headers=h("g_seller"),
                json={"delivered_kg": 20, "arrived_at": NOW().isoformat()})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DELIVERY_STATE_ORDER", r.text
    r = tc.post(f"{base}/deliveries/{did}/dispatch", headers=h("g_seller"),
                json={"dispatched_kg": 20, "dispatched_at": NOW().isoformat()})
    assert r.status_code == 200, r.text
    r = tc.post(f"{base}/deliveries/{did}/receipt", headers=h("g_buyer"),
                json={"delivered_kg": 20, "arrived_at": NOW().isoformat()})
    assert r.status_code == 200 and r.json()["status"] == "ARRIVED", r.text
    listed = tc.get(f"{base}/records/{trade['contract_id']}/deliveries", headers=h("g_buyer")).json()["deliveries"]
    assert did in {x["id"] for x in listed}


def test_the_incoterm_is_read_from_the_confirmed_terms_only():
    """A typed `delivery` clause naming both `incoterm` and `named_place` (risk only, R1); the
    flow's sub-leg's own clause first; free text is not an Incoterm."""
    from app.core import delivery_record as dr

    class Conn:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, params):
            rows = self.rows

            class R:
                def fetchall(self):
                    return rows
            return R()

    shared = {"sub_leg_id": None, "clause_type": "delivery", "attrs": {"incoterm": "FOB", "named_place": "Pecém, BR"}}
    own = {"sub_leg_id": "s2", "clause_type": "delivery", "attrs": {"incoterm": "DAP", "named_place": "Rotterdam, NL"}}
    text = {"sub_leg_id": None, "clause_type": "delivery", "attrs": {"delivery_terms": "FOB Rotterdam"}}
    assert dr.incoterm_of(Conn([own, shared]), "t", "s2") == ("DAP", "Rotterdam, NL")
    assert dr.incoterm_of(Conn([own, shared]), "t", "s1") == ("FOB", "Pecém, BR")
    assert dr.incoterm_of(Conn([text]), "t", None) == (None, None)
    assert dr.incoterm_of(Conn([{"sub_leg_id": None, "clause_type": "delivery", "attrs": {"incoterm": "FOB"}}]), "t", None) == (None, None)
    assert dr.incoterm_of(Conn([{"sub_leg_id": None, "clause_type": "delivery", "attrs": {"incoterm": "XYZ", "named_place": "x"}}]),
                          "t", None) == (None, None)


@pytest.fixture
def carved_trade(world, client, monkeypatch):
    """A confirmed trade for 40 of the token's 50 MTPD (alembic 114): the contract carries a carved
    child holding 40/50 of the lot's 1000 kg, and no allocation of its own."""
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GSELLER)})
    try:
        s = scenario(client, world, project=GPROJECT, capacity=GCAP, synthetic=False)
    finally:
        client.headers.pop("x-test-company", None)
    flow = _market_flow(world, s["token"], monkeypatch, rfq_mtpd=40)
    fac = _row(world, "SELECT facility_id FROM coc_period WHERE period_id = %s", (s["period"],))["facility_id"]
    assert flow["token_id"] != s["token"]
    return {"contract_id": flow["contract_id"], "token": flow["token_id"], "root": s["token"], "facility": fac,
            "period": s["period"], "url": world}


def test_a_carved_token_delivers_exactly_its_share_and_keeps_its_custody_rules(carved_trade):
    """Before 114's change the draw limit counted only allocations made to the token itself, which a
    carved child never has: the sold part of a custody token could not be delivered at all. And the
    closed-period check, matching allocations by token, never saw the child's period."""
    from app.core import delivery_record as dr

    seller, _ = _parties()
    t = carved_trade
    assert _row(t["url"], "SELECT app_token_kg(%s) AS kg", (t["token"],))["kg"] == 800
    _refused(lambda: _schedule(t, kg=800.5), status=409, code="DELIVERY_OVER_ALLOCATION")
    d = _schedule(t, kg=800)
    assert d["nominated_kg"] == "800"
    e = _refused(dr.dispatch, seller, d["id"], 800, "2026-02-15T08:00:00+00:00", status=409, code="COC_PERIOD_CLOSED")
    assert t["period"] in e.message
