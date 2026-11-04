"""
The GEX staff console is GEX's own view, for GEX staff only, and it writes
nothing (JML, 2026-11-03). Onboarding status is read from the records alone: a
registered account is found by its provisional company id and company name,
and a step is "done" only when its record exists.

Runs in the throwaway PostgreSQL database (conftest.pg_store), with the same
stand-in for the ABAC middleware as test_ciso_real_data_pg.py.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from pg_support import connect_dsn

CLIENT, FIXTURE_CO = "gexc_client_co", "test_gexc_fixture"
STAFF = {"user_id": "u_gexc_staff", "company_id": "greenearthx", "is_platform_admin": True}


@pytest.fixture(scope="module")
def client(pg_store):
    from app.db import session

    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company, name in ((CLIENT, "GexC Client Co"), (FIXTURE_CO, "TEST GexC Fixture")):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, name))
    rows = (
        # registered, not yet bound to the company: provisional id, same company name
        ("u_gexc_p1", "pending_ab12cd34", "GexC Client Co", "PENDING", None, None, 0),
        ("u_gexc_p2", "pending_ef56ab78", "GexC Client Co", "IN_VETTING", "u_gexc_caller", "USA-TEST-1", 0),
        # another company's applicant with a provisional id: must not be counted
        ("u_gexc_other", "pending_99999999", "Someone Else Ltd", "PENDING", None, None, 0),
        ("u_gexc_admin", "greenearthx", "GreenEarthX", "ACTIVE", None, None, 1),
    )
    for uid, company, cname, state, caller, agreement, admin in rows:
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state, phone_verified_by, agreement_ref, "
                    "is_platform_admin, kyc_status, clearance_level) "
                    "VALUES (%s, %s, 'TEST-not-a-hash', %s, %s, 'PRODUCER', 'EXECUTIVE', %s, %s, %s, %s, %s, "
                    "'UNVERIFIED', 'STANDARD') ON CONFLICT DO NOTHING",
                    (uid, f"{uid}@test.invalid", company, cname, f"TEST {uid}", state, caller, agreement, admin))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_gex_console

    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(routes_gex_console.router, prefix="/api/v1/gex-console")
    saved = session._sync_engine
    session._sync_engine = None
    try:
        yield TestClient(app)
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved


def _get(client, path, payload=STAFF):
    headers = {"x-test-payload": json.dumps(payload)} if payload else {}
    return client.get(f"/api/v1/gex-console{path}", headers=headers)


@pytest.mark.parametrize("path", ["/summary", f"/onboarding/{CLIENT}"])
def test_only_gex_staff_open_it(client, path):
    assert _get(client, path, None).status_code == 401
    client_exec = {"user_id": "u_gexc_p1", "company_id": CLIENT, "is_platform_admin": False}
    r = _get(client, path, client_exec)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "GEX_STAFF_ONLY"


def test_summary_lists_the_admins_and_flags_test_companies(client):
    body = _get(client, "/summary").json()
    assert "u_gexc_admin" in {a["user_id"] for a in body["administrators"]}
    assert all(a["user_id"] != "u_gexc_p1" for a in body["administrators"])
    flags = {c["company_id"]: c["is_test"] for c in body["companies"]}
    assert flags[FIXTURE_CO] is True and flags[CLIENT] is False
    assert body["vetting_queue_count"] >= 3


def test_the_rights_it_states_are_the_rule_in_force(client):
    from app.core.abac import PLATFORM_READ_RESOURCE_TYPES

    rights = _get(client, "/summary").json()["staff_rights"]
    assert rights["readable_on_every_project"] == sorted(PLATFORM_READ_RESOURCE_TYPES)
    assert rights["reviewer_gates"]["CERTIFIER"] == ["G2", "G11"]


def test_onboarding_finds_registered_accounts_by_provisional_id_and_name(client):
    body = _get(client, f"/onboarding/{CLIENT}").json()
    assert {a["user_id"] for a in body["accounts"]} == {"u_gexc_p1", "u_gexc_p2"}
    steps = {s["key"]: s for s in body["steps"]}
    assert steps["register"]["status"] == "done"
    assert steps["claim:u_gexc_p1"]["status"] == "waiting"
    assert steps["claim:u_gexc_p1"]["detail"] == "PENDING · no telephone recorded"
    assert steps["claim:u_gexc_p2"]["status"] == "done"
    assert steps["call:u_gexc_p2"]["status"] == "done"
    assert steps["agreement:u_gexc_p2"]["status"] == "done"
    # Both pieces of vetting are on file, so activation waits — for anyone but the caller.
    assert steps["activate:u_gexc_p2"]["status"] == "waiting"
    assert steps["activate:u_gexc_p2"]["detail"] == "Anyone but u_gexc_caller"
    assert steps["project"]["status"] == "waiting"


def test_an_unregistered_company_is_refused_not_invented(client):
    r = _get(client, "/onboarding/no_such_company")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "TENANT_NOT_REGISTERED"


def test_it_writes_nothing():
    from app.api.v1 import routes_gex_console

    methods = {m for route in routes_gex_console.router.routes for m in route.methods}
    assert methods <= {"GET", "HEAD"}, methods


def test_an_unreadable_store_answers_503_not_zero(client, monkeypatch):
    from app.db import session

    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(session, "get_sync_engine", broken)
    r = _get(client, "/summary")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "STORE_UNREADABLE"
