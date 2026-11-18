"""
Discovery review Phase 0, alembic 114:
  F13  a listing reserves exactly what it lists; the rest of the token stays available.
       (Acceptance carving is pinned in test_market_chain: the contract carries the agreed piece.)
  F12  an Idempotency-Key makes a retried create return the first response instead of a duplicate.

Real ABAC middleware and routes, throwaway PostgreSQL database (conftest.pg_store).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import marketplace_sqlite, routes_market, tokens_sqlite
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID = "proj_TEST_split_idem"
SELLER, BUYER = "TEST Split Seller", "TEST Split Buyer"
S_ID, B_ID = reg.company_slug(SELLER), reg.company_slug(BUYER)
CAP = "cap_TEST_split"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST split plant", owner_company_name=SELLER,
                                   associated_company_names=(), jurisdiction="DE")
USERS = {"x_seller": (SELLER, "PRODUCER"), "x_buyer": (BUYER, "OFFTAKER")}
DSN: dict = {}
RFQ = {"molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31"}


def _auth(uid, key=None):
    company, ctype = USERS[uid]
    h = {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": ctype, "service_type": None, "business_function": "COMMERCIAL",
        "user_name": uid, "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]}
    if key:
        h["Idempotency-Key"] = key
    return h


def _q(sql, params=()):
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _token(tid, mtpd, start, end):
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, created_at) VALUES (%s, %s, %s, %s, %s, 'e-Methanol', 'MINTED', 'CAP-SPLIT', now()::text)",
       (tid, CAP, mtpd, start, end))


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for company, ctype in ((SELLER, "PRODUCER"), (BUYER, "OFFTAKER")):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,'TEST split plant',%s,"
       "'e-Methanol') ON CONFLICT DO NOTHING", (PID, S_ID))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd, correlation_id) VALUES "
       "(%s, %s, 'TEST split plant', 'e-Methanol', 1000, 'CAP-SPLIT') ON CONFLICT DO NOTHING", (CAP, PID))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    # The throwaway database is shared by every module of the run: leave no open listing or RFQ
    # behind for another module's market view.
    mine = "SELECT id FROM tb_counterparty WHERE company_id IN (%s, %s)"
    _q(f"UPDATE tb_rfq SET status = 'withdrawn' WHERE status = 'published' AND requester_id IN ({mine})", (S_ID, B_ID))
    _q(f"UPDATE tb_order SET status = 'cancelled' WHERE status = 'open' AND owner_id IN ({mine})", (S_ID, B_ID))
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(routes_market.router, prefix="/api/v1/market")
    api.include_router(marketplace_sqlite.router, prefix="/api/v1/marketplace")
    api.include_router(tokens_sqlite.router, prefix="/api/v1/tokens")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _offer(client, token_id, mtpd, start, end, state="OPEN"):
    return client.post("/api/v1/marketplace/offers", headers=_auth("x_seller"), json={
        "token_id": token_id, "volume_mtpd": mtpd, "price_eur_kg": 1.1, "delivery_start": start,
        "delivery_end": end, "offer_type": "firm", "listing_state": state})


def _tonnes(rows):
    from datetime import date
    return sum(float(r["tokenised_mtpd"]) * ((date.fromisoformat(r["delivery_end"][:10])
                                              - date.fromisoformat(r["delivery_start"][:10])).days + 1) for r in rows)


# ── F13: a listing reserves exactly what it lists ────────────────────────────

def test_a_partial_listing_reserves_only_the_listed_piece(client):
    _token("tok_TEST_part", 40, "2028-01-01", "2028-12-31")
    r = _offer(client, "tok_TEST_part", 30, "2028-01-01", "2028-06-30")
    assert r.status_code == 201, r.text
    listed = r.json()["token_id"]
    assert listed != "tok_TEST_part"
    parent = _q("SELECT lifecycle_state, tokenised_mtpd, delivery_start, delivery_end FROM tokens WHERE id = %s",
                ("tok_TEST_part",))[0]
    assert parent["lifecycle_state"] == "SPLIT"
    kids = _q("SELECT t.id, t.lifecycle_state, t.tokenised_mtpd, t.delivery_start, t.delivery_end FROM tokens t "
              "WHERE t.parent_token_id = %s", ("tok_TEST_part",))
    k = {r["id"]: r for r in kids}
    assert (k[listed]["lifecycle_state"], k[listed]["tokenised_mtpd"], k[listed]["delivery_start"],
            k[listed]["delivery_end"]) == ("RESERVED", 30.0, "2028-01-01", "2028-06-30")
    rest = sorted((r["tokenised_mtpd"], r["delivery_start"], r["delivery_end"], r["lifecycle_state"])
                  for r in kids if r["id"] != listed)
    assert rest == [(10.0, "2028-01-01", "2028-12-31", "MINTED"), (30.0, "2028-07-01", "2028-12-31", "MINTED")]
    assert abs(_tonnes(kids) - _tonnes([parent])) < 1e-6           # the pieces partition the token exactly
    reasons = {r["reason"] for r in _q("SELECT reason FROM token_split WHERE parent_token_id = %s", ("tok_TEST_part",))}
    assert reasons == {"market_listing"}


def test_a_whole_listing_does_not_split(client):
    _token("tok_TEST_whole", 20, "2028-01-01", "2028-12-31")
    r = _offer(client, "tok_TEST_whole", 20, "2028-01-01", "2028-12-31")
    assert r.status_code == 201 and r.json()["token_id"] == "tok_TEST_whole"
    assert _q("SELECT lifecycle_state FROM tokens WHERE id = %s", ("tok_TEST_whole",))[0]["lifecycle_state"] == "RESERVED"


def test_a_listing_outside_its_tokens_window_is_refused(client):
    _token("tok_TEST_out", 20, "2028-01-01", "2028-06-30")
    r = _offer(client, "tok_TEST_out", 20, "2028-01-01", "2028-12-31")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "LISTING_OUTSIDE_TOKEN"
    assert _q("SELECT lifecycle_state FROM tokens WHERE id = %s", ("tok_TEST_out",))[0]["lifecycle_state"] == "MINTED"


# ── F12: idempotent creates ──────────────────────────────────────────────────

def _my_rfqs(client):
    return client.get("/api/v1/market/rfqs/mine", headers=_auth("x_buyer")).json()["rfqs"]


def test_a_retried_rfq_returns_the_first_response_and_creates_nothing(client):
    before = len(_my_rfqs(client))
    a = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-retry-0001"), json=RFQ)
    b = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-retry-0001"), json=RFQ)
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] == b.json()["id"] and b.headers.get("Idempotent-Replayed") == "true"
    assert len(_my_rfqs(client)) == before + 1


def test_the_same_key_for_a_different_request_is_refused(client):
    client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-reuse-0001"), json=RFQ)
    r = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-reuse-0001"), json={**RFQ, "volume_mtpd": 11})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_a_refused_request_releases_its_key(client):
    bad = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-fixit-0001"),
                      json={**RFQ, "delivery_end": "2027-01-01"})
    assert bad.status_code == 422
    good = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "rfq-fixit-0001"), json=RFQ)
    assert good.status_code == 201


def test_keys_belong_to_a_company(client):
    """The same key from another company is a different request, not a replay of this one."""
    a = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "shared-key-0001"), json=RFQ)
    b = client.post("/api/v1/market/rfqs", headers=_auth("x_seller", "shared-key-0001"), json=RFQ)
    assert (a.status_code, b.status_code) == (201, 201) and a.json()["id"] != b.json()["id"]
    assert b.headers.get("Idempotent-Replayed") is None


def test_a_retried_mint_mints_once(client):
    body = {"capacity_id": CAP, "tokenised_mtpd": 5, "delivery_start": "2029-01-01", "delivery_end": "2029-12-31"}
    before = _q("SELECT count(*) AS n FROM tokens WHERE capacity_id = %s AND delivery_start = '2029-01-01'", (CAP,))[0]["n"]
    a = client.post("/api/v1/tokens/", headers=_auth("x_seller", "mint-retry-0001"), json=body)
    b = client.post("/api/v1/tokens/", headers=_auth("x_seller", "mint-retry-0001"), json=body)
    assert (a.status_code, b.status_code) == (201, 201) and a.json()["id"] == b.json()["id"]
    after = _q("SELECT count(*) AS n FROM tokens WHERE capacity_id = %s AND delivery_start = '2029-01-01'", (CAP,))[0]["n"]
    assert after == before + 1


def test_a_malformed_key_is_refused(client):
    r = client.post("/api/v1/market/rfqs", headers=_auth("x_buyer", "bad key!"), json=RFQ)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "IDEMPOTENCY_KEY_FORMAT"


def test_the_database_refuses_a_market_split_that_loses_tonnes():
    """The partition rule is the database's, not only the application's (114: token_split_consistent)."""
    import psycopg2

    _token("tok_TEST_bad", 40, "2028-01-01", "2028-12-31")
    order = _q("SELECT id FROM tb_order LIMIT 1")[0]["id"]
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        for child, mtpd in (("tok_TEST_bad-a", 30), ("tok_TEST_bad-b", 5)):     # 35 of 40 MTPD: 5 MTPD lost
            cur.execute("INSERT INTO tokens (id, parent_token_id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, "
                        "molecule, lifecycle_state, correlation_id) VALUES (%s, 'tok_TEST_bad', %s, %s, '2028-01-01', "
                        "'2028-12-31', 'e-Methanol', 'MINTED', 'CAP-SPLIT')", (child, CAP, mtpd))
            cur.execute("INSERT INTO token_split (delivery_id, parent_token_id, child_token_id, kg, holder_company_id, "
                        "event_hash, reason, order_id, capacity_id, tokenised_mtpd, delivery_start, delivery_end) VALUES "
                        "(NULL, 'tok_TEST_bad', %s, 0, %s, repeat('0', 64), 'market_listing', %s, %s, %s, '2028-01-01', "
                        "'2028-12-31')", (child, S_ID, order, CAP, mtpd))
        cur.execute("UPDATE tokens SET lifecycle_state = 'SPLIT' WHERE id = 'tok_TEST_bad'")
        with pytest.raises(psycopg2.Error, match="TOKEN_SPLIT_TONNES"):
            conn.commit()
    finally:
        conn.rollback()
        conn.close()
