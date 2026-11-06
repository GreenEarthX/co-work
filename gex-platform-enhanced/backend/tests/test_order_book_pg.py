"""
The order book on the one contract model, on PostgreSQL (Phase 1, M3; 2026-11-06).

Through the REAL ABAC middleware and routes, in the throwaway database
(conftest.pg_store). Asserted: an order is one-sided until accepted; acceptance
is one locked transaction that makes exactly one fill and one draft contract
(T14), refuses a restricted pair in either direction (T09) and a partial fill
of an all-or-nothing order (T11); a quote is the quoting party's acceptance
(Q6); each party confirms with four eyes inside its own company (Q7); GEX reads
state and hashes, never terms (Q5); the event chain holds and is append-only for
every role; the legacy JTI routes survive record rows; M2 converts and is
idempotent; a producer can declare a capacity of its own project (alembic 084).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings

SELLER, BUYER, OTHER, BANNED = "test_ob_seller", "test_ob_buyer", "test_ob_bystander", "test_ob_banned"
PID = "proj_TEST_order_book"
USERS = {   # user -> (company, business function, platform admin)
    "u_ob_s1": (SELLER, "EXECUTIVE", False), "u_ob_s2": (SELLER, "COMMERCIAL", False),
    "u_ob_b1": (BUYER, "EXECUTIVE", False), "u_ob_b2": (BUYER, "COMMERCIAL", False),
    "u_ob_b3": (BUYER, "COMMERCIAL", False), "u_ob_o1": (OTHER, "EXECUTIVE", False),
    "u_ob_x1": (BANNED, "EXECUTIVE", False), "u_ob_gex": ("greenearthx", "EXECUTIVE", True),
}
DSN: dict = {}
STATE: dict = {}


def _q(sql: str, params: tuple = (), many: bool = False):
    from pg_support import connect_dsn

    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute(sql, params)
        conn.commit()
        if not cur.description:
            return None
        return cur.fetchall() if many else cur.fetchone()
    finally:
        conn.close()


def _auth(uid: str) -> dict:
    company, function, admin = USERS[uid]
    token = create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": company, "company_name": f"TEST {company}",
        "company_type": "PRODUCER", "service_type": None, "business_function": function,
        "user_name": f"TEST {uid}", "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": admin})[0]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session

    DSN["url"] = pg_store
    for company in (SELLER, BUYER, OTHER, BANNED):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,'PRODUCER','DE') "
           "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    for uid, (company, function, admin) in USERS.items():
        if not admin:
            _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
               "business_function, user_name, account_state, is_active) VALUES (%s,%s,'x',%s,%s,'PRODUCER',%s,%s,"
               "'ACTIVE',1) ON CONFLICT DO NOTHING",
               (uid, f"{uid}@test.invalid", company, f"TEST {company}", function, f"TEST {uid}"))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,'TEST order-book plant',"
       "%s,'e-Methanol') ON CONFLICT DO NOTHING", (PID, SELLER))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    from app.api.v1 import capacity_sqlite, routes_approvals, routes_order_book
    from app.trading_book.api import router as tb_router

    profile = reg.ProjectAccessProfile(project_id=PID, project_name="TEST order-book plant",
                                       owner_company_name=SELLER, associated_company_names=(),
                                       jurisdiction="DE")              # company_slug(SELLER) == SELLER
    lookup = lambda pid: profile if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", lookup)
    monkeypatch.setattr(reg, "get_project_profile", lookup)
    api = FastAPI()
    api.include_router(routes_order_book.router, prefix="/api/v1/trading-book")
    api.include_router(routes_approvals.router, prefix="/api/v1/approvals")
    api.include_router(capacity_sqlite.router, prefix="/api/v1/capacities")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api)


def _code(r):
    return r.json()["detail"]["code"]


def _flow(seq, start, end, kind, qty, price=None):
    f = {"seq": seq, "flow_type": kind, "period_start": start, "period_end": end, "settle_date": end,
         "quantity": qty, "unit": "t"}
    if kind == "fixed_cash":
        f.update(unit_price=price, quantity_basis="delivered", quantity_source_flow=f"1.{seq}")
    return f


def _terms(qty="100", price="900"):
    months = (("2027-01-01", "2027-01-31"), ("2027-02-01", "2027-02-28"))
    return {"settlement": "physical", "commodity": "EMEOH", "currency": "EUR",
            "quality_spec": {"certification": "RFNBO"},
            "legs": [{"seq": 1, "leg_role": "product",
                      "flows": [_flow(i, a, b, "physical", qty) for i, (a, b) in enumerate(months, 1)]},
                     {"seq": 2, "leg_role": "payment",
                      "flows": [_flow(i, a, b, "fixed_cash", qty, price) for i, (a, b) in enumerate(months, 1)]}],
            "clauses": [{"seq": 1, "clause_type": "delivery", "attrs": {"text": "TEST FOB Hamburg"}}]}


def _order(client, uid="u_ob_s1", side="sell", aon=False, open_it=True, **extra):
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = client.post("/api/v1/trading-book/orders", headers=_auth(uid),
                    json={"terms": _terms(), "side": side, "all_or_nothing": aon, "valid_until": until, **extra})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    if open_it:
        assert client.post(f"/api/v1/trading-book/orders/{oid}/open", headers=_auth(uid)).status_code == 200
    return oid


# ── orders ──────────────────────────────────────────────────────────────────

def test_terms_validate_without_writing(client):
    r = client.post("/api/v1/trading-book/terms/validate", headers=_auth("u_ob_o1"),
                    json={"terms": _terms(), "kind": "order"})
    assert r.json() == {"valid": True, "failed_rules": []}
    bad = _terms()
    bad["legs"][0]["payer"] = "00000000-0000-4000-8000-000000000001"           # an order names no party
    assert "V06" in client.post("/api/v1/trading-book/terms/validate", headers=_auth("u_ob_o1"),
                                json={"terms": bad, "kind": "order"}).json()["failed_rules"]


def test_an_order_is_one_sided_and_gex_does_not_trade(client):
    assert _code(client.post("/api/v1/trading-book/orders", headers=_auth("u_ob_gex"), json={
        "terms": _terms(), "side": "sell", "valid_until": "2030-01-01T00:00:00Z"})) == "GEX_DOES_NOT_TRADE"
    oid = _order(client, open_it=False)
    assert _code(client.post(f"/api/v1/trading-book/orders/{oid}/accept", headers=_auth("u_ob_b1"))) == "ORDER_STATE"
    assert client.post(f"/api/v1/trading-book/orders/{oid}/open", headers=_auth("u_ob_b1")).status_code == 404
    assert client.post(f"/api/v1/trading-book/orders/{oid}/open", headers=_auth("u_ob_s1")).json()["status"] == "open"
    seen = {o["id"]: o for o in client.get("/api/v1/trading-book/orders", headers=_auth("u_ob_b1")).json()["orders"]}
    assert seen[oid]["mine"] is False and "owner_company_id" not in seen[oid]          # anonymised
    STATE["open_order"] = oid


def test_acceptance_makes_one_fill_and_one_draft_contract_with_parties_resolved(client):
    oid = STATE["open_order"]
    assert _code(client.post(f"/api/v1/trading-book/orders/{oid}/accept", headers=_auth("u_ob_s2"))) == "SELF_TRADE"
    r = client.post(f"/api/v1/trading-book/orders/{oid}/accept", headers=_auth("u_ob_b1"), json={"quantity": "50"})
    assert r.status_code == 201, r.text
    cid = r.json()["contract_id"]
    rec = client.get(f"/api/v1/trading-book/records/{cid}", headers=_auth("u_ob_b1")).json()
    assert (rec["trade_status"], rec["verification_state"], rec["kind"]) == ("pending_confirmation", "UNVERIFIED", "trade")
    assert rec["chain_intact"] and rec["terms_hold"] and rec["parties"] == {"seller": SELLER, "buyers": [BUYER]}
    legs = {leg["leg_role"]: leg for leg in rec["terms"]["legs"]}
    seller_cp = _q("SELECT id FROM tb_counterparty WHERE company_id = %s", (SELLER,))["id"]
    assert legs["product"]["payer"] == f"cp:{seller_cp}"                        # T07: the seller delivers
    assert legs["payment"]["receiver"] == f"cp:{seller_cp}"
    # 50 of the order's 200 t (2 months x 100 t): each month scaled to a quarter.
    assert [f["quantity"] for f in legs["product"]["flows"]] == ["25.000000", "25.000000"]
    assert rec["terms"]["clauses"][0]["attrs"] == {"text": "TEST FOB Hamburg"}
    assert _q("SELECT status FROM tb_order WHERE id = %s", (oid,))["status"] == "partially_filled"
    fill = _q("SELECT * FROM tb_fill WHERE contract_id = %s", (cid,))
    assert str(fill["sell_order_id"]) == oid and fill["quantity"] == 50
    STATE["contract"] = cid


def test_t11_all_or_nothing_refuses_a_partial_fill(client):
    oid = _order(client, aon=True)
    assert _code(client.post(f"/api/v1/trading-book/orders/{oid}/accept", headers=_auth("u_ob_b1"),
                             json={"quantity": "10"})) == "ALL_OR_NOTHING"
    assert _q("SELECT count(*) AS n FROM tb_fill WHERE sell_order_id = %s", (oid,))["n"] == 0


def test_t09_a_restricted_pair_cannot_trade_in_either_direction(client):
    from pg_support import connect_dsn

    sell = _order(client)
    buy = _order(client, uid="u_ob_x1", side="buy")
    conn = connect_dsn(DSN["url"])
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    cur.execute("INSERT INTO tb_counterparty_restriction (counterparty_id, restricted_counterparty_id, reason, set_by) "
                "SELECT s.id, x.id, 'TEST sanctions screen', 'u_test' FROM tb_counterparty s, tb_counterparty x "
                "WHERE s.company_id = %s AND x.company_id = %s", (SELLER, BANNED))
    conn.commit()
    conn.close()
    assert _code(client.post(f"/api/v1/trading-book/orders/{sell}/accept", headers=_auth("u_ob_x1"))) == "RESTRICTED_COUNTERPARTY"
    assert _code(client.post(f"/api/v1/trading-book/orders/{buy}/accept", headers=_auth("u_ob_s1"))) == "RESTRICTED_COUNTERPARTY"


def test_t14_two_simultaneous_accepts_make_exactly_one_fill(client):
    oid = _order(client, aon=True)
    results, barrier = [], threading.Barrier(2)

    def go(uid):
        barrier.wait()
        results.append(client.post(f"/api/v1/trading-book/orders/{oid}/accept", headers=_auth(uid)).status_code)

    threads = [threading.Thread(target=go, args=(u,)) for u in ("u_ob_b1", "u_ob_o1")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 409], results
    assert _q("SELECT count(*) AS n FROM tb_fill WHERE sell_order_id = %s", (oid,))["n"] == 1


# ── RFQs and quotes (Q6) ────────────────────────────────────────────────────

def test_a_quote_is_the_quoting_partys_acceptance_and_only_the_requester_completes_it(client):
    until = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    rfq = client.post("/api/v1/trading-book/rfqs", headers=_auth("u_ob_b1"),
                      json={"terms": _terms(), "side": "buy", "valid_until": until}).json()["id"]
    assert client.post(f"/api/v1/trading-book/rfqs/{rfq}/publish", headers=_auth("u_ob_b1")).json()["status"] == "published"
    q1 = client.post(f"/api/v1/trading-book/rfqs/{rfq}/quotes", headers=_auth("u_ob_s1"),
                     json={"terms": _terms(price="905"), "valid_until": until}).json()
    q2 = client.post(f"/api/v1/trading-book/rfqs/{rfq}/quotes", headers=_auth("u_ob_o1"),
                     json={"terms": _terms(price="899"), "valid_until": until}).json()
    assert (q1["status"], q1["side"], q1["visibility"]) == ("open", "sell", "invited")
    assert _q("SELECT reason FROM tb_order_event WHERE order_id = %s", (q1["id"],))["reason"].endswith("acceptance")
    assert client.post(f"/api/v1/trading-book/orders/{q1['id']}/accept", headers=_auth("u_ob_o1")).status_code == 404
    assert client.post(f"/api/v1/trading-book/rfqs/{rfq}/quotes/{q1['id']}/accept",
                       headers=_auth("u_ob_s1")).status_code == 404                   # not the requester
    r = client.post(f"/api/v1/trading-book/rfqs/{rfq}/quotes/{q1['id']}/accept", headers=_auth("u_ob_b1"))
    assert r.status_code == 201, r.text
    assert _q("SELECT status FROM tb_rfq WHERE id = %s", (rfq,))["status"] == "closed"
    assert _q("SELECT status FROM tb_order WHERE id = %s", (q2["id"],))["status"] == "cancelled"


# ── TRADE_CONFIRM (Q7) and what GEX reads (Q5) ──────────────────────────────

def test_four_eyes_inside_each_party(client):
    cid = STATE["contract"]
    base = f"/api/v1/trading-book/records/{cid}"
    assert client.get(base, headers=_auth("u_ob_o1")).status_code == 404
    # Two non-executives of the buyer cannot confirm on their own.
    req = client.post(f"{base}/confirm", headers=_auth("u_ob_b2")).json()["request_id"]
    assert _code(client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_b3"))) == "EXECUTIVE_REQUIRED"
    assert _code(client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_b2"))) == "SOD_SELF_APPROVAL"
    assert client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_s2")).status_code == 404
    assert _code(client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_gex"))) == "GEX_DOES_NOT_TRADE"
    # The generic approvals route neither raises nor decides a contract confirmation. This
    # contract has no project, so RLS already hides its request there (404); the route's own
    # refusal (409) is asserted on a project-bound contract in test_market_chain.
    assert client.post(f"/api/v1/approvals/{req}/decide", headers=_auth("u_ob_b1"),
                       json={"decision": "APPROVE"}).status_code in (404, 409)
    assert _code(client.post("/api/v1/approvals/evaluate", headers=_auth("u_ob_b1"),
                             json={"action_type": "TRADE_CONFIRM", "resource_id": cid})) == "TRADE_CONFIRM_ON_THE_CONTRACT"
    done = client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_b1")).json()
    assert done["confirmed_by"] == [BUYER] and done["trade_status"] == "pending_confirmation"
    assert _code(client.post(f"{base}/confirm", headers=_auth("u_ob_b1"))) == "ALREADY_CONFIRMED"
    req = client.post(f"{base}/confirm", headers=_auth("u_ob_s1")).json()["request_id"]
    assert client.post(f"/api/v1/approvals/{req}/decide", headers=_auth("u_ob_s2"),
                       json={"decision": "APPROVE"}).status_code in (404, 409)   # 409 itself: test_market_chain
    done = client.post(f"{base}/confirm/{req}/approve", headers=_auth("u_ob_s2")).json()
    assert done["trade_status"] == "confirmed" and done["confirmed_by"] == sorted([BUYER, SELLER])
    mine = client.get(f"{base}/confirmations", headers=_auth("u_ob_s1")).json()["confirmations"]
    assert [c["status"] for c in mine] == ["APPROVED"]


def test_gex_reads_state_chain_and_hashes_never_terms(client):
    rec = client.get(f"/api/v1/trading-book/records/{STATE['contract']}", headers=_auth("u_ob_gex")).json()
    assert rec["chain_intact"] and rec["trade_status"] == "confirmed"
    assert "terms" not in rec and "parties" not in rec and "project_id" not in rec
    assert [e["event_type"] for e in rec["events"]] == ["CREATED_FROM_MATCH", "CONFIRMED", "CONFIRMED", "STATUS_CHANGED"]


def _owner_dsn() -> str:
    import os

    return os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + DSN["url"].rsplit("/", 1)[1]


def test_the_chain_is_append_only_for_every_role_and_a_rewrite_is_detected(client):
    from pg_support import connect_dsn

    cid = STATE["contract"]
    for dsn, refused in ((DSN["url"], "permission denied"), (_owner_dsn(), "EVENT_APPEND_ONLY")):
        conn = connect_dsn(dsn)                                                  # the runtime, then the owner
        cur = conn.cursor()
        for sql in ("UPDATE tb_contract_event SET note = 'x' WHERE contract_id = %s",
                    "DELETE FROM tb_contract_event WHERE contract_id = %s"):
            cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")       # a rollback resets it
            with pytest.raises(Exception, match=refused):
                cur.execute(sql, (cid,))
            conn.rollback()
        conn.close()
    # Even the owner who disables the trigger cannot rewrite unnoticed.
    conn = connect_dsn(_owner_dsn())
    cur = conn.cursor()
    cur.execute("ALTER TABLE tb_contract_event DISABLE TRIGGER tb_contract_event_append_only")
    cur.execute("UPDATE tb_contract_event SET at = at + interval '1 second' WHERE contract_id = %s AND seq = 2", (cid,))
    from app.core import market_engine as me
    from app.trading_book import record

    mconn = me._conn()
    try:
        conn_intact = None
        conn.commit()
        conn_intact = record.chain_intact(mconn, cid)
    finally:
        mconn.close()
        cur.execute("UPDATE tb_contract_event SET at = at - interval '1 second' WHERE contract_id = %s AND seq = 2", (cid,))
        cur.execute("ALTER TABLE tb_contract_event ENABLE TRIGGER tb_contract_event_append_only")
        conn.commit()
        conn.close()
    assert conn_intact is False
    mconn = me._conn()
    try:
        assert record.chain_intact(mconn, cid)                                   # and holds again once restored
    finally:
        mconn.close()


def test_frozen_contract_terms_cannot_change(client):
    from pg_support import connect_dsn

    v = _q("SELECT terms_id FROM tb_contract_version WHERE contract_id = %s", (STATE["contract"],))
    conn = connect_dsn(DSN["url"])
    cur = conn.cursor()
    for sql in ("UPDATE tb_clause SET attrs = '{}' WHERE terms_id = %s", "DELETE FROM tb_sub_leg WHERE terms_id = %s",
                "INSERT INTO tb_clause (terms_id, clause_type, seq) VALUES (%s, 'damages', 9)"):
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")           # a rollback resets it
        with pytest.raises(Exception, match="TERMS_FROZEN"):
            cur.execute(sql, (v["terms_id"],))
        conn.rollback()
    conn.close()


# ── around the record ───────────────────────────────────────────────────────

def test_the_legacy_jti_routes_survive_record_rows(client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.trading_book import api as tb

    api = FastAPI()
    api.include_router(tb.router, prefix="/api/v1/trading-book")
    api.dependency_overrides[tb.get_db] = tb.tenant_session_dependency(
        sessionmaker(bind=create_engine(DSN["url"]), autoflush=False, expire_on_commit=False))
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    r = TestClient(api).get("/api/v1/trading-book/contracts", headers=_auth("u_ob_s1"))
    assert r.status_code == 200, r.text                                         # no 'terms' row breaks the JTI mapper
    assert all(c.get("contract_type") != "terms" for c in r.json())


def test_m2_converts_jti_contracts_and_is_idempotent(client):
    from app.core import market_engine as me
    from app.trading_book.migrate import jti_to_terms

    s = _q("SELECT id FROM tb_counterparty WHERE company_id = %s", (SELLER,))["id"]
    b = _q("SELECT id FROM tb_counterparty WHERE company_id = %s", (BUYER,))["id"]
    _q("INSERT INTO tb_contract (id, contract_number, owner_company_id, buy_side_id, sell_side_id, fuel_type, "
       "trade_date, effective_date, termination_date, notional_quantity, quantity_unit, currency, status, "
       "contract_type) VALUES ('00000000-0000-4000-8000-00000000f001', 'TEST-JTI-1', %s, %s, %s, 'EMEOH', "
       "'2026-11-01', '2027-01-01', '2027-03-31', 300, 't', 'EUR', 'COMMITTED', 'fixed_price')", (SELLER, b, s))
    _q("INSERT INTO tb_contract_fixed_price (id, fixed_price, price_basis) VALUES "
       "('00000000-0000-4000-8000-00000000f001', 850, 'flat')")
    _q("INSERT INTO tb_contract (id, contract_number, owner_company_id, buy_side_id, sell_side_id, fuel_type, "
       "trade_date, effective_date, termination_date, notional_quantity, quantity_unit, currency, status, "
       "contract_type) VALUES ('00000000-0000-4000-8000-00000000f002', 'TEST-JTI-2', %s, %s, %s, 'UNOBTAINIUM', "
       "'2026-11-01', '2027-01-01', '2027-03-31', 300, 't', 'EUR', 'DRAFT', 'fixed_price')", (SELLER, b, s))
    _q("INSERT INTO tb_contract_fixed_price (id, fixed_price, price_basis) VALUES "
       "('00000000-0000-4000-8000-00000000f002', 850, 'flat')")

    def run(execute):
        conn = me._conn()
        try:
            report = jti_to_terms.run(conn, execute=execute)
            conn.commit() if execute else conn.rollback()
            return report
        finally:
            conn.close()

    dry = run(False)
    assert [c["from"] for c in dry["converted"]] == ["TEST-JTI-1"]
    assert "UNOBTAINIUM" in " ".join(dry["stopped"]["TEST-JTI-2"])                # stops and reports, never guesses
    assert _q("SELECT count(*) AS n FROM tb_contract WHERE origin_ref LIKE 'jti:%%'")["n"] == 0
    run(True)
    c = _q("SELECT id, trade_status FROM tb_contract WHERE origin_ref = 'jti:00000000-0000-4000-8000-00000000f001'")
    assert c["trade_status"] == "confirmed"
    flows = _q("SELECT f.quantity, f.unit_price FROM tb_flow f JOIN tb_leg l ON l.id = f.leg_id JOIN tb_contract_version v "
               "ON v.terms_id = l.terms_id WHERE v.contract_id = %s AND f.flow_type = 'fixed_cash' ORDER BY f.seq",
               (c["id"],), many=True)
    assert [(r["quantity"], r["unit_price"]) for r in flows] == [(100, 850)] * 3   # the old engine's flat months
    note = _q("SELECT note FROM tb_contract_event WHERE contract_id = %s", (c["id"],))["note"]
    assert "NOT confirmed through TRADE_CONFIRM" in note
    again = run(True)
    assert again["skipped_already_converted"] == ["TEST-JTI-1"] and again["converted"] == []


def test_a_producer_declares_a_capacity_of_its_own_project(client):
    body = {"project_id": PID, "project_name": "TEST order-book plant", "molecule": "e-Methanol", "capacity_mtpd": 50}
    r = client.post("/api/v1/capacities/", headers=_auth("u_ob_s1"), json=body)
    assert r.status_code == 201, r.text                                         # 084: before, RLS refused this
    assert r.json()["project_id"] == PID and r.json()["id"] != PID
    assert _code(client.post("/api/v1/capacities/", headers=_auth("u_ob_b1"), json=body)) == "NOT_YOUR_PROJECT"
    assert _code(client.post("/api/v1/capacities/", headers=_auth("u_ob_gex"), json=body)) == "GEX_DOES_NOT_TRADE"


def test_rls_a_capacity_is_written_only_by_its_projects_owner():
    from pg_support import connect_dsn

    conn = connect_dsn(DSN["url"])
    cur = conn.cursor()
    cur.execute("SET ROLE gex_app")
    cur.execute("SET app.current_company_id = %s", (BUYER,))
    with pytest.raises(Exception, match="row-level security"):
        cur.execute("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) "
                    "VALUES ('cap_TEST_ob_foreign', %s, 'x', 'e-Methanol', 1)", (PID,))
    conn.rollback()
    cur.execute("SET app.current_company_id = %s", (SELLER,))
    cur.execute("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) "
                "VALUES ('cap_TEST_ob_own', %s, 'x', 'e-Methanol', 1)", (PID,))
    conn.rollback()
    conn.close()


def test_the_generic_project_visibility_helper_still_takes_a_project_id():
    """app_company_can_see_capacity is used by eight policies (063–069) with a
    PROJECT id. 084's first draft redefined it to look up a capacity and broke
    every one of them; this pins its meaning."""
    from pg_support import connect_dsn

    conn = connect_dsn(DSN["url"])
    cur = conn.cursor()
    cur.execute("SELECT app_company_can_see_capacity(%s, %s) AS owner, app_company_can_see_capacity(%s, %s) AS other",
                (PID, SELLER, PID, OTHER))
    assert dict(cur.fetchone()) == {"owner": True, "other": False}
    conn.close()
