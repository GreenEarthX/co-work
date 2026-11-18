"""
Compatibility on the market (discovery Phase 1, R7; alembic 118), end to end on PostgreSQL.

A buyer's RFQ with a mandatory carbon-intensity limit; two listings, the cheaper one over the limit.
The compatible listing ranks first, the cheaper one is excluded and says why; Compare takes at most
four; only the RFQ's owner sees the assessment. A seller cannot propose an excluded listing; the
buyer may waive its own requirement. Every proposal stores the assessment it was made on, which is
never changed (check 6; report §6.3).
"""
from __future__ import annotations

import os

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import marketplace_sqlite, routes_market
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID = "proj_TEST_compat"
SELLER, BUYER, OTHER = "TEST Compat Seller", "TEST Compat Buyer", "TEST Compat Other"
S_ID, B_ID, O_ID = (reg.company_slug(c) for c in (SELLER, BUYER, OTHER))
CAP = "cap_TEST_compat"
CLEAN, DIRTY, SPARE = "tok_TEST_compat_clean", "tok_TEST_compat_dirty", "tok_TEST_compat_spare"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST compat plant", owner_company_name=SELLER,
                                   associated_company_names=(), jurisdiction="DE")
USERS = {"cx_seller": (SELLER, "PRODUCER"), "cx_buyer": (BUYER, "OFFTAKER"), "cx_other": (OTHER, "OFFTAKER")}
DSN: dict = {}
IDS: dict = {}


def _auth(uid):
    company, ctype = USERS[uid]
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company), "company_name": company,
        "company_type": ctype, "service_type": None, "business_function": "COMMERCIAL", "user_name": uid,
        "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED", "nda_signed_with": [],
        "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]}


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


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for uid, (company, ctype) in USERS.items():
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
        _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
           "business_function, user_name, account_state, is_active) VALUES (%s, %s, 'x', %s, %s, %s, 'COMMERCIAL', %s, "
           "'ACTIVE', 1) ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", reg.company_slug(company), company, ctype, uid))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, country) VALUES (%s,'TEST compat plant',"
       "%s,'e-Methanol','DE') ON CONFLICT DO NOTHING", (PID, S_ID))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,'TEST','e-Methanol',"
       "1000) ON CONFLICT DO NOTHING", (CAP, PID))
    for tok, ci in ((CLEAN, 9.4), (DIRTY, 32), (SPARE, 9.4)):
        _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
           "correlation_id, physical_form, created_at) VALUES (%s,%s,40,'2028-01-01','2028-12-31','e-Methanol','MINTED',"
           "%s,'liquid', now()::text) ON CONFLICT DO NOTHING", (tok, CAP, f"CAP-{tok[-5:]}"))
        _q("INSERT INTO token_carbon_intensity (token_id, value_gco2e_mj, method, system_boundary, calculation_date, basis, "
           "document_sha256, recorded_by) VALUES (%s, %s, 'DA 2023/1185', 'WtW', '2026-11-01', 'calculated', %s, "
           "'cx_seller')", (tok, ci, "c" * 64))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    mine = "SELECT id FROM tb_counterparty WHERE company_id IN (%s, %s, %s)"
    _q(f"UPDATE tb_rfq SET status = 'withdrawn' WHERE status = 'published' AND requester_id IN ({mine})", (S_ID, B_ID, O_ID))
    _q(f"UPDATE tb_order SET status = 'cancelled' WHERE status = 'open' AND owner_id IN ({mine})", (S_ID, B_ID, O_ID))
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
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _list(client, token, price):
    r = client.post("/api/v1/marketplace/offers", headers=_auth("cx_seller"), json={
        "token_id": token, "volume_mtpd": 40, "price_eur_kg": price, "delivery_start": "2028-01-01",
        "delivery_end": "2028-12-31", "offer_type": "firm", "listing_state": "OPEN", "incoterm": "FOB",
        "named_place": "Rotterdam"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_setup_listings_and_an_rfq_with_a_mandatory_limit(client):
    IDS["clean"] = _list(client, CLEAN, 1.2)
    IDS["dirty"] = _list(client, DIRTY, 0.01)                # far cheaper, over the limit
    IDS["spare"] = _list(client, SPARE, 1.25)
    r = client.post("/api/v1/market/rfqs", headers=_auth("cx_buyer"), json={
        "molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "max_price_eur_kg": 1.3, "requirements": {"max_ci_gco2e_mj": 28.2, "physical_form": "liquid",
                                                  "mandatory": ["max_ci_gco2e_mj"]}})
    assert r.status_code == 201, r.text
    IDS["rfq"] = r.json()["id"]


def test_eligibility_comes_before_price(client):                       # check 6
    r = client.get(f"/api/v1/market/rfqs/{IDS['rfq']}/compatibility", headers=_auth("cx_buyer"))
    assert r.status_code == 200, r.text
    rows = [c for c in r.json()["candidates"] if c["listing"]["id"] in IDS.values()]
    assert [c["listing"]["id"] for c in rows] == [IDS["clean"], IDS["spare"], IDS["dirty"]]
    dirty = rows[-1]["assessment"]
    assert dirty["status"] == "incompatible" and not dirty["eligible"]
    assert any(o["reason"] == "CI 32 gCO2e/MJ exceeds your 28.2 limit." and o["mandatory"] for o in dirty["outcomes"])
    assert rows[0]["assessment"]["status"] == "compatible"
    # the candidates are the anonymous listing: no seller, project, token or capacity
    assert not {"seller_company_id", "token_id", "capacity_id", "capacity_project_id", "location"} & set(rows[0]["listing"])


def test_compare_names_up_to_four_and_only_the_rfqs_owner_sees_it(client):
    r = client.get(f"/api/v1/market/rfqs/{IDS['rfq']}/compatibility?offer_ids={IDS['dirty']},{IDS['clean']}",
                   headers=_auth("cx_buyer"))
    assert [c["listing"]["id"] for c in r.json()["candidates"]] == [IDS["clean"], IDS["dirty"]]
    five = ",".join([IDS["clean"]] * 5)
    assert client.get(f"/api/v1/market/rfqs/{IDS['rfq']}/compatibility?offer_ids={five}",
                      headers=_auth("cx_buyer")).status_code == 422
    for uid in ("cx_other", "cx_seller"):
        assert client.get(f"/api/v1/market/rfqs/{IDS['rfq']}/compatibility", headers=_auth(uid)).status_code == 404


def test_a_seller_cannot_propose_an_excluded_listing(client):
    r = client.post("/api/v1/market/matches", headers=_auth("cx_seller"), json={"offer_id": IDS["dirty"], "rfq_id": IDS["rfq"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "REQUIREMENT_NOT_MET"
    assert "exceeds your 28.2 limit" in r.json()["detail"]["message"]


def test_a_proposal_stores_the_assessment_it_was_made_on(client):
    r = client.post("/api/v1/market/matches", headers=_auth("cx_seller"), json={"offer_id": IDS["clean"], "rfq_id": IDS["rfq"]})
    assert r.status_code == 201, r.text
    assert r.json()["compatibility"] == "compatible"
    row = _q("SELECT * FROM compatibility_assessment WHERE id = %s", (r.json()["assessment_id"],))[0]
    assert (row["purpose"], row["status"], row["company_id"], str(row["proposal_order_id"])) == (
        "proposal", "compatible", S_ID, r.json()["id"])
    assert row["requirements"]["max_ci_gco2e_mj"] == 28.2 and row["listing"]["id"] == IDS["clean"]
    IDS["stored"] = str(row["id"])


def test_the_buyer_may_waive_its_own_requirement_knowingly(client):
    r = client.post("/api/v1/market/matches", headers=_auth("cx_buyer"), json={"offer_id": IDS["dirty"], "rfq_id": IDS["rfq"]})
    assert r.status_code == 201, r.text
    assert r.json()["compatibility"] == "incompatible"
    assert _q("SELECT status, company_id FROM compatibility_assessment WHERE id = %s", (r.json()["assessment_id"],))[0] == {
        "status": "incompatible", "company_id": B_ID}


def test_a_stored_assessment_is_read_by_its_company_and_never_changed():
    conn = connect_dsn(DSN["url"])                                     # the runtime role, gex_app
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (B_ID,))
        cur.execute("SELECT count(*) AS n FROM compatibility_assessment WHERE id = %s", (IDS["stored"],))
        assert cur.fetchone()["n"] == 0                               # the seller's, not the buyer's
        cur.execute("SET app.current_company_id = %s", (S_ID,))
        cur.execute("SELECT count(*) AS n FROM compatibility_assessment WHERE id = %s", (IDS["stored"],))
        assert cur.fetchone()["n"] == 1
        with pytest.raises(psycopg2.Error, match="permission denied"):
            cur.execute("UPDATE compatibility_assessment SET status = 'incompatible' WHERE id = %s", (IDS["stored"],))
    finally:
        conn.rollback()
        conn.close()
    # Not even the table's owner: the trigger refuses it.
    admin = os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + DSN["url"].rsplit("/", 1)[1]
    for sql in ("UPDATE compatibility_assessment SET status = 'incompatible' WHERE id = %s",
                "DELETE FROM compatibility_assessment WHERE id = %s"):
        conn = connect_dsn(admin)
        try:
            with pytest.raises(psycopg2.Error, match="APPEND_ONLY"):
                conn.cursor().execute(sql, (IDS["stored"],))
        finally:
            conn.rollback()
            conn.close()
