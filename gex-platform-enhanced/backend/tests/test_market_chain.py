"""
The market chain end to end — one synthetic, labelled TEST trade (gap register P0).

capacity -> token -> listing -> RFQ -> match -> both parties accept -> contract
-> settlement -> confirmation, through the REAL ABAC middleware and the REAL
/api/v1/market routes, in a throwaway PostgreSQL database built by the
migrations and dropped afterwards (conftest.pg_store). The market
is PostgreSQL only (JML, 2026-10-23) — there is no SQLite path to test.

Asserted at every step: who may act (and the refusals), the token's lifecycle
state, that listings never reveal the counterparty, and that one correlation_id
runs through the whole trail (G-02, G-03). JML's decisions of 2026-10-23:
anonymised listings, and both parties must accept.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_market
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings

PID = "proj_TEST_market_seller"
SELLER, BUYER, OTHER = "TEST Market Seller", "TEST Market Buyer", "TEST Market Bystander"
TOKEN, OFFER, CHAIN = "tok_TEST_market", "off_TEST_market", "CAP-TESTMKT1"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST market seller plant",
                                   owner_company_name=SELLER, associated_company_names=(),
                                   jurisdiction="DE")

USERS = {   # user -> (company name, platform admin)
    "u_seller": (SELLER, False), "u_buyer": (BUYER, False),
    "u_other": (OTHER, False), "u_gex": ("GreenEarthX", True),
}


def _token(uid: str) -> str:
    company, admin = USERS[uid]
    return create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": "PRODUCER", "service_type": None,
        "business_function": "EXECUTIVE", "user_name": f"TEST {uid}", "clearance_level": "STANDARD",
        "jurisdiction": "DE", "kyc_status": "VERIFIED", "nda_signed_with": [], "assigned_audits": [],
        "actor_type_per_project": {}, "is_platform_admin": admin})[0]


def _auth(uid):
    return {"Authorization": f"Bearer {_token(uid)}"}


DSN: dict = {}


def _q(sql: str, params: tuple = ()) -> dict | None:
    """Read the throwaway database directly, as GEX, bypassing nothing but tenancy."""
    from pg_support import connect_dsn

    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute(sql, params)
        conn.commit()
        return cur.fetchone() if cur.description else None
    finally:
        conn.close()


def _token_row():
    return dict(_q("SELECT * FROM tokens WHERE id = %s", (TOKEN,)))


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    DSN["url"] = pg_store
    _q("INSERT INTO capacities (id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,%s,%s)",
       (PID, "TEST market seller plant", "E_METHANOL", 100))
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
       "lifecycle_state, correlation_id, carbon_intensity_gco2e_mj) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
       (TOKEN, PID, 50, "2027-01-01", "2029-12-31", "E_METHANOL", "MINTED", CHAIN, 12.5))
    _q("INSERT INTO offers (id, token_id, molecule, volume_mtpd, price_eur_kg, delivery_start, delivery_end, "
       "location, status, listing_state, correlation_id, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
       (OFFER, TOKEN, "E_METHANOL", 50, 1.10, "2027-01-01", "2029-12-31", "TEST Hamburg berth 7",
        "draft", "DRAFT", CHAIN, "2026-10-23T00:00:00+00:00"))
    yield


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(routes_market.router, prefix="/api/v1/market")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api)


def _code(r):
    return r.json()["detail"]["code"]


STATE: dict = {}


def test_1_only_the_seller_lists_and_listing_reserves_the_token(client):
    assert _code(client.post(f"/api/v1/market/offers/{OFFER}/open", headers=_auth("u_other"))) == "NOT_YOUR_OFFER"
    assert _code(client.post(f"/api/v1/market/offers/{OFFER}/open", headers=_auth("u_gex"))) == "GEX_DOES_NOT_TRADE"
    r = client.post(f"/api/v1/market/offers/{OFFER}/open", headers=_auth("u_seller"))
    assert r.status_code == 200, r.text
    assert r.json()["listing_state"] == "OPEN"
    assert _token_row()["lifecycle_state"] == "RESERVED"


def test_2_listings_are_anonymised(client):
    offers = client.get("/api/v1/market/listings/offers", headers=_auth("u_buyer")).json()["offers"]
    assert [o["id"] for o in offers] == [OFFER]
    o = offers[0]
    assert o["price_eur_kg"] == 1.10 and o["carbon_intensity_gco2e_mj"] == 12.5 and o["mine"] is False
    for secret in ("token_id", "capacity_id", "project_id", "location", "correlation_id"):
        assert secret not in o, secret
    assert "TEST Hamburg" not in str(offers) and PID not in str(offers) and TOKEN not in str(offers)
    seller_view = client.get("/api/v1/market/listings/offers", headers=_auth("u_seller")).json()["offers"]
    assert seller_view[0]["mine"] is True and seller_view[0]["project_id"] == PID   # its own only


def test_3_buyer_requests_and_its_rfq_is_anonymised_too(client):
    assert _code(client.post("/api/v1/market/rfqs", headers=_auth("u_gex"), json={
        "molecule": "E_METHANOL", "volume_mtpd": 40, "delivery_start": "2027-01-01",
        "delivery_end": "2028-12-31"})) == "GEX_DOES_NOT_TRADE"
    r = client.post("/api/v1/market/rfqs", headers=_auth("u_buyer"), json={
        "molecule": "E_METHANOL", "volume_mtpd": 40, "max_price_eur_kg": 1.25,
        "delivery_start": "2027-01-01", "delivery_end": "2028-12-31",
        "location": "TEST Rotterdam", "buyer_contact": "TEST desk"})
    assert r.status_code == 201, r.text
    STATE["rfq"] = r.json()["id"]
    assert r.json()["buyer_company_id"] == reg.company_slug(BUYER)
    rfqs = client.get("/api/v1/market/listings/rfqs", headers=_auth("u_seller")).json()["rfqs"]
    assert [x["id"] for x in rfqs] == [STATE["rfq"]]
    for secret in ("buyer_company_id", "buyer_name", "buyer_contact", "location", "created_by"):
        assert secret not in rfqs[0], secret
    assert BUYER not in str(rfqs) and "TEST Rotterdam" not in str(rfqs)


def test_4_matching_is_bilateral_the_buyer_proposes_to_the_listing(client):
    # JML, 2026-10-23 (spec decision 2B): GEX pairs no one automatically.
    assert _code(client.post("/api/v1/market/matching/run", headers=_auth("u_buyer"))) == "AUTO_MATCHING_SUSPENDED"
    body = {"offer_id": OFFER, "rfq_id": STATE["rfq"]}
    assert _code(client.post("/api/v1/market/matches", headers=_auth("u_other"), json=body)) == "NOT_A_PARTY"
    assert _code(client.post("/api/v1/market/matches", headers=_auth("u_gex"), json=body)) == "GEX_DOES_NOT_TRADE"
    r = client.post("/api/v1/market/matches", headers=_auth("u_buyer"), json=body)
    assert r.status_code == 201, r.text
    mine = client.get("/api/v1/market/matches/mine", headers=_auth("u_buyer")).json()["matches"]
    assert len(mine) == 1 and mine[0]["status"] == "pending" and mine[0]["side"] == "buyer"
    STATE["match"] = mine[0]["id"]
    # Once matched, each party sees the other.
    assert mine[0]["seller_company_name"] == SELLER
    seller_side = client.get("/api/v1/market/matches/mine", headers=_auth("u_seller")).json()["matches"]
    assert seller_side[0]["buyer_name"] == BUYER
    assert client.get("/api/v1/market/matches/mine", headers=_auth("u_other")).json()["matches"] == []
    assert _code(client.post("/api/v1/market/matches", headers=_auth("u_buyer"), json=body)) == "NOT_MATCHABLE"


def test_5_both_parties_must_accept(client):
    m = STATE["match"]
    assert _code(client.post(f"/api/v1/market/matches/{m}/accept", headers=_auth("u_other"))) == "MATCH_NOT_FOUND"
    assert _code(client.post(f"/api/v1/market/matches/{m}/accept", headers=_auth("u_gex"))) == "GEX_DOES_NOT_TRADE"
    r = client.post(f"/api/v1/market/matches/{m}/accept", headers=_auth("u_seller"))
    assert r.json()["status"] == "pending" and r.json()["seller_accepted_by"] == "u_seller"
    assert _token_row()["lifecycle_state"] == "RESERVED"           # one side is not enough
    assert _code(client.post(f"/api/v1/market/matches/{m}/accept", headers=_auth("u_seller"))) == "ALREADY_ACCEPTED"
    r = client.post(f"/api/v1/market/matches/{m}/accept", headers=_auth("u_buyer"))
    assert r.json()["status"] == "accepted" and r.json()["buyer_accepted_by"] == "u_buyer"
    assert _token_row()["lifecycle_state"] == "MATCHED"
    assert _code(client.post(f"/api/v1/market/offers/{OFFER}/withdraw", headers=_auth("u_seller"))) == "LISTING_STATE"


def test_6_contract_from_the_agreed_match_once(client):
    body = {"match_id": STATE["match"], "delivery_terms": "TEST FOB", "payment_terms": "TEST 30 days"}
    assert _code(client.post("/api/v1/market/contracts", headers=_auth("u_other"), json=body)) == "MATCH_NOT_FOUND"
    r = client.post("/api/v1/market/contracts", headers=_auth("u_buyer"), json=body)
    assert r.status_code == 201, r.text
    c = r.json()
    STATE["contract"] = c["id"]
    assert (c["token_id"], c["seller_company_id"], c["buyer_company_id"], c["correlation_id"]) == \
        (TOKEN, reg.company_slug(SELLER), reg.company_slug(BUYER), CHAIN)
    assert _code(client.post("/api/v1/market/contracts", headers=_auth("u_seller"), json=body)) == "CONTRACT_EXISTS"


def test_7_settlement_the_payee_confirms_and_title_passes_to_the_buyer(client):
    r = client.post("/api/v1/market/settlements", headers=_auth("u_buyer"), json={
        "contract_id": STATE["contract"], "settlement_type": "SPOT", "volume_kg": 1000})
    assert r.status_code == 201, r.text
    s = r.json()
    STATE["settlement"] = s["settlement_id"]
    assert (s["total_amount"], s["token_id"], s["correlation_id"], s["settlement_status"]) == \
        (1100.0, TOKEN, CHAIN, "PENDING")
    url = f"/api/v1/market/settlements/{s['settlement_id']}/confirm"
    assert _code(client.post(url, headers=_auth("u_buyer"), json={"payment_reference": "TEST-REF"})) == "PAYEE_CONFIRMS"
    assert _code(client.post(url, headers=_auth("u_other"), json={"payment_reference": "TEST-REF"})) == "SETTLEMENT_NOT_FOUND"
    r = client.post(url, headers=_auth("u_seller"), json={"payment_reference": "TEST-REF-001"})
    assert r.json()["settlement_status"] == "CONFIRMED", r.text
    tok = _token_row()
    assert tok["lifecycle_state"] == "SETTLED" and tok["holder_company_id"] == reg.company_slug(BUYER)


def test_8_one_trail_from_listing_to_settlement(client):
    r = client.get(f"/api/v1/market/trail/{CHAIN}", headers=_auth("u_buyer"))
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    kinds = [e.get("event_type") for e in events]
    for expected in ("offer.opened", "match.created", "match.accepted", "match.agreed",
                     "contract.created", "settlement.created", "settlement.confirmed"):
        assert expected in kinds, (expected, kinds)
    assert kinds.count("token.state_changed") == 3                  # RESERVED, MATCHED, SETTLED
    assert {e.get("correlation_id") for e in events} == {CHAIN}
    assert _code(client.get(f"/api/v1/market/trail/{CHAIN}", headers=_auth("u_other"))) == "TRAIL_NOT_FOUND"


# ── The older routes delegate to the engine and cannot go round it ──────────

@pytest.fixture
def legacy(client):
    from app.api.v1 import contracts_sqlite, marketplace_sqlite, matching_sqlite, trader_rfqs

    api = client.app
    api.include_router(marketplace_sqlite.router, prefix="/api/v1/marketplace")
    api.include_router(matching_sqlite.router, prefix="/api/v1/matching")
    api.include_router(contracts_sqlite.router, prefix="/api/v1/contracts")
    api.include_router(trader_rfqs.router, prefix="/api/v1/trader/rfqs")
    return client


def test_9_contracts_are_shown_to_the_parties_only_and_never_deleted(legacy):
    cid = STATE["contract"]
    assert [c["id"] for c in legacy.get("/api/v1/contracts/", headers=_auth("u_seller")).json()["contracts"]] == [cid]
    assert legacy.get("/api/v1/contracts/", headers=_auth("u_other")).json()["contracts"] == []
    assert legacy.get(f"/api/v1/contracts/{cid}", headers=_auth("u_other")).status_code == 404
    assert _code(legacy.delete(f"/api/v1/contracts/{cid}", headers=_auth("u_buyer"))) == "CONTRACTS_ARE_RECORDS"
    assert _code(legacy.patch(f"/api/v1/contracts/{cid}/status?new_status=cancelled",
                              headers=_auth("u_gex"))) == "GEX_DOES_NOT_TRADE"


def test_10_trader_rfqs_are_the_callers_own_and_the_body_names_no_buyer(legacy):
    r = legacy.post("/api/v1/trader/rfqs/", headers=_auth("u_other"), json={
        "molecule": "E_METHANOL", "volume_mtpd": 5, "delivery_start": "2027-01-01",
        "delivery_end": "2027-12-31", "buyer_name": SELLER})
    assert r.status_code == 201, r.text
    rfq = r.json()
    assert rfq["status"] == "draft" and rfq["buyer_company_id"] == reg.company_slug(OTHER)
    assert rfq["buyer_name"] != SELLER                                # the body cannot impersonate
    assert legacy.get(f"/api/v1/trader/rfqs/{rfq['id']}", headers=_auth("u_buyer")).status_code == 404
    bad = legacy.patch(f"/api/v1/trader/rfqs/{rfq['id']}/status?new_status=matched", headers=_auth("u_other"))
    assert bad.status_code == 409, bad.text                           # 'matched' is set by the market
    ok = legacy.patch(f"/api/v1/trader/rfqs/{rfq['id']}/status?new_status=cancelled", headers=_auth("u_other"))
    assert ok.json()["status"] == "cancelled", ok.text


def test_11_matching_routes_show_my_matches_only(legacy):
    assert [m["id"] for m in legacy.get("/api/v1/matching/", headers=_auth("u_buyer")).json()["matches"]] \
        == [STATE["match"]]
    assert legacy.get("/api/v1/matching/", headers=_auth("u_other")).json()["matches"] == []
    assert legacy.get(f"/api/v1/matching/{STATE['match']}", headers=_auth("u_other")).status_code == 404


def test_12_a_listing_cannot_be_set_matched_by_hand_or_offered_by_a_stranger(legacy):
    assert _code(legacy.patch(f"/api/v1/marketplace/offers/{OFFER}/status?status=matched",
                              headers=_auth("u_seller"))) == "USE_TRANSITION"
    assert _code(legacy.post(f"/api/v1/marketplace/offers/{OFFER}/transition", headers=_auth("u_seller"),
                             json={"new_state": "MATCHED"})) == "SET_BY_THE_MARKET"
    body = {"token_id": TOKEN, "volume_mtpd": 1, "price_eur_kg": 1, "delivery_start": "2027-01-01",
            "delivery_end": "2027-12-31"}
    assert legacy.post("/api/v1/marketplace/offers", headers=_auth("u_other"), json=body).status_code == 404  # RLS hides it
    assert _code(legacy.post("/api/v1/marketplace/offers", headers=_auth("u_gex"), json=body)) == "NOT_YOUR_TOKEN"
    # A listing that was live is a record.
    assert _code(legacy.delete(f"/api/v1/marketplace/offers/{OFFER}", headers=_auth("u_seller"))) \
        == "LISTING_IS_A_RECORD"
