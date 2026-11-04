"""
The CISO workspace serves the company's REAL data, or says it is not recorded
(JML, 2026-10-25). It used to serve invented rosters, a random access feed,
invented compliance scores and sample barriers, and took the company from a
header defaulting to "bp_global_energy".

Runs in the throwaway PostgreSQL database (conftest.pg_store). The caller's
payload is bound by a stand-in for the ABAC middleware, which sets
request.state.user_payload exactly as the real one does.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pg_support import connect_dsn

A, B = "test_ciso_a", "test_ciso_b"
SOURCE = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "routes_ciso.py"


def _payload(user_id, company_id, admin=False):
    return {"user_id": user_id, "company_id": company_id, "is_platform_admin": admin}


@pytest.fixture(scope="module")
def client(pg_store):
    from app.db import session

    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (A, B):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    for uid, company, kyc in (("u_ciso_a1", A, "VERIFIED"), ("u_ciso_a2", A, "PENDING"),
                              ("u_ciso_b1", B, "VERIFIED")):
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state, kyc_status, clearance_level) "
                    "VALUES (%s, %s, 'TEST-not-a-hash', %s, %s, 'PRODUCER', 'CISO', %s, 'ACTIVE', %s, 'STANDARD') "
                    "ON CONFLICT DO NOTHING",
                    (uid, f"{uid}@test.invalid", company, f"TEST {company}", f"TEST {uid}", kyc))
    cur.execute("INSERT INTO auth_login_history (id, user_id, email, event_type, ip_address, timestamp, success) "
                "VALUES ('test_ciso_login_1', 'u_ciso_a1', 'u_ciso_a1@test.invalid', 'login', '127.0.0.1', %s, 0) "
                "ON CONFLICT DO NOTHING", (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_ciso

    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(routes_ciso.router, prefix="/api/v1/ciso")
    # projects_store reads through a cached engine; point it at the throwaway database.
    saved = session._sync_engine
    session._sync_engine = None
    try:
        yield TestClient(app)
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved


def _get(client, path, payload, company=None):
    headers = {"x-test-payload": json.dumps(payload)}
    if company:
        headers["x-ciso-company"] = company
    return client.get(f"/api/v1/ciso{path}", headers=headers)


def test_a_ciso_sees_its_own_accounts_only(client):
    users = _get(client, "/users", _payload("u_ciso_a1", A)).json()["users"]
    assert sorted(u["user_id"] for u in users) == ["u_ciso_a1", "u_ciso_a2"]
    assert all(u["mfa_enabled"] is None for u in users), "MFA is not recorded; it must not be invented"


def test_naming_another_company_is_refused_unless_gex_staff(client):
    assert _get(client, "/users", _payload("u_ciso_a1", A), company=B).status_code == 403
    staff = _get(client, "/users", _payload("u_staff", "greenearthx", admin=True), company=B)
    assert [u["user_id"] for u in staff.json()["users"]] == ["u_ciso_b1"]


def test_the_fetch_bridges_demo_header_is_ignored(client):
    """The frontend stamps x-demo-company (a slug of the company NAME) on every
    request; it must neither refuse a CISO nor redirect it."""
    r = client.get("/api/v1/ciso/users", headers={"x-test-payload": json.dumps(_payload("u_ciso_a1", A)),
                                                  "x-demo-company": "test-ciso-b"})
    assert r.status_code == 200 and {u["user_id"] for u in r.json()["users"]} == {"u_ciso_a1", "u_ciso_a2"}


def test_the_company_list_is_own_company_unless_gex_staff(client):
    own = _get(client, "/companies", _payload("u_ciso_a1", A)).json()["companies"]
    assert [c["company_id"] for c in own] == [A]
    staff = _get(client, "/companies", _payload("u_staff", "greenearthx", admin=True)).json()["companies"]
    assert {A, B} <= {c["company_id"] for c in staff}


def test_no_caller_is_refused(client):
    assert client.get("/api/v1/ciso/overview").status_code == 401


def test_overview_counts_are_real_and_nothing_is_scored(client):
    body = _get(client, "/overview", _payload("u_ciso_a1", A)).json()
    assert body["company_name"] == f"TEST {A}"
    assert body["security_score"] is None and body["kpis"]["mfa_enabled_pct"] is None
    assert body["kpis"]["total_users"] == 2 and body["kpis"]["kyc_verified"] == 1
    assert body["events_24h"]["deny"] == 1   # the one refused sign-in seeded above


def test_access_log_is_the_sign_in_history(client):
    events = _get(client, "/access-log", _payload("u_ciso_a1", A)).json()["events"]
    assert [(e["user_id"], e["decision"], e["resource_type"]) for e in events] == [("u_ciso_a1", "DENY", "SIGN_IN")]
    assert _get(client, "/access-log", _payload("u_ciso_b1", B)).json()["events"] == []


def test_compliance_is_not_recorded(client):
    body = _get(client, "/compliance", _payload("u_ciso_a1", A)).json()
    assert body["recorded"] is False and body["frameworks"] == [] and body["overall_score"] is None


def test_only_gex_staff_change_account_attributes(client):
    body = {"clearance_level": "CONFIDENTIAL"}
    own = client.patch("/api/v1/ciso/users/u_ciso_a2/attributes", json=body,
                       headers={"x-test-payload": json.dumps(_payload("u_ciso_a1", A))})
    assert own.status_code == 403
    staff = {"x-test-payload": json.dumps(_payload("u_staff", "greenearthx", admin=True)), "x-ciso-company": A}
    ok = client.patch("/api/v1/ciso/users/u_ciso_a2/attributes", json=body, headers=staff)
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["clearance_level"] == "CONFIDENTIAL"
    roles = client.patch("/api/v1/ciso/users/u_ciso_a2/attributes",
                         json={"actor_type_per_project": {"p": ["LENDER"]}}, headers=staff)
    assert roles.status_code == 422


def test_a_barrier_is_saved_and_seen_by_its_company_only(client):
    headers = {"x-test-payload": json.dumps(_payload("u_ciso_a1", A))}
    made = client.post("/api/v1/ciso/barriers", headers=headers,
                       json={"side_a": "TEST trading desk", "side_b": "TEST advisory", "barrier_type": "HARD"})
    assert made.status_code == 201, made.text
    barrier_id = made.json()["barrier"]["id"]
    assert [b["id"] for b in _get(client, "/barriers", _payload("u_ciso_a1", A)).json()["barriers"]] == [barrier_id]
    assert _get(client, "/barriers", _payload("u_ciso_b1", B)).json()["barriers"] == []
    assert _get(client, f"/barriers/{barrier_id}", _payload("u_ciso_b1", B)).status_code == 404


def test_the_seeded_rosters_and_generators_are_gone():
    """Negative-verified 2026-10-25: re-adding `_BP_USERS = []` fails this."""
    removed = {"_BP_USERS", "_HAMBURGONE_USERS", "_NORDLB_USERS", "_BREMENTHREE_USERS", "_COMPANY_USERS",
               "_COMPANY_PROJECT_IDS", "GEX_PROJECTS", "_COMPANY_DISPLAY_NAMES", "_DEMO_BARRIERS",
               "_DEMO_RESIDENCY_POLICIES", "_gen_access_events", "SEED_PROVENANCE"}
    tree, names, literals = ast.parse(SOURCE.read_text()), set(), set()
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            literals.add(node.value)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    assert not names & removed, f"seeded CISO data is back: {sorted(names & removed)}"
    assert not any("bp_global_energy" in v for v in literals), "the demo default company is back"


def test_the_ciso_screens_carry_no_sample_companies_or_fallbacks():
    """Negative-verified 2026-10-25: restoring `const GEX_COMPANIES = [` fails this."""
    screens = Path(__file__).resolve().parents[2] / "frontend" / "src" / "features" / "ciso"
    forbidden = ("bp_global_energy", "BP Global Energy", "GEX_COMPANIES", "COMPANY_REGISTRY", "demoOverview",
                 "demoUsers", "demoBarriers", "demoResidency", "demoCommitments", "optimistic update anyway",
                 "overall_score ?? 74", "NDA_PARTNERS", "gex_ciso_guest_policy")
    hits = [(f.name, word) for f in screens.glob("*.tsx") for word in forbidden if word in f.read_text()]
    assert not hits, f"sample CISO data is back in the screens: {hits}"
