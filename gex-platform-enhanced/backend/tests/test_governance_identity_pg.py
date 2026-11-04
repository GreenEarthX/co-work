"""
Approvals (WAE) and commitments (CSS) act as the SIGNED-IN account, in its
tenant (2026-10-25). Before: the approver and the signer came from the
x-demo-user header or the request body, so anyone could approve or sign in
anyone's name; the initiator could approve their own request, and twice; and
the pending list and commitment records were readable by any caller for any
company. Also: residency had built-in policies for two sample companies.

Throwaway PostgreSQL database (conftest.pg_store). The caller's payload is bound
the way ABACMiddleware binds it, on request.state.user_payload.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pg_support import connect_dsn

A, B = "test_gov_a", "test_gov_b"
PID = "proj_TEST_governance_identity"
USERS = {"u_gov_a1": A, "u_gov_a2": A, "u_gov_b1": B}


def _h(user_id: str) -> dict:
    return {"x-test-payload": json.dumps({"user_id": user_id, "company_id": USERS[user_id]})}


@pytest.fixture(scope="module")
def client(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (A, B):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                "VALUES (%s, 'TEST governance plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (PID, A))
    for uid, company in USERS.items():
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST-not-a-hash', %s, %s, "
                    "'PRODUCER', 'EXECUTIVE', %s, 'ACTIVE') ON CONFLICT DO NOTHING",
                    (uid, f"{uid}@test.invalid", company, f"TEST {company}", f"TEST {uid}"))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_approvals, routes_commitments

    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(routes_approvals.router, prefix="/api/v1/approvals")
    app.include_router(routes_commitments.router, prefix="/api/v1/commitments")
    from app.db import session

    saved = session._sync_engine   # projects_store reads through a cached engine
    session._sync_engine = None
    try:
        yield TestClient(app)
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved


@pytest.fixture(scope="module")
def pending(client):
    r = client.post("/api/v1/approvals/evaluate", headers=_h("u_gov_a1"),
                    json={"action_type": "PPA_EXECUTION", "project_id": PID,
                          "initiator_user_id": "someone_else"})   # ignored: the token decides
    assert r.status_code == 200 and r.json()["outcome"] == "PENDING_APPROVAL", r.text
    return r.json()["request_id"]


def test_no_token_is_refused(client):
    assert client.get("/api/v1/approvals/pending").status_code == 401
    assert client.post("/api/v1/approvals/evaluate", json={"action_type": "PPA_EXECUTION", "project_id": PID},
                       headers={"x-demo-user": "u_gov_a2"}).status_code == 401


def test_the_initiator_is_the_signed_in_account(client, pending):
    req = client.get(f"/api/v1/approvals/{pending}", headers=_h("u_gov_a2")).json()
    assert req["initiator_user_id"] == "u_gov_a1"


def test_another_company_neither_sees_nor_raises(client, pending):
    assert pending not in [i["id"] for i in client.get("/api/v1/approvals/pending", headers=_h("u_gov_b1")).json()["items"]]
    assert client.get(f"/api/v1/approvals/{pending}", headers=_h("u_gov_b1")).status_code == 404
    assert client.post(f"/api/v1/approvals/{pending}/decide", headers=_h("u_gov_b1"),
                       json={"decision": "APPROVE"}).status_code == 404
    r = client.post("/api/v1/approvals/evaluate", headers=_h("u_gov_b1"),
                    json={"action_type": "PPA_EXECUTION", "project_id": PID})
    assert r.status_code == 403


def test_four_eyes_no_self_approval_and_no_double_count(client, pending):
    own = client.post(f"/api/v1/approvals/{pending}/decide", headers=_h("u_gov_a1"), json={"decision": "APPROVE"})
    assert own.status_code == 403 and own.json()["detail"]["code"] == "SOD_SELF_APPROVAL"
    first = client.post(f"/api/v1/approvals/{pending}/decide", headers=_h("u_gov_a2"), json={"decision": "APPROVE"})
    assert first.status_code == 200 and first.json()["approvals_received"] == 1
    again = client.post(f"/api/v1/approvals/{pending}/decide", headers=_h("u_gov_a2"), json={"decision": "APPROVE"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_DECIDED"


def test_a_commitment_is_signed_by_the_token_and_read_in_its_tenant(client):
    r = client.post("/api/v1/commitments/sign", headers=_h("u_gov_a1"),
                    json={"action_type": "PPA_EXECUTION", "project_id": PID, "payload": {"mwh": 1},
                          "initiator_user_id": "u_gov_b1", "initiator_company_id": B})   # ignored
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["initiator_user_id"], body["initiator_company_id"]) == ("u_gov_a1", A)
    cid = body["commitment_id"]
    assert [c["commitment_id"] for c in
            client.get(f"/api/v1/commitments/project/{PID}", headers=_h("u_gov_a2")).json()["commitments"]] == [cid]
    assert client.get(f"/api/v1/commitments/project/{PID}", headers=_h("u_gov_b1")).json()["commitments"] == []
    assert client.get(f"/api/v1/commitments/{cid}", headers=_h("u_gov_b1")).status_code == 404
    same = client.post(f"/api/v1/commitments/{cid}/countersign", headers=_h("u_gov_a2"))
    assert same.status_code == 403 and same.json()["detail"]["code"] == "SAME_COMPANY"


def test_signing_on_a_project_the_company_cannot_see_is_refused(client):
    r = client.post("/api/v1/commitments/sign", headers=_h("u_gov_b1"),
                    json={"action_type": "PPA_EXECUTION", "project_id": PID, "payload": {}})
    assert r.status_code == 403


def test_an_unapproved_request_does_not_cover_a_signature(client, pending):
    r = client.post("/api/v1/commitments/sign", headers=_h("u_gov_a1"),
                    json={"action_type": "PPA_EXECUTION", "project_id": PID, "payload": {},
                          "approval_request_id": pending})
    assert r.status_code == 409   # one approval of two: still PENDING


def test_residency_has_no_sample_company_policies():
    from app.core import drpl

    assert not hasattr(drpl, "DEFAULT_POLICIES")
    audit = drpl.get_residency_audit("test_gov_nobody")
    assert audit["storage_checked"] is False
    assert {c["status"] for c in audit["categories"].values()} == {"NOT_CHECKED"}
    assert audit["categories"]["PERSONAL"]["required_jurisdiction"] is None
    assert audit["categories"]["AUDIT_LOG"]["required_jurisdiction"] == "EU"
