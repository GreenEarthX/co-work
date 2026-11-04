"""
A premise that removes evidence takes effect only on a document and a second
party; a contest restores the protections (JML 2026-10-28; alembic 077).

Before: the owner's executive set balance-sheet funding or a power model alone,
and the lender-protection or PPA items left the bar at once.

Throwaway PostgreSQL database (conftest.pg_store); the engine is faked — what
is asserted is which premises the engine is GIVEN, and who may move them.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pg_support import connect_dsn

OWNER, BUYER, OUTSIDER = "test_pm_owner", "test_pm_buyer", "test_pm_outsider"
PID = "proj_TEST_premises"
USERS = {
    "u_pm_exec": (OWNER, "EXECUTIVE", False), "u_pm_eng": (OWNER, "ENGINEERING", False),
    "u_pm_buyer": (BUYER, "COMMERCIAL", False), "u_pm_out": (OUTSIDER, "EXECUTIVE", False),
    "u_pm_gex": ("greenearthx", "EXECUTIVE", True),
}
NAMES = {OWNER: "Test PM Owner", BUYER: "Test PM Buyer", OUTSIDER: "Test PM Outsider", "greenearthx": "GreenEarthX"}


def _h(uid):
    company, fn, gex = USERS[uid]
    return {"x-test-payload": json.dumps({"user_id": uid, "company_id": company, "company_name": NAMES[company],
                                          "business_function": fn, "is_platform_admin": gex})}


@pytest.fixture(scope="module")
def client(pg_store, tmp_path_factory):
    import os
    saved_dir = os.environ.get("GEX_EVIDENCE_DOCS_DIR")
    os.environ["GEX_EVIDENCE_DOCS_DIR"] = str(tmp_path_factory.mktemp("premise_docs"))   # never the dev data dir
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, BUYER, OUTSIDER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST premises plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (PID, BUYER))
    cur.execute("INSERT INTO project_context (project_id, power_model, phase, financing_model, updated_by, "
                "updated_at) VALUES (%s, 'GRID_CONNECTED', 'development', 'PROJECT_FINANCE', 'TEST', now()::text) "
                "ON CONFLICT DO NOTHING", (PID,))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_bankability_proxy as proxy, routes_premises, routes_projects
    from app.db import session

    seen = []

    async def engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "t", "persona_gates": {"EXECUTIVE": []}}
        seen.append(json_data)
        return {"current_state": "SPECULATIVE", "rules_version": "t", "gate_evaluations": []}

    saved_engine, saved_session = proxy._call_engine, session._sync_engine
    proxy._call_engine = engine
    session._sync_engine = None
    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        from app.core.request_tenant import (reset_current_company, reset_current_user, set_current_company,
                                             set_current_user)
        raw = request.headers.get("x-test-payload")
        payload = json.loads(raw) if raw else None
        request.state.user_payload = payload
        t1 = set_current_company(("PLATFORM_ADMIN" if payload and payload["is_platform_admin"] else
                                  (payload or {}).get("company_id")))
        t2 = set_current_user((payload or {}).get("user_id"))
        try:
            return await call_next(request)
        finally:
            reset_current_company(t1)
            reset_current_user(t2)

    app.include_router(routes_premises.router, prefix="/api/v1")
    app.include_router(routes_projects.router, prefix="/api/v1/projects")
    c = TestClient(app)
    c.engine_calls = seen
    yield c
    proxy._call_engine = saved_engine
    if saved_dir is None:
        os.environ.pop("GEX_EVIDENCE_DOCS_DIR", None)
    else:
        os.environ["GEX_EVIDENCE_DOCS_DIR"] = saved_dir
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved_session


def _engine_premise(field):
    from app.api.v1.routes_bankability_proxy import _physical_payload
    from app.core.request_tenant import reset_current_company, set_current_company
    t = set_current_company("PLATFORM_ADMIN")
    try:
        return _physical_payload(PID)[field]
    finally:
        reset_current_company(t)


DOC = {"file": ("board_resolution.pdf", b"%PDF TEST balance-sheet funding resolution", "application/pdf")}


def test_the_old_route_refuses_a_change_that_removes_evidence(client):
    from app.core.auth import create_access_token

    token, _ = create_access_token({
        "user_id": "u_pm_exec", "email": "u_pm_exec@test.invalid", "company_id": OWNER,
        "company_name": NAMES[OWNER], "company_type": "PRODUCER", "service_type": None,
        "business_function": "EXECUTIVE", "user_name": "TEST u_pm_exec", "clearance_level": "STANDARD",
        "jurisdiction": "DE", "kyc_status": "UNVERIFIED", "nda_signed_with": [], "assigned_audits": [],
        "actor_type_per_project": {}})
    r = client.patch(f"/api/v1/projects/{PID}/context", headers={**_h("u_pm_exec"), "authorization": f"Bearer {token}"},
                     json={"financing_model": "BALANCE_SHEET"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "PREMISE_NEEDS_DOCUMENT_AND_SECOND_PARTY"
    assert _engine_premise("financing_model") == "PROJECT_FINANCE"


def test_a_removing_change_needs_a_document_and_waits_for_a_second_party(client):
    nodoc = client.post(f"/api/v1/premises/{PID}", headers=_h("u_pm_exec"),
                        data={"field": "financing_model", "to_value": "BALANCE_SHEET"})
    assert nodoc.status_code == 422 and nodoc.json()["detail"]["code"] == "PREMISE_NEEDS_DOCUMENT"
    assert client.post(f"/api/v1/premises/{PID}", headers=_h("u_pm_eng"), files=DOC,
                       data={"field": "financing_model", "to_value": "BALANCE_SHEET"}).status_code == 403
    r = client.post(f"/api/v1/premises/{PID}", headers=_h("u_pm_exec"), files=DOC,
                    data={"field": "financing_model", "to_value": "BALANCE_SHEET"})
    assert r.status_code == 201 and r.json()["status"] == "PENDING", r.text
    assert _engine_premise("financing_model") == "PROJECT_FINANCE"      # nothing changed yet
    cid = r.json()["change_id"]
    same = client.post(f"/api/v1/premises/{PID}/{cid}/confirm", headers=_h("u_pm_eng"))
    assert same.status_code == 403 and same.json()["detail"]["code"] == "SECOND_PARTY_REQUIRED"
    assert client.post(f"/api/v1/premises/{PID}/{cid}/confirm", headers=_h("u_pm_out")).status_code == 404
    ok = client.post(f"/api/v1/premises/{PID}/{cid}/confirm", headers=_h("u_pm_buyer"))
    assert ok.status_code == 200 and ok.json()["status"] == "CONFIRMED", ok.text
    assert _engine_premise("financing_model") == "BALANCE_SHEET"
    assert client.engine_calls and client.engine_calls[-1]["financing_model"] == "BALANCE_SHEET"   # re-evaluated


def test_a_contest_restores_the_protections_until_gex_decides(client):
    cid = next(c["id"] for c in client.get(f"/api/v1/premises/{PID}", headers=_h("u_pm_buyer")).json()["changes"]
               if c["field"] == "financing_model" and c["status"] == "CONFIRMED" and c["applied"])
    r = client.post(f"/api/v1/premises/{PID}/{cid}/contest", headers=_h("u_pm_buyer"),
                    data={"note": "The offtake requires lender-grade protections"},
                    files={"file": ("offtake_clause.pdf", b"%PDF TEST clause 14.2", "application/pdf")})
    assert r.status_code == 200 and r.json()["status"] == "CONTESTED", r.text
    assert _engine_premise("financing_model") == "PROJECT_FINANCE"      # protections back at once
    refused = client.post(f"/api/v1/premises/{PID}/{cid}/confirm", headers=_h("u_pm_buyer"))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "CONTESTED_GEX_DECIDES"
    assert client.post(f"/api/v1/premises/{PID}/{cid}/confirm", headers=_h("u_pm_gex")).status_code == 200
    assert _engine_premise("financing_model") == "BALANCE_SHEET"


def test_back_to_project_finance_strengthens_the_bar_and_applies_at_once(client):
    r = client.post(f"/api/v1/premises/{PID}", headers=_h("u_pm_exec"),
                    data={"field": "financing_model", "to_value": "PROJECT_FINANCE"})
    assert r.status_code == 201 and r.json()["status"] == "CONFIRMED"
    assert _engine_premise("financing_model") == "PROJECT_FINANCE"


def test_documents_of_a_decision_cannot_be_rewritten(client, pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    with pytest.raises(Exception, match="permission denied"):
        cur.execute("UPDATE project_premise_document SET filename = 'x' WHERE project_id = %s", (PID,))
    conn.rollback()
    conn.close()
