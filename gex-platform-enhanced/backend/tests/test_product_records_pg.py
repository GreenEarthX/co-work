"""
Product records behind a token (Phase 1; alembic 116; decision D-F).

Pins: GEX computes document hashes; quality parameters are typed and a measured value needs its lab
report; a carbon intensity states method, boundary, date and basis; a certificate states its scope and
is never verified by the company that submits it; ONLY an appointed independent reviewer decides it;
a verified certificate past its date reads EXPIRED; a carved token shows its parent's records; and
the records are append-only and readable by the owner, the appointed reviewers and GEX only.
"""
from __future__ import annotations

import io

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_products
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID = "proj_TEST_products"
OWNER, CERT, OTHER = "TEST Product Owner", "TEST Certifier Co", "TEST Product Stranger"
O_ID, C_ID, X_ID = reg.company_slug(OWNER), reg.company_slug(CERT), reg.company_slug(OTHER)
CAP, TOK, CHILD = "cap_TEST_products", "tok_TEST_products", "tok_TEST_products-child"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST product plant", owner_company_name=OWNER,
                                   associated_company_names=(CERT,), jurisdiction="DE")
USERS = {  # uid -> (company, company_type, function)
    "pr_com": (OWNER, "PRODUCER", "COMMERCIAL"), "pr_eng": (OWNER, "PRODUCER", "ENGINEERING"),
    "pr_ceo": (OWNER, "PRODUCER", "EXECUTIVE"),
    "pr_cert": (CERT, "THIRD_PARTY", "ENGINEERING"),       # appointed CERTIFIER on the project
    "pr_cert2": (CERT, "THIRD_PARTY", "ENGINEERING"),      # same company, NOT appointed
    "pr_x": (OTHER, "PRODUCER", "COMMERCIAL"),
}
DSN: dict = {}


def _auth(uid, admin=False):
    company, ctype, fn = USERS.get(uid, ("GreenEarthX", "THIRD_PARTY", "EXECUTIVE"))
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company) if not admin else "greenearthx",
        "company_name": company, "company_type": ctype, "service_type": None, "business_function": fn,
        "user_name": uid, "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [PID] if uid == "pr_cert" else [], "actor_type_per_project": {},
        "is_platform_admin": admin})[0]}


def _q(sql, params=(), company="PLATFORM_ADMIN"):
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store, tmp_path_factory):
    from app.db import session
    DSN["url"] = pg_store
    for company, ctype in ((OWNER, "PRODUCER"), (CERT, "THIRD_PARTY"), (OTHER, "PRODUCER")):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
    for uid, (company, ctype, fn) in USERS.items():
        _q("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, business_function, "
           "user_name, account_state, is_active, assigned_audits_json) VALUES (%s,%s,'x',%s,%s,%s,%s,%s,'ACTIVE',1,%s) "
           "ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", reg.company_slug(company), company, ctype, fn, uid,
                                      f'["{PID}"]' if uid == "pr_cert" else "[]"))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,'TEST product plant',%s,"
       "'e-Methanol') ON CONFLICT DO NOTHING", (PID, O_ID))
    _q("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) VALUES "
       "(%s,%s,'CERTIFIER','REVIEWER','TEST') ON CONFLICT DO NOTHING", (PID, C_ID))
    _q("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES ('pr_cert', %s, 'CERTIFIER') "
       "ON CONFLICT DO NOTHING", (PID,))
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES (%s,%s,'TEST',"
       "'e-Methanol',1000) ON CONFLICT DO NOTHING", (CAP, PID))
    _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, lifecycle_state, "
       "correlation_id, production_pathway, physical_form) VALUES (%s,%s,10,'2028-01-01','2028-12-31','e-Methanol',"
       "'MINTED','CAP-PROD','PEM electrolysis + DAC methanol synthesis','liquid') ON CONFLICT DO NOTHING", (TOK, CAP))
    _q("INSERT INTO tokens (id, parent_token_id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
       "lifecycle_state, correlation_id) VALUES (%s,%s,%s,5,'2028-01-01','2028-06-30','e-Methanol','MINTED','CAP-PROD') "
       "ON CONFLICT DO NOTHING", (CHILD, TOK, CAP))
    import os
    os.environ["GEX_PRODUCT_DOCS_DIR"] = str(tmp_path_factory.mktemp("product_docs"))
    saved = session._sync_engine
    session._sync_engine = None
    yield
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(routes_products.router, prefix="/api/v1/products")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _doc(client, content=b"TEST lab report"):
    r = client.post(f"/api/v1/products/projects/{PID}/documents", headers=_auth("pr_com"),
                    files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def _code(r):
    return r.json()["detail"]["code"]


def test_gex_computes_the_document_hash_and_filing_twice_is_one_record(client):
    import hashlib
    sha = _doc(client, b"TEST certificate bytes")
    assert sha == hashlib.sha256(b"TEST certificate bytes").hexdigest()
    assert _doc(client, b"TEST certificate bytes") == sha
    assert _q("SELECT count(*) AS n FROM product_document WHERE sha256 = %s", (sha,))[0]["n"] == 1


def test_quality_is_typed_and_a_measured_value_needs_its_report(client):
    url = f"/api/v1/products/tokens/{TOK}/quality"
    assert _code(client.post(url, headers=_auth("pr_com"), json={"parameter": "shininess", "value": 1})) == "QUALITY_PARAMETER"
    assert _code(client.post(url, headers=_auth("pr_com"), json={"parameter": "purity_pct_mass", "value": 99.9,
                                                                   "basis": "measured"})) == "DOCUMENT_REQUIRED"
    assert client.post(url, headers=_auth("pr_eng"), json={"parameter": "purity_pct_mass", "value": 99.8}).status_code == 201
    r = client.post(url, headers=_auth("pr_com"), json={"parameter": "purity_pct_mass", "value": 99.9, "basis": "measured",
                                                       "document_sha256": _doc(client, b"TEST lab 1")})
    assert r.status_code == 201 and r.json()["unit"] == "% m/m"
    view = client.get(f"/api/v1/products/tokens/{TOK}", headers=_auth("pr_com")).json()
    assert [(q["parameter"], float(q["value"]), q["basis"]) for q in view["quality"]] == [("purity_pct_mass", 99.9, "measured")]


def test_carbon_intensity_states_its_method_boundary_and_basis(client):
    url = f"/api/v1/products/tokens/{TOK}/carbon-intensity"
    body = {"value_gco2e_mj": 9.4, "method": "DA 2023/1185", "system_boundary": "well-to-wheel",
            "calculation_date": "2026-11-01", "basis": "calculated"}
    assert _code(client.post(url, headers=_auth("pr_com"), json=body)) == "DOCUMENT_REQUIRED"
    assert client.post(url, headers=_auth("pr_com"), json={**body, "basis": "estimate"}).status_code == 201
    r = client.post(url, headers=_auth("pr_com"), json={**body, "document_sha256": _doc(client, b"TEST LCA")})
    assert r.status_code == 201
    ci = client.get(f"/api/v1/products/tokens/{TOK}", headers=_auth("pr_com")).json()["carbon_intensity"]
    assert (float(ci["value_gco2e_mj"]), ci["basis"], ci["method"]) == (9.4, "calculated", "DA 2023/1185")


def test_only_the_owners_declaring_functions_record_product_facts(client):
    url = f"/api/v1/products/tokens/{TOK}/quality"
    body = {"parameter": "water_ppm_mass", "value": 500}
    assert _code(client.post(url, headers=_auth("pr_ceo"), json=body)) == "ROLE_NOT_ALLOWED"
    assert _code(client.post(url, headers=_auth("pr_x"), json=body)) == "NOT_YOUR_PRODUCT"


def _certificate(client, **over):
    body = {"project_id": PID, "kind": "certificate", "scheme": "ISCC EU", "body": "TEST Cert Body",
            "reference": over.pop("reference", "TEST-REF-1"), "scope": "batch", "valid_from": "2026-01-01",
            "valid_until": "2027-12-31", "covers": [{"token_id": TOK, "quantity_t": 3650}], **over}
    return client.post("/api/v1/products/certificates", headers=_auth("pr_com"), json=body)


def test_a_certificate_states_its_scope_and_the_submitter_cannot_verify_it(client):
    assert _code(_certificate(client, reference="TEST-NOCOVER", covers=[])) == "CERTIFICATE_COVERAGE"
    assert _code(_certificate(client, reference="TEST-SITECOVER", scope="site")) == "CERTIFICATE_COVERAGE"
    asserted = _certificate(client, reference="TEST-ASSERTED").json()
    assert (asserted["state"], asserted["covers"]) == ("asserted", "covers this quantity")
    submitted = _certificate(client, reference="TEST-SUB", document_sha256=_doc(client, b"TEST cert 1")).json()
    assert submitted["state"] == "submitted"
    r = client.post(f"/api/v1/products/certificates/{submitted['id']}/decision", headers=_auth("pr_com"),
                    json={"decision": "verified"})
    assert _code(r) == "NOT_INDEPENDENT"


def test_only_an_appointed_independent_reviewer_decides(client):
    cert = _certificate(client, reference="TEST-DECIDE", document_sha256=_doc(client, b"TEST cert 2")).json()
    url = f"/api/v1/products/certificates/{cert['id']}/decision"
    assert _code(client.post(url, headers=_auth("pr_cert2"), json={"decision": "verified"})) == "NOT_APPOINTED"
    assert _code(client.post(url, headers=_auth("gex_staff", admin=True), json={"decision": "verified"})) == "GEX_DOES_NOT_VERIFY"
    r = client.post(url, headers=_auth("pr_cert"), json={"decision": "verified", "note": "TEST checked"})
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["effective_state"], r.json()["decided_by"]) == ("verified", "verified", "pr_cert")
    assert _code(client.post(url, headers=_auth("pr_cert"), json={"decision": "rejected"})) == "CERTIFICATE_STATE"
    asserted = _certificate(client, reference="TEST-NODOC").json()
    r = client.post(f"/api/v1/products/certificates/{asserted['id']}/decision", headers=_auth("pr_cert"),
                    json={"decision": "verified"})
    assert _code(r) == "CERTIFICATE_STATE"


def test_a_verified_certificate_past_its_date_reads_expired_everywhere(client):
    """Check 5 of the remediation report: a pending or expired certificate never appears verified."""
    _q("INSERT INTO product_certificate (project_id, kind, scheme, body, reference, scope, valid_from, valid_until, "
       "document_sha256, state, submitted_by, company_id, decided_by, decided_company_id, decided_at) VALUES "
       "(%s,'certificate','CertifHy','TEST','TEST-OLD','site','2020-01-01','2021-12-31',%s,'verified','pr_com',%s,"
       "'pr_cert',%s,now())", (PID, "a" * 64, O_ID, C_ID))
    view = client.get(f"/api/v1/products/tokens/{TOK}", headers=_auth("pr_com")).json()
    old = next(c for c in view["certificates"] if c["reference"] == "TEST-OLD")
    assert (old["state"], old["effective_state"], old["covers"]) == ("verified", "expired", "covers the site")
    pending = [c for c in view["certificates"] if c["state"] in ("asserted", "submitted")]
    assert pending and all(c["effective_state"] != "verified" for c in pending)


def test_a_carved_token_shows_the_records_of_the_token_it_came_from(client):
    view = client.get(f"/api/v1/products/tokens/{CHILD}", headers=_auth("pr_com")).json()
    assert view["carved_from"] == [TOK]
    assert view["carbon_intensity"] is not None and view["quality"]
    assert any(c["reference"] == "TEST-DECIDE" for c in view["certificates"])


def test_reading_is_for_the_owner_its_reviewers_and_gex(client):
    assert client.get(f"/api/v1/products/tokens/{TOK}", headers=_auth("pr_x")).status_code == 404
    assert client.get(f"/api/v1/products/tokens/{TOK}", headers=_auth("pr_cert")).status_code == 200
    assert _q("SELECT count(*) AS n FROM product_certificate", company=X_ID)[0]["n"] == 0
    assert _q("SELECT count(*) AS n FROM product_certificate", company=C_ID)[0]["n"] > 0


def test_the_records_are_append_only_and_a_decision_never_goes_back():
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="APPEND_ONLY|permission denied"):   # no UPDATE grant at all
            cur.execute("UPDATE token_quality SET value = 1")
        conn.rollback()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="PRODUCT_CERTIFICATE_STATE"):
            cur.execute("UPDATE product_certificate SET state = 'submitted' WHERE state = 'verified'")
        conn.rollback()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(psycopg2.Error, match="PRODUCT_CERTIFICATE_KEPT|permission denied"):   # no DELETE grant
            cur.execute("DELETE FROM product_certificate")
    finally:
        conn.rollback()
        conn.close()
