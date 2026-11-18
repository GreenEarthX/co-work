"""
PROBES, not tests — run explicitly: pytest tests/probe_discovery_pg.py
(the file name does not match test_*.py, so the suite never collects it).

Characterises current behaviour for the discovery review (13 Nov 2026) in the throwaway
PostgreSQL database built by the migrations (conftest.pg_store) — never the dev database.
Each probe RECORDS what happened; it asserts nothing about what should happen. Results are
written to the path in $PROBE_OUT as JSON.

Real ABAC middleware, real routes: /api/v1/market, /api/v1/marketplace, /api/v1/tokens,
/api/v1/capacities.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import capacity_sqlite, marketplace_sqlite, routes_market, tokens_sqlite
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings

PID = "proj_TEST_probe_seller"
SELLER, BUYER = "TEST Probe Seller", "TEST Probe Buyer"
S_ID, B_ID = reg.company_slug(SELLER), reg.company_slug(BUYER)
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST probe plant", owner_company_name=SELLER,
                                   associated_company_names=(BUYER,), jurisdiction="DE")
USERS = {  # uid -> (company, company_type, business_function)
    "p_s_com": (SELLER, "PRODUCER", "COMMERCIAL"), "p_s_cfo": (SELLER, "PRODUCER", "FINANCE_TREASURY"),
    "p_s_eng": (SELLER, "PRODUCER", "ENGINEERING"),
    "p_b_com": (BUYER, "OFFTAKER", "COMMERCIAL"), "p_b_cfo": (BUYER, "OFFTAKER", "FINANCE_TREASURY"),
}
R: dict = {}
DSN: dict = {}


def _auth(uid):
    company, ctype, fn = USERS[uid]
    tok = create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": ctype, "service_type": None, "business_function": fn,
        "user_name": f"TEST {uid}", "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]
    return {"Authorization": f"Bearer {tok}"}


def _q(sql, params=(), company="PLATFORM_ADMIN", commit=True):
    from pg_support import connect_dsn
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        if commit:
            conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for company, ctype in ((SELLER, "PRODUCER"), (BUYER, "OFFTAKER")):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
    for uid, (company, ctype, fn) in USERS.items():
        _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
           "business_function, user_name, account_state, is_active) VALUES (%s,%s,'x',%s,%s,%s,%s,%s,'ACTIVE',1) "
           "ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", reg.company_slug(company), company, ctype, fn, uid))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,%s,%s,'e-Methanol') "
       "ON CONFLICT DO NOTHING", (PID, "TEST probe plant", S_ID))
    _q("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) VALUES "
       "(%s,%s,'OFFTAKER','STAKEHOLDER','TEST') ON CONFLICT DO NOTHING", (PID, B_ID))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved
    out = os.environ.get("PROBE_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(R, f, indent=1, default=str)


@pytest.fixture
def c(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(routes_market.router, prefix="/api/v1/market")
    api.include_router(marketplace_sqlite.router, prefix="/api/v1/marketplace")
    api.include_router(tokens_sqlite.router, prefix="/api/v1/tokens")
    api.include_router(capacity_sqlite.router, prefix="/api/v1/capacities")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _rec(key, r, **extra):
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = r.text[:300]
    R[key] = {"status": r.status_code, "body": body if len(json.dumps(body, default=str)) < 1500 else str(body)[:1500],
              **extra}
    return r


RFQ = {"molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
       "max_price_eur_kg": 1.3, "location": "TEST Rotterdam", "buyer_contact": "buyer@test.invalid"}


def test_01_publication_path_through_the_api(c):
    """Seller commercial: capacity -> token (self-declared CONFIRMED) -> listing, via API only."""
    r = _rec("01a_capacity_create", c.post("/api/v1/capacities/", headers=_auth("p_s_com"), json={
        "project_id": PID, "project_name": "TEST probe plant", "molecule": "e-Methanol", "capacity_mtpd": 100,
        "location": "TEST Hamburg", "production_start": "2027-06-01", "compliance_certifications": ["RFNBO"]}))
    cap = r.json().get("id") if r.status_code < 300 else None
    R["_cap"] = cap
    r = _rec("01b_token_mint_self_declared_CONFIRMED", c.post("/api/v1/tokens/", headers=_auth("p_s_com"), json={
        "capacity_id": cap, "tokenised_mtpd": 40, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
        "certification_pathway": "RFNBO", "carbon_intensity_gco2e_mj": 9.0, "verification_state": "CONFIRMED"}))
    R["01c_token_rows_after_mint_call"] = _q("SELECT id, verification_state, lifecycle_state, tokenised_mtpd "
                                             "FROM tokens WHERE capacity_id = %s", (cap,))
    rows = R["01c_token_rows_after_mint_call"] or []
    tok = rows[0]["id"] if rows else None
    if tok is None:          # the API did not leave a token: seed one directly so the listing steps can run
        _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
           "lifecycle_state, correlation_id, carbon_intensity_gco2e_mj, certification_pathway) VALUES "
           "('tok_TEST_probe', %s, 40, '2028-01-01', '2028-12-31', 'e-Methanol', 'MINTED', 'CAP-PROBE', 9.0, 'RFNBO')",
           (cap,))
        tok = "tok_TEST_probe"
        R["01c_note"] = "token seeded directly (API mint left no row)"
    R["_tok"] = tok
    r = _rec("01d_listing_create_open", c.post("/api/v1/marketplace/offers", headers=_auth("p_s_com"), json={
        "token_id": tok, "volume_mtpd": 30, "price_eur_kg": 1.10, "delivery_start": "2028-01-01",
        "delivery_end": "2028-12-31", "location": "TEST Hamburg berth 7", "offer_type": "firm",
        "delivery_basis": "FOB Hamburg", "price_basis": "fixed", "min_order_kg": 500000,
        "country_of_origin": "DE", "esg_score": 80, "listing_state": "OPEN"}))
    R["_offer"] = r.json().get("id") if r.status_code < 300 else None


def test_02_buyer_sees_the_listing(c):
    r = _rec("02_buyer_listing_view", c.get("/api/v1/market/listings/offers", headers=_auth("p_b_com")))
    rows = r.json().get("offers", []) if r.status_code == 200 else []
    R["02_listing_fields_seen_by_buyer"] = sorted(rows[0].keys()) if rows else []


def test_03_role_not_checked_on_the_server(c):
    """Producer CFO and engineer: the menu hides RFQs and Market Discovery. What does the API say?"""
    _rec("03a_producer_cfo_creates_rfq", c.post("/api/v1/market/rfqs", headers=_auth("p_s_cfo"), json=RFQ))
    _rec("03b_producer_engineer_creates_rfq", c.post("/api/v1/market/rfqs", headers=_auth("p_s_eng"), json=RFQ))
    _rec("03c_producer_cfo_reads_market", c.get("/api/v1/market/listings/rfqs", headers=_auth("p_s_cfo")))


def test_04_replay_creates_duplicates(c):
    a = c.post("/api/v1/market/rfqs", headers=_auth("p_b_com"), json=RFQ)
    b = c.post("/api/v1/market/rfqs", headers=_auth("p_b_com"), json=RFQ)
    R["04_same_rfq_posted_twice"] = {"statuses": [a.status_code, b.status_code],
                                     "ids_distinct": a.json().get("id") != b.json().get("id"),
                                     "buyer_open_rfqs_now": len(c.get("/api/v1/market/rfqs/mine",
                                                                      headers=_auth("p_b_com")).json()["rfqs"])}
    R["_rfq"] = a.json().get("id")


def test_05_no_enquiry_route(c):
    _rec("05a_post_enquiry", c.post("/api/v1/market/enquiries", headers=_auth("p_b_com"),
                                    json={"offer_id": R.get("_offer"), "message": "Spec sheet please"}))
    if R.get("_offer") and R.get("_rfq"):
        _rec("05b_propose_match_is_the_only_contact", c.post("/api/v1/market/matches", headers=_auth("p_b_com"),
             json={"offer_id": R["_offer"], "rfq_id": R["_rfq"]}))
        m = c.get("/api/v1/market/matches/mine", headers=_auth("p_s_com")).json().get("matches", [])
        R["05c_seller_view_of_proposal_keys"] = sorted(m[0].keys()) if m else []
        R["05d_seller_sees_buyer_contact_or_location"] = bool(m) and any(
            k in m[0] for k in ("buyer_contact", "location"))


def test_06_mint_race_overshoots_capacity(c):
    """Deterministic interleaving of two mints on one capacity (READ COMMITTED): an uncommitted
    60 MTPD mint is in flight while the API checks SUM(tokenised_mtpd) for a second 60."""
    from pg_support import connect_dsn
    cap = R.get("_cap")
    if not cap:
        R["06_mint_race"] = "skipped: no capacity"
        return
    already = _q("SELECT COALESCE(SUM(tokenised_mtpd),0) AS s FROM tokens WHERE capacity_id = %s", (cap,))[0]["s"]
    other = connect_dsn(DSN["url"])
    cur = other.cursor()
    cur.execute("SET app.current_company_id = %s", (S_ID,))
    cur.execute("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
                "lifecycle_state, correlation_id) VALUES ('tok_TEST_race_A', %s, 40, '2028-01-01', '2028-12-31', "
                "'e-Methanol', 'MINTED', 'CAP-RACE')", (cap,))         # not committed yet
    r = c.post("/api/v1/tokens/", headers=_auth("p_s_com"), json={
        "capacity_id": cap, "tokenised_mtpd": 40, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31"})
    try:
        other.commit()
        other_result = "committed"
    except Exception as exc:  # noqa: BLE001 — 115 refuses it at commit
        other.rollback()
        other_result = str(exc).splitlines()[0][:160]
    other.close()
    total = _q("SELECT COALESCE(SUM(tokenised_mtpd),0) AS s FROM tokens WHERE capacity_id = %s", (cap,))[0]["s"]
    total = _q("SELECT COALESCE(SUM(tokenised_mtpd),0) AS s FROM tokens WHERE capacity_id = %s "
               "AND lifecycle_state NOT IN ('SPLIT', 'VOIDED')", (cap,))[0]["s"]
    R["06_mint_race"] = {"other_writer": other_result, "capacity_mtpd": 100, "before": already, "in_flight_mint": 40, "api_mint": 40,
                         "api_status": r.status_code, "total_after": total, "over_capacity": float(total) > 100}


def test_07_score_rewards_price_over_requirements():
    """The only comparator: an offer that fails the buyer's certification need still scores 100."""
    from app.api.v1.matching_sqlite import calculate_match_score
    offer = {"molecule": "e-Methanol", "price_eur_kg": 0.9, "volume_mtpd": 30, "delivery_start": "2028-01-01",
             "delivery_end": "2028-12-31", "certification_pathway": None, "carbon_intensity_gco2e_mj": 60.0}
    rfq = {"molecule": "e-Methanol", "max_price_eur_kg": 1.3, "volume_mtpd": 10, "delivery_start": "2028-01-01",
           "delivery_end": "2028-12-31", "compliance_requirements": ["RFNBO", "max CI 28.2 gCO2e/MJ"]}
    R["07_score_cert_and_ci_mismatch"] = calculate_match_score(offer, rfq)


def test_05e_buyer_cannot_mint_on_sellers_capacity(c):
    cap = R.get("_cap")
    if cap:
        _rec("05e_buyer_mints_on_seller_capacity", c.post("/api/v1/tokens/", headers=_auth("p_b_com"), json={
            "capacity_id": cap, "tokenised_mtpd": 1, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31"}))
