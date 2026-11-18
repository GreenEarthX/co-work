"""
A non-binding enquiry, and contact released only by consent (discovery Phase 1, R9; D-D; alembic 119).

A buyer asks about a listing, citing its own RFQ (the assessment is stored with the enquiry); the
seller sees the buyer's badge and the thread, never its name; only the seller can share contact or
decline; sharing releases both identities to both parties and is recorded in the ledger; declining
releases nothing. Commercial asks and answers, Engineering reads (D-B). The thread is append-only and
an enquiry never goes back (check 10's enquiry leg).
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

PID = "proj_TEST_enquiry"
SELLER, BUYER, OTHER = "TEST Enquiry Seller", "TEST Enquiry Buyer", "TEST Enquiry Other"
S_ID, B_ID, O_ID = (reg.company_slug(c) for c in (SELLER, BUYER, OTHER))
CAP, TOK = "cap_TEST_enquiry", "tok_TEST_enquiry"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST enquiry plant", owner_company_name=SELLER,
                                   associated_company_names=(), jurisdiction="DE")
USERS = {"eq_seller": (SELLER, "PRODUCER", "COMMERCIAL"), "eq_engineer": (SELLER, "PRODUCER", "ENGINEERING"),
         "eq_buyer": (BUYER, "OFFTAKER", "COMMERCIAL"), "eq_other": (OTHER, "OFFTAKER", "COMMERCIAL")}
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
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, country) VALUES (%s,'TEST enquiry plant',"
       "%s,'e-Methanol','DE') ON CONFLICT DO NOTHING", (PID, S_ID))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,'TEST','e-Methanol',"
       "1000) ON CONFLICT DO NOTHING", (CAP, PID))
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, physical_form, created_at) VALUES (%s,%s,40,'2028-01-01','2028-12-31','e-Methanol','MINTED',"
       "'CAP-ENQ','liquid', now()::text) ON CONFLICT DO NOTHING", (TOK, CAP))
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


def test_setup_a_listing_and_an_rfq(client):
    r = client.post("/api/v1/marketplace/offers", headers=_auth("eq_seller"), json={
        "token_id": TOK, "volume_mtpd": 40, "price_eur_kg": 1.2, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "offer_type": "indicative", "listing_state": "OPEN", "incoterm": "FOB", "named_place": "Rotterdam",
        "location": "TEST secret berth 7"})
    assert r.status_code == 201, r.text
    IDS["listing"] = r.json()["id"]
    r = client.post("/api/v1/market/rfqs", headers=_auth("eq_buyer"), json={
        "molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "max_price_eur_kg": 1.3, "buyer_contact": "TEST buyer desk +49 000", "location": "TEST buyer terminal",
        "requirements": {"physical_form": "liquid", "mandatory": ["physical_form"]}})
    assert r.status_code == 201, r.text
    IDS["rfq"] = r.json()["id"]


def test_a_buyer_asks_about_a_listing_without_revealing_itself(client):
    r = client.post("/api/v1/market/enquiries", headers=_auth("eq_buyer"), json={
        "listing_id": IDS["listing"], "about_rfq_id": IDS["rfq"], "body": "Is Q1 2028 firm?",
        "evidence_request": "The ISCC EU certificate covering 2028-Q1"})
    assert r.status_code == 201, r.text
    e = r.json()
    IDS["enq"] = e["id"]
    assert (e["role"], e["status"], e["subject"]["kind"]) == ("sent", "open", "listing")
    assert "identity" not in e["counterparty"] and e["counterparty"]["role"] == "PRODUCER"
    assert e["messages"] == [{"side": "you", "body": "Is Q1 2028 firm?",
                              "evidence_request": "The ISCC EU certificate covering 2028-Q1", "at": e["messages"][0]["at"]}]
    stored = _q("SELECT purpose, status, company_id FROM compatibility_assessment WHERE id = %s", (e["assessment_id"],))[0]
    assert stored == {"purpose": "enquiry", "status": "compatible", "company_id": B_ID}


@pytest.mark.parametrize("who, body, code", [
    ("eq_buyer", {"listing_id": "LISTING", "body": "again"}, "ENQUIRY_OPEN"),           # one open enquiry per subject
    ("eq_seller", {"listing_id": "LISTING", "body": "self"}, "SELF_ENQUIRY"),
    ("eq_buyer", {"listing_id": "LISTING", "rfq_id": "RFQ", "body": "both"}, "ENQUIRY_SUBJECT"),
    ("eq_buyer", {"listing_id": "00000000-0000-0000-0000-000000000000", "body": "?"}, "ENQUIRY_SUBJECT_NOT_FOUND"),
    ("eq_other", {"listing_id": "LISTING", "about_rfq_id": "RFQ", "body": "not my RFQ"}, "RFQ_NOT_FOUND"),
    ("eq_engineer", {"rfq_id": "RFQ", "body": "engineering reads"}, "ROLE_NOT_ALLOWED"),
    ("eq_other", {"listing_id": "LISTING", "body": "   "}, "ENQUIRY_MESSAGE"),
])
def test_what_an_enquiry_refuses(client, who, body, code):
    body = {k: IDS["listing"] if v == "LISTING" else IDS["rfq"] if v == "RFQ" else v for k, v in body.items()}
    r = client.post("/api/v1/market/enquiries", headers=_auth(who), json=body)
    assert r.status_code in (403, 404, 409, 422) and _code(r) == code, r.text


def test_the_seller_sees_the_thread_and_the_badge_never_the_name(client):
    rows = client.get("/api/v1/market/enquiries/mine", headers=_auth("eq_seller")).json()["enquiries"]
    e = next(x for x in rows if x["id"] == IDS["enq"])
    assert e["role"] == "received" and e["can"]["share_contact"] and e["assessment_id"] is None   # the buyer's, not shown
    full = client.get(f"/api/v1/market/enquiries/{IDS['enq']}", headers=_auth("eq_seller")).json()
    flat = json.dumps(full)
    for secret in (BUYER, B_ID, "eq_buyer", IDS["rfq"]):
        assert secret not in flat
    assert full["messages"][0]["side"] == "them"
    assert client.get(f"/api/v1/market/enquiries/{IDS['enq']}", headers=_auth("eq_other")).status_code == 404


def test_only_the_receiver_shares_and_only_commercial(client):
    r = client.post(f"/api/v1/market/enquiries/{IDS['enq']}/share-contact", headers=_auth("eq_buyer"))
    assert r.status_code == 403 and _code(r) == "NOT_THE_RECEIVER"
    r = client.post(f"/api/v1/market/enquiries/{IDS['enq']}/share-contact", headers=_auth("eq_engineer"))
    assert r.status_code == 403 and _code(r) == "ROLE_NOT_ALLOWED"
    r = client.post(f"/api/v1/market/enquiries/{IDS['enq']}/messages", headers=_auth("eq_seller"),
                    json={"body": "Firm from January; certificate on request after contact."})
    assert r.status_code == 200 and [m["side"] for m in r.json()["messages"]] == ["them", "you"]


def test_sharing_contact_releases_both_identities_to_both_and_is_recorded(client):
    r = client.post(f"/api/v1/market/enquiries/{IDS['enq']}/share-contact", headers=_auth("eq_seller"))
    assert r.status_code == 200, r.text
    seen_by_seller = r.json()["counterparty"]["identity"]
    assert (seen_by_seller["company_name"], seen_by_seller["person"]["email"]) == (BUYER, "eq_buyer@test.invalid")
    seen_by_buyer = client.get(f"/api/v1/market/enquiries/{IDS['enq']}", headers=_auth("eq_buyer")).json()["counterparty"]["identity"]
    assert (seen_by_buyer["company_name"], seen_by_buyer["person"]["name"]) == (SELLER, "TEST eq_seller")
    assert seen_by_buyer["details"] == {"location": "TEST secret berth 7"}
    ev = _q("SELECT event_type FROM platform_events WHERE event_type = 'enquiry.contact_shared' AND object_id = %s",
            (IDS["enq"],))
    assert len(ev) == 1
    assert client.post(f"/api/v1/market/enquiries/{IDS['enq']}/decline", headers=_auth("eq_seller")).status_code == 409


def test_declining_releases_nothing_and_closes_the_thread(client):
    r = client.post("/api/v1/market/enquiries", headers=_auth("eq_other"), json={"rfq_id": IDS["rfq"], "body": "We can supply."})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert client.post(f"/api/v1/market/enquiries/{eid}/withdraw", headers=_auth("eq_buyer")).status_code == 403
    r = client.post(f"/api/v1/market/enquiries/{eid}/decline", headers=_auth("eq_buyer"))
    assert r.status_code == 200 and r.json()["status"] == "declined" and "identity" not in r.json()["counterparty"]
    other_view = client.get(f"/api/v1/market/enquiries/{eid}", headers=_auth("eq_other")).json()
    assert "identity" not in other_view["counterparty"] and "TEST buyer desk" not in json.dumps(other_view)
    r = client.post(f"/api/v1/market/enquiries/{eid}/messages", headers=_auth("eq_other"), json={"body": "Please?"})
    assert r.status_code == 409 and _code(r) == "ENQUIRY_CLOSED"


def test_the_thread_is_append_only_and_an_enquiry_never_goes_back():
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="permission denied"):
            cur.execute("UPDATE market_enquiry_message SET body = 'changed'")
        conn.rollback()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="ENQUIRY_STATE"):
            cur.execute("UPDATE market_enquiry SET status = 'open' WHERE id = %s", (IDS["enq"],))
    finally:
        conn.rollback()
        conn.close()
    for sql, why in (("UPDATE market_enquiry_message SET body = 'x'", "APPEND_ONLY"),
                     ("DELETE FROM market_enquiry WHERE id = '" + IDS["enq"] + "'", "ENQUIRY_KEPT"),
                     ("UPDATE market_enquiry SET from_company_id = 'someone' WHERE id = '" + IDS["enq"] + "'", "ENQUIRY_FIXED")):
        conn = _admin()
        try:
            with pytest.raises(psycopg2.Error, match=why):
                conn.cursor().execute(sql)
        finally:
            conn.rollback()
            conn.close()
