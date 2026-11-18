"""
Check 10 of the discovery remediation (report §8): a producer and a buyer complete publication,
assessment and a non-binding enquiry in one isolated scenario, through the real routes only.

    producer (Commercial)  declares capacity -> mints a token -> records carbon intensity -> lists it
    buyer (Commercial)     raises an RFQ with a mandatory CI limit -> finds the listing on the market
                           (product and evidence, no identity) -> its supply list rates it Compatible
                           -> asks about it (non-binding), citing the RFQ
    producer               sees a badge, not a name -> shares contact
    buyer                  sees the producer's identity -> proposes (binding), the assessment stored
    a competing listing over the CI limit is excluded at any price, and its seller cannot propose it.

Every step is the screen's own API call (the listing wizard's, Market Discovery's, RFQs' Find supply,
Deals'). Nothing is inserted behind the routes but the tenants, accounts and project, which
onboarding owns.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import capacity_sqlite, marketplace_sqlite, routes_market, routes_products, tokens_sqlite
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID, PID2 = "proj_TEST_journey", "proj_TEST_journey_rival"
PRODUCER, RIVAL, BUYER = "TEST Journey Producer", "TEST Journey Rival", "TEST Journey Buyer"
P_ID, R_ID, B_ID = (reg.company_slug(c) for c in (PRODUCER, RIVAL, BUYER))
PROFILES = {PID: reg.ProjectAccessProfile(project_id=PID, project_name="TEST journey plant", owner_company_name=PRODUCER,
                                          associated_company_names=(), jurisdiction="DE"),
            PID2: reg.ProjectAccessProfile(project_id=PID2, project_name="TEST rival plant", owner_company_name=RIVAL,
                                           associated_company_names=(), jurisdiction="DE")}
USERS = {"j_producer": (PRODUCER, "PRODUCER"), "j_rival": (RIVAL, "PRODUCER"), "j_buyer": (BUYER, "OFFTAKER")}
DSN: dict = {}


def _auth(uid, key=None):
    company, ctype = USERS[uid]
    h = {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company), "company_name": company,
        "company_type": ctype, "service_type": None, "business_function": "COMMERCIAL", "user_name": uid,
        "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED", "nda_signed_with": [],
        "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]}
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


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for uid, (company, ctype) in USERS.items():
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
        _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
           "business_function, user_name, account_state, is_active) VALUES (%s, %s, 'x', %s, %s, %s, 'COMMERCIAL', %s, "
           "'ACTIVE', 1) ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", reg.company_slug(company), company, ctype,
                                                   f"TEST {uid}"))
    for pid, owner in ((PID, P_ID), (PID2, R_ID)):
        _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, country) VALUES (%s, %s, %s, "
           "'e-Methanol', 'DE') ON CONFLICT DO NOTHING", (pid, f"TEST {pid}", owner))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    mine = "SELECT id FROM tb_counterparty WHERE company_id IN (%s, %s, %s)"
    _q(f"UPDATE tb_rfq SET status = 'withdrawn' WHERE status = 'published' AND requester_id IN ({mine})", (P_ID, R_ID, B_ID))
    _q(f"UPDATE tb_order SET status = 'cancelled' WHERE status = 'open' AND owner_id IN ({mine})", (P_ID, R_ID, B_ID))
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILES.get(reg.normalize_project_id(pid))  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    for router, prefix in ((capacity_sqlite.router, "capacities"), (tokens_sqlite.router, "tokens"),
                           (routes_products.router, "products"), (marketplace_sqlite.router, "marketplace"),
                           (routes_market.router, "market")):
        api.include_router(router, prefix=f"/api/v1/{prefix}")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _publish(client, uid, pid, ci, price):
    """The listing wizard's calls: capacity, token, carbon intensity, listing (OPEN)."""
    cap = client.post("/api/v1/capacities/", headers=_auth(uid, f"cap-{pid}"), json={
        "project_id": pid, "project_name": f"TEST {pid}", "molecule": "e-Methanol", "capacity_mtpd": 100,
        "production_start": "2028-01-01", "production_end": "2028-12-31"})
    assert cap.status_code == 201, cap.text
    assert [c["id"] for c in client.get(f"/api/v1/capacities/?project_id={pid}", headers=_auth(uid)).json()["capacities"]] \
        == [cap.json()["id"]]
    tok = client.post("/api/v1/tokens/", headers=_auth(uid, f"tok-{pid}"), json={
        "capacity_id": cap.json()["id"], "tokenised_mtpd": 40, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "production_pathway": "TEST PEM + DAC synthesis", "physical_form": "liquid", "specification_standard": "IMPCA"})
    assert tok.status_code == 201, tok.text
    tid = tok.json()["id"]
    r = client.post(f"/api/v1/products/tokens/{tid}/carbon-intensity", headers=_auth(uid), json={
        "value_gco2e_mj": ci, "method": "TEST DA 2023/1185", "system_boundary": "WtW", "calculation_date": "2026-11-01",
        "basis": "estimate"})
    assert r.status_code == 201, r.text
    preview = client.get(f"/api/v1/products/tokens/{tid}/listing-preview", headers=_auth(uid)).json()["product"]
    assert preview["carbon_intensity"]["value_gco2e_mj"] == ci and preview["physical_form"] == "liquid"
    offer = client.post("/api/v1/marketplace/offers", headers=_auth(uid, f"offer-{pid}"), json={
        "token_id": tid, "volume_mtpd": 40, "price_eur_kg": price, "price_basis": "FIXED", "delivery_start": "2028-01-01",
        "delivery_end": "2028-12-31", "offer_type": "firm", "incoterm": "FOB", "named_place": "Rotterdam",
        "location": f"TEST berth of {uid}", "listing_state": "OPEN"})
    assert offer.status_code == 201, offer.text
    return offer.json()["id"]


def test_publication_assessment_enquiry_and_consent_end_to_end(client):          # check 10
    clean = _publish(client, "j_producer", PID, ci=9.4, price=1.2)
    dirty = _publish(client, "j_rival", PID2, ci=40.0, price=0.5)                   # cheaper, over the limit

    rfq = client.post("/api/v1/market/rfqs", headers=_auth("j_buyer", "journey-rfq-1"), json={
        "molecule": "e-Methanol", "volume_mtpd": 20, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "max_price_eur_kg": 1.3, "buyer_contact": "TEST buyer desk",
        "requirements": {"max_ci_gco2e_mj": 28.2, "physical_form": "liquid", "incoterms": ["FOB"],
                         "mandatory": ["max_ci_gco2e_mj", "physical_form"]}})
    assert rfq.status_code == 201, rfq.text
    rfq_id = rfq.json()["id"]

    # Search: the buyer sees both listings with their product and evidence, never a seller.
    market = {o["id"]: o for o in client.get("/api/v1/market/listings/offers?molecule=e-Methanol",
                                             headers=_auth("j_buyer")).json()["offers"]}
    assert {clean, dirty} <= set(market)
    seen = market[clean]
    assert seen["product"]["carbon_intensity"]["basis"] == "estimate" and seen["incoterm"] == "FOB"
    flat = json.dumps(seen)
    for secret in (PRODUCER, P_ID, "j_producer", "berth", PID):
        assert secret not in flat

    # Compare: eligibility before price.
    found = client.get(f"/api/v1/market/rfqs/{rfq_id}/compatibility?offer_ids={dirty},{clean}",
                       headers=_auth("j_buyer")).json()["candidates"]
    assert [c["listing"]["id"] for c in found] == [clean, dirty]
    assert found[0]["assessment"]["status"] == "compatible" and not found[1]["assessment"]["eligible"]
    rival = client.post("/api/v1/market/matches", headers=_auth("j_rival"), json={"offer_id": dirty, "rfq_id": rfq_id})
    assert rival.status_code == 409 and rival.json()["detail"]["code"] == "REQUIREMENT_NOT_MET"

    # Enquiry: non-binding, anonymous until the producer consents.
    sent = client.post("/api/v1/market/enquiries", headers=_auth("j_buyer", "journey-enq-1"), json={
        "listing_id": clean, "about_rfq_id": rfq_id, "body": "Can you hold 20 MTPD for Q1?",
        "evidence_request": "Your carbon-intensity calculation"})
    assert sent.status_code == 201, sent.text
    eid = sent.json()["id"]
    received = client.get(f"/api/v1/market/enquiries/{eid}", headers=_auth("j_producer")).json()
    assert received["role"] == "received" and "identity" not in received["counterparty"]
    assert BUYER not in json.dumps(received) and "j_buyer" not in json.dumps(received)
    shared = client.post(f"/api/v1/market/enquiries/{eid}/share-contact", headers=_auth("j_producer"))
    assert shared.status_code == 200 and shared.json()["counterparty"]["identity"]["company_name"] == BUYER
    mine = client.get(f"/api/v1/market/enquiries/{eid}", headers=_auth("j_buyer")).json()["counterparty"]["identity"]
    assert (mine["company_name"], mine["person"]["email"], mine["details"]["location"]) == (
        PRODUCER, "j_producer@test.invalid", "TEST berth of j_producer")

    # Then, and only as a separate act, the binding proposal, on the assessment it was made on.
    proposal = client.post("/api/v1/market/matches", headers=_auth("j_buyer"), json={"offer_id": clean, "rfq_id": rfq_id})
    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["compatibility"] == "compatible"
    stored = _q("SELECT purpose FROM compatibility_assessment WHERE rfq_id = %s ORDER BY computed_at", (rfq_id,))
    assert [r["purpose"] for r in stored] == ["enquiry", "proposal"]
    events = {r["event_type"] for r in _q("SELECT event_type FROM platform_events WHERE object_id = %s", (eid,))}
    assert {"enquiry.sent", "enquiry.contact_shared"} <= events
