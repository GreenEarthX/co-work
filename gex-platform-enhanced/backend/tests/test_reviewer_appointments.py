"""
Reviewer appointments (JML, 2026-10-21): GEX staff appoint, on the instruction of
a named party. core/reviewer_appointments.py has the policy.

Before this, only the account seeding in core/auth.py wrote reviewer assignments,
so no reviewer could be appointed and no evidence verified on any project. The
last test here is the one that matters: an appointment makes a verification
possible, and a revocation takes it away again — through the REAL ABAC middleware
and the REAL bankability router.

Throwaway SQLite store (isolated_store). The PostgreSQL half — the project_access
row and RLS — is in test_reviewer_appointments_pg.py.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_bankability_proxy as proxy
from app.api.v1 import routes_reviewer_appointments as routes
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings

PID = "proj_TEST_appointments"
OWNER = "TEST Appoint Producer"
SHA = "a" * 64
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST appointments",
                                   owner_company_name=OWNER, associated_company_names=("TEST Appoint Bank",),
                                   jurisdiction="DE")

# user_id -> (company_id, company_name, state, platform admin)
ACCOUNTS = {
    "u_staff": ("greenearthx", "GreenEarthX", "ACTIVE", 1),
    "u_staff2": ("greenearthx", "GreenEarthX", "ACTIVE", 1),
    "u_gex_analyst": ("greenearthx", "GreenEarthX", "ACTIVE", 0),
    "u_grant": ("test_appoint_grant_body", "TEST Appoint Grant Body", "ACTIVE", 0),
    "u_ie": ("test_appoint_engineers", "TEST Appoint Engineers", "ACTIVE", 0),
    "u_ie2": ("test_appoint_engineers", "TEST Appoint Engineers", "ACTIVE", 0),
    "u_owner_emp": (reg.company_slug(OWNER), OWNER, "ACTIVE", 0),
    "u_pending": ("test_appoint_newcomer", "TEST Appoint Newcomer", "PENDING", 0),
    "u_bank": ("test_appoint_bank", "TEST Appoint Bank", "ACTIVE", 0),
    "u_stranger": ("test_appoint_stranger", "TEST Appoint Stranger", "ACTIVE", 0),
}
PRODUCER_TOKEN: dict[str, str] = {}


@pytest.fixture(scope="module", autouse=True)
def _store(isolated_store, tmp_path_factory):
    from app.core import auth, event_store
    from app.core.db_backend import evidence_is_postgres, is_postgres

    # Guard, not a formality: every write below must land in the throwaway file.
    assert settings.SQLITE_DB_PATH == isolated_store and not is_postgres() and not evidence_is_postgres()
    conn = auth.auth_db_connection()
    auth._ensure_tables(conn)
    for uid, (cid, cname, state, admin) in ACCOUNTS.items():
        conn.execute(
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
            "business_function, user_name, is_platform_admin, account_state) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (uid, f"{uid}@test.invalid", "TEST-not-a-hash", cid, cname, "THIRD_PARTY", "EXECUTIVE",
             f"TEST {uid}", admin, state))
    conn.commit()
    conn.close()
    event_store.init_event_store()
    pconn = proxy._get_db()
    proxy._ensure_tables(pconn)
    pconn.close()
    docs = tmp_path_factory.mktemp("evidence_docs")
    original = proxy.EVIDENCE_DOCS_DIR
    proxy.EVIDENCE_DOCS_DIR = str(docs)
    PRODUCER_TOKEN["t"] = create_access_token({
        "user_id": "u_prod", "email": "u_prod@test.invalid", "company_id": reg.company_slug(OWNER),
        "company_name": OWNER, "company_type": "PRODUCER", "service_type": None,
        "business_function": "EXECUTIVE", "user_name": "TEST u_prod", "clearance_level": "STANDARD",
        "jurisdiction": "DE", "kyc_status": "VERIFIED", "nda_signed_with": [], "assigned_audits": [],
        "actor_type_per_project": {PID: ["PRODUCER"]}})[0]
    yield
    proxy.EVIDENCE_DOCS_DIR = original


def _token(uid: str) -> str:
    """A token built from the STORE, as sign-in builds it — so an appointment shows."""
    from app.core.auth import get_user_payload_by_email

    payload = get_user_payload_by_email(f"{uid}@test.invalid")
    return create_access_token(payload)[0]


def _auth(uid: str) -> dict:
    return {"Authorization": f"Bearer {PRODUCER_TOKEN['t'] if uid == 'u_prod' else _token(uid)}"}


async def _engine(path, method="GET", json_data=None):
    detail = [{"key": e["key"], "status": e["status"]} for e in (json_data or {}).get("evidence", [])]
    return {"current_state": "SPECULATIVE", "gate_evaluations": [{"gate_id": "G_TEST", "evidence_detail": detail}]}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    for mod in (mw, reg, routes):
        monkeypatch.setattr(mod, "get_project_profile", profile)
    monkeypatch.setattr(proxy, "_call_engine", _engine)
    monkeypatch.setattr(proxy, "_project_owner", lambda pid: reg.company_slug(OWNER) if pid == PID else None)
    monkeypatch.setattr(proxy, "_physical_payload", lambda pid: {
        "power_model": "GRID_CONNECTED", "project_phase": "FEED", "financing_model": "PROJECT_FINANCE"})
    monkeypatch.setattr(proxy, "_account_directory", lambda ids: {
        u: {"name": f"TEST {u}", "business_function": "EXECUTIVE", "account_state": "ACTIVE",
            "company_id": reg.company_slug(OWNER) if u == "u_prod" else ACCOUNTS.get(u, ("x",))[0]}
        for u in ids})
    api = FastAPI()
    api.include_router(routes.router, prefix="/api/v1/projects")
    api.include_router(proxy.router, prefix="/api/v1/bankability")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api)


def _appoint(client, by, user_id, role, instructed_by="TEST Appoint Grant Body", sha=SHA):
    return client.post(f"/api/v1/projects/{PID}/reviewers", headers=_auth(by),
                       json={"user_id": user_id, "role": role, "instructed_by": instructed_by,
                             "instruction_sha256": sha})


def _revoke(client, by, user_id, role, reason="TEST engagement ended"):
    return client.request("DELETE", f"/api/v1/projects/{PID}/reviewers/{user_id}", params={"role": role},
                          headers=_auth(by), json={"reason": reason})


def _code(r) -> str:
    return r.json()["detail"]["code"]


def _row(uid: str) -> tuple[list, list]:
    from app.core.auth import auth_db_connection

    conn = auth_db_connection()
    audits = json.loads(conn.execute("SELECT assigned_audits_json FROM auth_users WHERE user_id = ?",
                                     (uid,)).fetchone()[0])
    roles = [r[0] for r in conn.execute("SELECT actor_type FROM auth_user_project_roles "
                                        "WHERE user_id = ? AND project_id = ?", (uid, PID)).fetchall()]
    conn.close()
    return audits, roles


# ── Who may appoint ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("by", ["u_owner_emp", "u_bank", "u_ie", "u_gex_analyst"])
def test_only_gex_staff_appoint(client, by):
    r = _appoint(client, by, "u_grant", "GRANT_ASSESSOR")
    assert r.status_code == 403 and _code(r) == "GEX_STAFF_ONLY"
    assert _row("u_grant") == ([], [])


def test_only_gex_staff_revoke(client):
    assert _revoke(client, "u_owner_emp", "u_grant", "GRANT_ASSESSOR").status_code == 403


# ── What an appointment must carry ──────────────────────────────────────────

@pytest.mark.parametrize("role,instructed_by,sha,code", [
    ("PRODUCER", "TEST Appoint Grant Body", SHA, "NOT_A_REVIEWER_ROLE"),
    ("COMMERCIAL_BANKER", "TEST Appoint Grant Body", SHA, "NOT_A_REVIEWER_ROLE"),
    ("GRANT_ASSESSOR", "  ", SHA, "INSTRUCTING_PARTY_REQUIRED"),
    ("GRANT_ASSESSOR", "TEST Appoint Grant Body", "", "INSTRUCTION_DOCUMENT_REQUIRED"),
    ("GRANT_ASSESSOR", "TEST Appoint Grant Body", "not-a-hash", "INSTRUCTION_DOCUMENT_REQUIRED"),
])
def test_an_appointment_names_a_reviewer_role_its_instructor_and_the_document(client, role, instructed_by, sha, code):
    r = _appoint(client, "u_staff", "u_grant", role, instructed_by=instructed_by, sha=sha)
    assert r.status_code == 422 and _code(r) == code


# ── Who may be appointed ────────────────────────────────────────────────────

@pytest.mark.parametrize("user_id,status,code", [
    ("u_owner_emp", 403, "OWNER_CANNOT_REVIEW"),       # the owner never verifies its own evidence
    ("u_gex_analyst", 403, "GEX_VERIFIES_NOTHING"),    # nor does GEX
    ("u_staff2", 403, "GEX_VERIFIES_NOTHING"),
    ("u_staff", 403, "CANNOT_APPOINT_YOURSELF"),
    ("u_pending", 409, "APPOINTEE_NOT_ACTIVE"),        # vetted accounts only
    ("u_nobody", 404, "APPOINTEE_NOT_FOUND"),
])
def test_who_cannot_be_appointed(client, user_id, status, code):
    r = _appoint(client, "u_staff", user_id, "INDEPENDENT_ENGINEER")
    assert r.status_code == status and _code(r) == code


def test_the_owner_cannot_choose_its_own_verifier(client):
    r = _appoint(client, "u_staff", "u_ie", "INDEPENDENT_ENGINEER", instructed_by=OWNER)
    assert r.status_code == 403 and _code(r) == "OWNER_CANNOT_INSTRUCT"
    assert _row("u_ie") == ([], [])


def test_an_unknown_project_is_refused(client):
    r = client.post("/api/v1/projects/proj_TEST_nowhere/reviewers", headers=_auth("u_staff"),
                    json={"user_id": "u_ie", "role": "INDEPENDENT_ENGINEER",
                          "instructed_by": "TEST Appoint Bank", "instruction_sha256": SHA})
    assert r.status_code == 404


# ── An appointment, listed and audited ──────────────────────────────────────

def test_staff_appoint_and_the_appointment_is_listed_and_audited(client):
    from app.core.event_store import get_entity_history

    r = _appoint(client, "u_staff", "u_ie", "INDEPENDENT_ENGINEER", instructed_by="TEST Appoint Bank")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gates"] == ["G0", "G1", "G3", "G5", "G6", "G11"]
    assert body["effective"] == "at the reviewer's next sign-in"
    assert _row("u_ie") == ([PID], ["INDEPENDENT_ENGINEER"])
    assert _appoint(client, "u_staff", "u_ie", "INDEPENDENT_ENGINEER").status_code == 409   # once

    events = get_entity_history("reviewer_appointment", f"{PID}:u_ie:INDEPENDENT_ENGINEER")
    assert len(events) == 1
    ev = json.dumps(events[0], default=str)
    assert "REVIEWER_APPOINTED" in ev and "u_staff" in ev and "TEST Appoint Bank" in ev and SHA in ev

    for viewer in ("u_staff", "u_owner_emp", "u_bank", "u_ie"):   # staff, owner, stakeholder, the reviewer
        listed = client.get(f"/api/v1/projects/{PID}/reviewers", headers=_auth(viewer))
        assert listed.status_code == 200, viewer
        assert [(x["user_id"], x["role"]) for x in listed.json()["reviewers"]] == [("u_ie", "INDEPENDENT_ENGINEER")]
    assert client.get(f"/api/v1/projects/{PID}/reviewers", headers=_auth("u_stranger")).status_code == 403


def test_revoking_one_of_two_roles_keeps_the_assignment(client):
    assert _appoint(client, "u_staff", "u_ie", "CERTIFIER", instructed_by="TEST Appoint Bank").status_code == 200
    r = _revoke(client, "u_staff", "u_ie", "CERTIFIER")
    assert r.status_code == 200 and r.json()["still_assigned"] is True
    assert _row("u_ie") == ([PID], ["INDEPENDENT_ENGINEER"])
    assert _revoke(client, "u_staff", "u_ie", "CERTIFIER").status_code == 404   # nothing left to revoke


def test_an_appointment_that_cannot_be_recorded_is_undone(client, monkeypatch):
    def broken_ledger(**_):
        raise RuntimeError("TEST ledger down")

    monkeypatch.setattr(routes, "append_event", broken_ledger)
    r = _appoint(client, "u_staff", "u_ie2", "LENDERS_ADVISER", instructed_by="TEST Appoint Bank")
    assert r.status_code == 500 and _code(r) == "APPOINTMENT_NOT_RECORDED"
    assert _row("u_ie2") == ([], [])


def test_a_revocation_needs_a_reason(client):
    r = client.request("DELETE", f"/api/v1/projects/{PID}/reviewers/u_ie", params={"role": "INDEPENDENT_ENGINEER"},
                       headers=_auth("u_staff"), json={"reason": ""})
    assert r.status_code == 422


# ── The point: appointed means able to verify; revoked means not ────────────

def _submit_and_verify(client, reviewer: str, key: str):
    up = client.post("/api/v1/bankability/evidence/document", data={"project_id": PID, "evidence_key": key},
                     files={"file": ("TEST.pdf", f"TEST {key}".encode(), "application/pdf")},
                     headers=_auth("u_prod"))
    assert up.status_code == 200, up.text
    return client.post("/api/v1/bankability/evidence", headers=_auth(reviewer), json={
        "project_id": PID, "evidence_key": key, "new_status": "VERIFIED",
        "document_sha256": up.json()["sha256"]})


def test_an_appointment_makes_verification_possible_and_a_revocation_ends_it(client):
    key = "site_technical_suitability"                          # G0, the grant assessor's gate
    before = _submit_and_verify(client, "u_grant", key)
    assert before.status_code == 403, before.text                # not appointed: a stranger

    assert _appoint(client, "u_staff", "u_grant", "GRANT_ASSESSOR").status_code == 200
    during = _submit_and_verify(client, "u_grant", key)
    assert during.status_code == 200, during.text
    assert _appoint(client, "u_staff", "u_grant", "GRANT_ASSESSOR").status_code == 409

    outside = _submit_and_verify(client, "u_grant", "technology_maturity_dossier")   # G1: not its gate
    assert outside.status_code == 403

    assert _revoke(client, "u_staff", "u_grant", "GRANT_ASSESSOR").status_code == 200
    assert _row("u_grant") == ([], [])
    after = _submit_and_verify(client, "u_grant", "stakeholder_map_v1")          # G0 again
    assert after.status_code == 403
