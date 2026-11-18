"""
What an anonymous listing shows and what an RFQ can require (Phase 1; D-C; alembic 117).

D-C (JML 2026-11-14): before an accepted enquiry a member sees the country of production, the named
place and Incoterm, the counterparty's role and vetting badge, firm or indicative and validity, and
the product with the EVIDENCE STATUS of each claim — never the company, site, contact, certificate
reference or document. An RFQ states structured requirements, fixed once published. A proposal
carries the listing's typed Incoterm into the contract (G-24).
"""
from __future__ import annotations

import psycopg2
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

PID = "proj_TEST_listing_fields"
SELLER, BUYER = "TEST Fields Seller", "TEST Fields Buyer"
S_ID, B_ID = reg.company_slug(SELLER), reg.company_slug(BUYER)
CAP, TOK = "cap_TEST_fields", "tok_TEST_fields"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST fields plant", owner_company_name=SELLER,
                                   associated_company_names=(), jurisdiction="DE")
USERS = {"lf_seller": (SELLER, "PRODUCER"), "lf_buyer": (BUYER, "OFFTAKER")}
DSN: dict = {}
SECRETS = ("token_id", "capacity_id", "project_id", "location", "correlation_id", "reference", "document_sha256",
           "facility_id", "seller_company_id", "buyer_name", "buyer_contact")


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
    for company, ctype in ((SELLER, "PRODUCER"), (BUYER, "OFFTAKER")):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
    # the seller's account passed vetting; the buyer's was grandfathered (no telephone, no agreement)
    _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, business_function, "
       "user_name, account_state, is_active, phone_verified_at, agreement_signed_at) VALUES ('lf_seller', "
       "'lf_seller@test.invalid', 'x', %s, %s, 'PRODUCER', 'COMMERCIAL', 'lf_seller', 'ACTIVE', 1, now()::text, now()::text) "
       "ON CONFLICT DO NOTHING", (S_ID, SELLER))
    _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, business_function, "
       "user_name, account_state, is_active) VALUES ('lf_buyer', 'lf_buyer@test.invalid', 'x', %s, %s, 'OFFTAKER', "
       "'COMMERCIAL', 'lf_buyer', 'ACTIVE', 1) ON CONFLICT DO NOTHING", (B_ID, BUYER))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, country) VALUES (%s,'TEST fields plant',"
       "%s,'e-Methanol','DE') ON CONFLICT DO NOTHING", (PID, S_ID))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,'TEST','e-Methanol',"
       "1000) ON CONFLICT DO NOTHING", (CAP, PID))
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, production_pathway, physical_form, specification_standard, created_at) VALUES (%s,%s,40,"
       "'2028-01-01','2028-12-31','e-Methanol','MINTED','CAP-FIELDS','PEM electrolysis + DAC methanol synthesis','liquid',"
       "'IMPCA', now()::text) ON CONFLICT DO NOTHING", (TOK, CAP))
    doc = "b" * 64
    _q("INSERT INTO token_carbon_intensity (token_id, value_gco2e_mj, method, system_boundary, calculation_date, basis, "
       "document_sha256, recorded_by) VALUES (%s, 9.4, 'DA 2023/1185', 'well-to-wheel', '2026-11-01', 'calculated', %s, "
       "'lf_seller')", (TOK, doc))
    _q("INSERT INTO token_quality (token_id, parameter, value, unit, basis, recorded_by) VALUES "
       "(%s, 'purity_pct_mass', 99.85, '%% m/m', 'declared', 'lf_seller')", (TOK,))
    _q("INSERT INTO product_certificate (project_id, kind, scheme, body, reference, scope, valid_from, valid_until, "
       "document_sha256, state, submitted_by, company_id, decided_by, decided_company_id, decided_at) VALUES "
       "(%s,'certificate','ISCC EU','TEST Body','TEST-SECRET-REF','site','2026-01-01','2030-12-31',%s,'verified',"
       "'lf_seller',%s,'reviewer','TEST reviewer co',now())", (PID, doc, S_ID))
    _q("INSERT INTO product_certificate (project_id, kind, scheme, body, reference, scope, valid_from, state, submitted_by, "
       "company_id) VALUES (%s,'certificate','CertifHy','TEST Body 2','TEST-SECRET-REF-2','site','2026-01-01','asserted',"
       "'lf_seller',%s)", (PID, S_ID))
    saved = session._sync_engine
    session._sync_engine = None
    yield
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
    api.include_router(capacity_sqlite.router, prefix="/api/v1/capacities")
    api.include_router(tokens_sqlite.router, prefix="/api/v1/tokens")
    api.include_router(routes_products.router, prefix="/api/v1/products")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


LISTING = {"token_id": TOK, "volume_mtpd": 40, "price_eur_kg": 1.1, "delivery_start": "2028-01-01",
           "delivery_end": "2028-12-31", "offer_type": "firm", "listing_state": "OPEN", "incoterm": "FOB",
           "named_place": "Rotterdam", "valid_until": "2027-12-31", "location": "TEST secret berth"}
REQ = {"max_ci_gco2e_mj": 28.2, "ci_min_basis": "calculated", "regimes": ["RFNBO"], "accepted_schemes": ["ISCC EU"],
       "min_evidence_state": "verified", "physical_form": "liquid",
       "quality_limits": {"purity_pct_mass": {"min": 99.85}, "water_ppm_mass": {"max": 1000}},
       "incoterms": ["FOB", "CIF"], "named_place": "Rotterdam", "delivery_country": "NL",
       "mandatory": ["max_ci_gco2e_mj", "regimes", "physical_form"]}
RFQ = {"molecule": "e-Methanol", "volume_mtpd": 10, "delivery_start": "2028-01-01", "delivery_end": "2028-12-31",
       "max_price_eur_kg": 1.3}


def _code(r):
    return r.json()["detail"]["code"]


def test_a_listing_shows_what_d_c_allows_and_nothing_that_identifies_the_seller(client):
    r = client.post("/api/v1/marketplace/offers", headers=_auth("lf_seller"), json=LISTING)
    assert r.status_code == 201, r.text
    offers = client.get("/api/v1/market/listings/offers", headers=_auth("lf_buyer")).json()["offers"]
    o = next(x for x in offers if x["incoterm"] == "FOB")
    assert (o["production_country"], o["incoterm"], o["named_place"], o["offer_type"]) == ("DE", "FOB", "Rotterdam", "firm")
    assert o["valid_until"].startswith("2027-12-31")
    assert (o["seller_role"], o["seller_vetting"]) == ("PRODUCER", "vetted")
    p = o["product"]
    assert (p["production_pathway"], p["physical_form"], p["specification_standard"]) == \
        ("PEM electrolysis + DAC methanol synthesis", "liquid", "IMPCA")
    assert p["carbon_intensity"] == {"value_gco2e_mj": 9.4, "method": "DA 2023/1185", "system_boundary": "well-to-wheel",
                                     "basis": "calculated"}
    assert [(q["parameter"], q["basis"]) for q in p["quality"]] == [("purity_pct_mass", "declared")]
    assert [(c["scheme"], c["status"], c["covers"]) for c in p["certificates"]] == \
        [("CertifHy", "asserted", "covers the site"), ("ISCC EU", "verified", "covers the site")]
    text = str(o)
    for secret in SECRETS:
        assert f"'{secret}'" not in text, secret
    assert "TEST-SECRET-REF" not in text and "TEST secret berth" not in text and "b" * 64 not in text


def test_an_invalid_incoterm_or_validity_is_refused(client):
    tok = "tok_TEST_fields_2"
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, created_at) VALUES (%s,%s,10,'2029-01-01','2029-12-31','e-Methanol','MINTED','CAP-F2',now()::text) "
       "ON CONFLICT DO NOTHING", (tok, CAP))
    body = {**LISTING, "token_id": tok, "volume_mtpd": 10, "delivery_start": "2029-01-01", "delivery_end": "2029-12-31"}
    assert _code(client.post("/api/v1/marketplace/offers", headers=_auth("lf_seller"),
                             json={**body, "incoterm": "XYZ"})) == "TERMS_INVALID"
    assert _code(client.post("/api/v1/marketplace/offers", headers=_auth("lf_seller"),
                             json={**body, "valid_until": "2030-06-30"})) == "LISTING_VALIDITY"


def test_an_rfq_states_structured_requirements_that_every_seller_sees(client):
    r = client.post("/api/v1/market/rfqs", headers=_auth("lf_buyer"), json={**RFQ, "requirements": REQ})
    assert r.status_code == 201, r.text
    rfqs = client.get("/api/v1/market/listings/rfqs", headers=_auth("lf_seller")).json()["rfqs"]
    seen = next(x for x in rfqs if x["id"] == r.json()["id"])
    assert seen["requirements"] == REQ
    assert (seen["buyer_role"], seen["buyer_vetting"]) == ("OFFTAKER", "not_yet_vetted")
    for secret in ("buyer_name", "buyer_contact", "location", "buyer_company_id"):
        assert secret not in seen


@pytest.mark.parametrize("bad, reason", [
    ({"colour": "green"}, "unknown requirement"),
    ({"quality_limits": {"shininess": {"max": 1}}}, "unknown quality parameter"),
    ({"incoterms": ["FOB", "XYZ"]}, "incoterms are among"),
    ({"min_evidence_state": "rumoured"}, "min_evidence_state is one of"),
    ({"mandatory": ["physical_form"]}, "mandatory lists requirements stated above"),
    ({"delivery_country": "Netherlands"}, "two-letter"),
])
def test_invalid_requirements_are_refused_with_the_reason(client, bad, reason):
    r = client.post("/api/v1/market/rfqs", headers=_auth("lf_buyer"), json={**RFQ, "requirements": bad})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "RFQ_REQUIREMENTS"
    assert reason in r.json()["detail"]["message"]


def test_a_published_rfqs_requirements_never_change():
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="RFQ_REQUIREMENTS_FIXED"):
            cur.execute("UPDATE tb_rfq SET requirements = '{}'::jsonb WHERE status = 'published' "
                        "AND requirements <> '{}'::jsonb")
    finally:
        conn.rollback()
        conn.close()


def test_the_listings_incoterm_becomes_the_contracts(client):
    offer = next(x for x in client.get("/api/v1/market/listings/offers", headers=_auth("lf_buyer")).json()["offers"]
                 if x["incoterm"] == "FOB")
    rfq = client.post("/api/v1/market/rfqs", headers=_auth("lf_buyer"), json=RFQ).json()
    m = client.post("/api/v1/market/matches", headers=_auth("lf_buyer"),
                    json={"offer_id": offer["id"], "rfq_id": rfq["id"], "delivery_terms": "TEST monthly parcels"})
    assert m.status_code == 201, m.text
    terms = _q("SELECT terms_id FROM tb_order WHERE id = %s", (m.json()["id"],))[0]["terms_id"]
    clauses = {c["clause_type"]: c["attrs"] for c in _q("SELECT clause_type, attrs FROM tb_clause WHERE terms_id = %s",
                                                        (terms,))}
    assert clauses["delivery"] == {"incoterm": "FOB", "named_place": "Rotterdam", "text": "TEST monthly parcels"}


# ── The listing wizard's reads (R8) ────────────────────────────────────────────────────────────

def test_the_wizard_reads_its_projects_capacities_and_tokens(client):
    caps = client.get(f"/api/v1/capacities/?project_id={PID}", headers=_auth("lf_seller")).json()["capacities"]
    assert [c["id"] for c in caps] == [CAP] and caps[0]["project_id"] == PID
    assert client.get("/api/v1/capacities/?project_id=proj_TEST_none", headers=_auth("lf_seller")).json()["capacities"] == []
    toks = client.get(f"/api/v1/tokens/?project_id={PID}", headers=_auth("lf_seller")).json()["tokens"]
    mine = next(t for t in toks if t["id"] == TOK)
    assert mine["project_id"] == PID and mine["lifecycle_state"] in ("MINTED", "RESERVED", "SPLIT")   # stated; the wizard offers MINTED only
    assert (mine["production_pathway"], mine["physical_form"]) == ("PEM electrolysis + DAC methanol synthesis", "liquid")
    # another company does not read the seller's capacities or tokens (RLS)
    assert client.get(f"/api/v1/capacities/?project_id={PID}", headers=_auth("lf_buyer")).json()["capacities"] == []
    assert client.get(f"/api/v1/tokens/?project_id={PID}", headers=_auth("lf_buyer")).json()["tokens"] == []


def test_the_wizard_previews_the_markets_own_summary_to_the_owner_only(client):
    r = client.get(f"/api/v1/products/tokens/{TOK}/listing-preview", headers=_auth("lf_seller"))
    assert r.status_code == 200, r.text
    product = r.json()["product"]
    assert product["carbon_intensity"]["basis"] == "calculated"
    assert {c["scheme"]: c["status"] for c in product["certificates"]} == {"ISCC EU": "verified", "CertifHy": "asserted"}
    flat = repr(product)
    assert not [k for k in SECRETS if f"'{k}'" in flat] and "TEST-SECRET-REF" not in flat
    assert client.get(f"/api/v1/products/tokens/{TOK}/listing-preview", headers=_auth("lf_buyer")).status_code == 404
