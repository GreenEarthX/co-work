"""
Check 9 (report §6.3): changed data updates views and assessments without rewriting history.

A buyer enquires about a listing and proposes on it while it meets the buyer's mandatory carbon-
intensity limit; both assessments are stored. The seller then records a new, higher carbon
intensity. The buyer's thread and both parties' pending proposal now say what changed since the
assessment (status, the requirement, the field); the stored assessments are unchanged and viewing
stores nothing; the acceptance stores its own assessment, made on the data as it is then.
"""
from __future__ import annotations

import json
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

PID = "proj_TEST_changed"
SELLER, BUYER, OTHER = "TEST Changed Seller", "TEST Changed Buyer", "TEST Changed Other"
S_ID, B_ID, O_ID = (reg.company_slug(c) for c in (SELLER, BUYER, OTHER))
CAP, TOK = "cap_TEST_changed", "tok_TEST_changed"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST changed plant", owner_company_name=SELLER,
                                   associated_company_names=(), jurisdiction="DE")
USERS = {"ch_seller": (SELLER, "PRODUCER", "COMMERCIAL"), "ch_engineer": (SELLER, "PRODUCER", "ENGINEERING"),
         "ch_buyer": (BUYER, "OFFTAKER", "COMMERCIAL"), "ch_other": (OTHER, "OFFTAKER", "COMMERCIAL")}
DSN: dict = {}
IDS: dict = {}


def _auth(uid):
    company, ctype, fn = USERS[uid]
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company), "company_name": company,
        "company_type": ctype, "service_type": None, "business_function": fn, "user_name": uid,
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


def _admin():
    return connect_dsn(os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + DSN["url"].rsplit("/", 1)[1])


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for uid, (company, ctype, fn) in USERS.items():
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
        _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
           "business_function, user_name, account_state, is_active) VALUES (%s, %s, 'x', %s, %s, %s, %s, %s, "
           "'ACTIVE', 1) ON CONFLICT DO NOTHING",
           (uid, f"{uid}@test.invalid", reg.company_slug(company), company, ctype, fn, f"TEST {uid}"))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, country) VALUES (%s,'TEST changed plant',"
       "%s,'e-Methanol','DE') ON CONFLICT DO NOTHING", (PID, S_ID))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,'TEST','e-Methanol',"
       "1000) ON CONFLICT DO NOTHING", (CAP, PID))
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, physical_form, created_at) VALUES (%s,%s,40,'2028-01-01','2028-12-31','e-Methanol','MINTED',"
       "'CAP-CHG','liquid', now()::text) ON CONFLICT DO NOTHING", (TOK, CAP))
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


def _code(r):
    return r.json().get("detail", {}).get("code") if isinstance(r.json().get("detail"), dict) else r.json().get("detail")


def _ci(value):
    _q("INSERT INTO token_carbon_intensity (token_id, value_gco2e_mj, method, system_boundary, calculation_date, basis, "
       "recorded_by) VALUES (%s, %s, 'TEST DA 2023/1185', 'WtW', '2026-11-01', 'estimate', 'ch_seller')", (TOK, value))


def _assessments():
    return _q("SELECT id, purpose, status FROM compatibility_assessment WHERE rfq_id = %s ORDER BY computed_at",
              (IDS["rfq"],))


def test_setup_an_assessed_enquiry_and_proposal(client):
    _ci(9.4)
    r = client.post("/api/v1/marketplace/offers", headers=_auth("ch_seller"), json={
        "token_id": TOK, "volume_mtpd": 40, "price_eur_kg": 1.2, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "offer_type": "firm", "listing_state": "OPEN", "incoterm": "FOB", "named_place": "Rotterdam"})
    assert r.status_code == 201, r.text
    IDS["listing"] = r.json()["id"]
    r = client.post("/api/v1/market/rfqs", headers=_auth("ch_buyer"), json={
        "molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "requirements": {"max_ci_gco2e_mj": 28.2, "mandatory": ["max_ci_gco2e_mj"]}})
    IDS["rfq"] = r.json()["id"]
    e = client.post("/api/v1/market/enquiries", headers=_auth("ch_buyer"), json={
        "listing_id": IDS["listing"], "about_rfq_id": IDS["rfq"], "body": "Still 9.4?"}).json()
    IDS["enq"] = e["id"]
    assert e.get("changed_since_assessed") is None                               # nothing changed yet
    m = client.post("/api/v1/market/matches", headers=_auth("ch_buyer"), json={"offer_id": IDS["listing"], "rfq_id": IDS["rfq"]})
    assert m.status_code == 201 and m.json()["compatibility"] == "compatible", m.text
    IDS["match"] = m.json()["id"]
    assert [(a["purpose"], a["status"]) for a in _assessments()] == [("enquiry", "compatible"), ("proposal", "compatible")]


def test_a_change_of_evidence_is_shown_to_whoever_assessed_and_history_stays(client):
    _ci(40.0)                                                                     # the seller records a new value
    before = _assessments()
    thread = client.get(f"/api/v1/market/enquiries/{IDS['enq']}", headers=_auth("ch_buyer")).json()
    ch = thread["changed_since_assessed"]
    assert (ch["status_then"], ch["status_now"], ch["eligible_now"], ch["purpose"]) == (
        "compatible", "incompatible", False, "enquiry")
    ci = next(o for o in ch["outcomes"] if o["requirement"] == "max_ci_gco2e_mj")
    assert (ci["then"], ci["now"]) == ("compatible", "incompatible") and "40" in ci["reason_now"]
    assert "product" in ch["listing_fields"]
    # The receiver's view of the thread carries no assessment of the buyer's (it is the buyer's).
    assert "changed_since_assessed" not in client.get(f"/api/v1/market/enquiries/{IDS['enq']}",
                                                      headers=_auth("ch_seller")).json()
    for uid in ("ch_buyer", "ch_seller"):
        mine = next(x for x in client.get("/api/v1/market/matches/mine", headers=_auth(uid)).json()["matches"]
                    if x["id"] == IDS["match"])
        assert mine["changed_since_assessed"]["status_now"] == "incompatible"
    assert _assessments() == before                                               # viewing stores nothing, changes nothing


def test_the_acceptance_keeps_the_assessment_it_was_made_on(client):
    r = client.post(f"/api/v1/market/matches/{IDS['match']}/accept", headers=_auth("ch_seller"))
    assert r.status_code == 200, r.text
    assert r.json()["compatibility"] == "incompatible"
    assert [(a["purpose"], a["status"]) for a in _assessments()] == [
        ("enquiry", "compatible"), ("proposal", "compatible"), ("acceptance", "incompatible")]
