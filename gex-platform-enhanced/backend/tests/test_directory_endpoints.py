"""
The staff directory must not leak what Supabase leaked.

`docs/supabase-cutover-endpoints.md` increment 1. The five tables behind the
Team screen answered anonymous requests under the bundled anon key — including
19 people's email and phone. So the interesting tests here are the refusals:
an anonymous caller gets nothing, and an authenticated caller who is not GEX
staff gets the org chart WITHOUT the personal columns.

The PII assertion is deliberately `not in`, not `is None`. A nulled key still
tells a reader the field exists and invites a UI to render "None" where a phone
number belongs; the rule is omission.

Uses `isolated_store`, so nothing touches the development database.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_directory
from app.core import directory_store

# The identity the test app binds to the request. `None` means anonymous.
_IDENTITY: dict[str, Any] = {"payload": None}

STAFF = {"user_id": "u_admin", "email": "staff@gex.example", "is_platform_admin": True}
MEMBER = {"user_id": "u_plain", "email": "plain@gex.example", "is_platform_admin": False}


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    directory_store.init_db()
    # Two teams out of alphabetical insertion order, so an ORDER BY that went
    # missing would show up as a failure rather than a coincidence.
    directory_store.upsert_team("T02", "T02 Structuring", "Capital", "finance")
    directory_store.upsert_team("T01", "T01 Origination", "Deals", "marketplace")
    directory_store.upsert_role("R02", "ORG-02", "Analyst", "STANDARD", False, "T01")
    directory_store.upsert_role("R01", "ORG-01", "Head of Origination",
                                "ELEVATED", True, "T01")
    directory_store.upsert_member(
        "M02", full_name="Zoe Ndiaye", email="zoe@gex.example",
        phone="+33 6 00 00 00 02", organisation="GEX", status="ACTIVE",
        primary_team_id="T01", primary_role_id="R02")
    directory_store.upsert_member(
        "M01", full_name="Adam Fournier", email="adam@gex.example",
        phone="+33 6 00 00 00 01", organisation=None, status="ACTIVE",
        primary_team_id="T02", primary_role_id="R01",
        secondary_team_id="T01", secondary_role_id="R02")
    directory_store.upsert_gate("G1", "NDA countersigned", "Before any data room")
    directory_store.set_gate_status("M01", "G1", "GRANTED")


@pytest.fixture()
def client() -> TestClient:
    api = FastAPI()

    @api.middleware("http")
    async def _bind_identity(request, call_next):
        payload = _IDENTITY["payload"]
        if payload is not None:
            request.state.auth_user_payload = payload
        return await call_next(request)

    api.include_router(routes_directory.router, prefix="/api/v1/directory")
    return TestClient(api)


@pytest.fixture(autouse=True)
def _anonymous_by_default():
    _IDENTITY["payload"] = None
    yield
    _IDENTITY["payload"] = None


def _as(identity: dict[str, Any]) -> None:
    _IDENTITY["payload"] = identity


ENDPOINTS = ("/api/v1/directory/overview",
             "/api/v1/directory/members",
             "/api/v1/directory/gate-status")


# ── refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ENDPOINTS)
def test_an_anonymous_caller_gets_nothing(client, path):
    """What Supabase answered. Every endpoint, not just the one with names."""
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ENDPOINTS)
def test_a_customers_user_cannot_read_the_internal_directory_at_all(client, path):
    """
    THE RULE: no user of a paying customer may read GEX's internal directory,
    in any instance — not the names, not the teams, not the gates.

    The first version of this router admitted any authenticated caller and
    withheld only the addresses. A live check found an ETFuels counterparty
    account reading GEX's entire org chart, which is what this replaces. Every
    endpoint refuses: a rule kept on one of three doors is not a rule.
    """
    _as(MEMBER)
    res = client.get(path)
    assert res.status_code == 403
    # Nothing leaks through the refusal body either.
    assert "Adam" not in res.text and "Zoe" not in res.text


def test_the_redaction_rule_survives_underneath_the_access_rule():
    """
    Defence in depth, pinned at the store because no HTTP path reaches it any
    more. If read access is ever widened — to a caller's own organisation,
    say — addresses must not come along by default.
    """
    redacted = directory_store.list_members(include_pii=False)
    assert [m["full_name"] for m in redacted] == ["Adam Fournier", "Zoe Ndiaye"]
    for m in redacted:
        assert "email" not in m, "email must be omitted, not nulled"
        assert "phone" not in m, "phone must be omitted, not nulled"
        assert m["primary_team_id"]  # the org chart itself still renders

    assert directory_store.list_members(include_pii=True)[0]["email"] == "adam@gex.example"


def test_gex_staff_see_the_personal_columns(client):
    _as(STAFF)
    members = {m["full_name"]: m for m in
               client.get("/api/v1/directory/members").json()}
    assert members["Adam Fournier"]["email"] == "adam@gex.example"
    assert members["Adam Fournier"]["phone"] == "+33 6 00 00 00 01"
    assert client.get("/api/v1/directory/overview").json()["personal_data_included"] is True


# ── the contract the frontend already expects ────────────────────────────────

def test_overview_answers_all_five_collections_in_one_call(client):
    _as(STAFF)
    body = client.get("/api/v1/directory/overview").json()
    for key in ("teams", "roles", "members", "gates", "gate_statuses"):
        assert body[key], f"{key} missing or empty"


def test_ordering_matches_what_the_hook_asked_postgrest_for(client):
    """teams by name, roles by role_code, members by full_name — the three
    `.order()` calls in useTeamData, now server-side."""
    _as(STAFF)
    body = client.get("/api/v1/directory/overview").json()
    assert [t["name"] for t in body["teams"]] == ["T01 Origination", "T02 Structuring"]
    assert [r["role_code"] for r in body["roles"]] == ["ORG-01", "ORG-02"]
    assert [m["full_name"] for m in body["members"]] == ["Adam Fournier", "Zoe Ndiaye"]


def test_the_row_shapes_are_the_frontend_interfaces(client):
    """TeamRow, RoleRow, TeamUserRow, PermissionGate, GateStatusRow. This
    increment changes transport, not shapes."""
    _as(STAFF)
    body = client.get("/api/v1/directory/overview").json()
    assert set(body["teams"][0]) == {"id", "name", "description", "primary_modules"}
    assert set(body["roles"][0]) == {"id", "role_code", "role_name",
                                     "permission_tier", "is_default_admin", "team_id"}
    assert set(body["gates"][0]) == {"id", "gate_name", "trigger_description"}
    assert set(body["gate_statuses"][0]) == {"user_id", "gate_id", "status"}
    assert set(body["members"][0]) == {
        "id", "full_name", "organisation", "status", "primary_team_id",
        "primary_role_id", "secondary_team_id", "secondary_role_id",
        "email", "phone"}


def test_is_default_admin_is_a_boolean_not_a_sqlite_integer(client):
    """`RoleRow.is_default_admin` is typed boolean; 0/1 would be truthy both ways."""
    _as(STAFF)
    roles = {r["role_code"]: r for r in client.get("/api/v1/directory/overview").json()["roles"]}
    assert roles["ORG-01"]["is_default_admin"] is True
    assert roles["ORG-02"]["is_default_admin"] is False


def test_gate_status_is_staff_only_because_it_maps_people_to_internal_gates(client):
    """No addresses in these rows, and they are still internal structure —
    which GEX person cleared which internal process gate."""
    _as(STAFF)
    rows = client.get("/api/v1/directory/gate-status").json()
    assert rows == [{"user_id": "M01", "gate_id": "G1", "status": "GRANTED"}]


# ── the store ────────────────────────────────────────────────────────────────

def test_the_store_never_creates_the_pii_tables_on_postgres(monkeypatch):
    """A PII table created by CREATE TABLE IF NOT EXISTS on PostgreSQL would
    carry no RLS policy — the mistake this module undoes.

    Until migration 047 this module refused outright. 047 creates the five
    tables WITH a policy, so refusing would only stop the app booting on a
    database that already has them. What must not change is who creates them:
    `init_db()` is a no-op on PostgreSQL and issues no DDL there. This test
    fails loudly if anyone reintroduces runtime DDL against PostgreSQL.
    """
    def _explode(*a, **kw):
        raise AssertionError(
            "init_db() opened a PostgreSQL connection — the directory schema "
            "belongs to migration 047, not to the runtime")

    monkeypatch.setattr(directory_store, "governance_is_postgres", lambda: True)
    monkeypatch.setattr(directory_store, "governance_connection", _explode)
    directory_store.init_db()


def test_reconciliation_measures_the_gap_between_directory_and_accounts():
    """The measurement the open identity decision needs: who is in the
    directory with no account, and who has an account but no directory row."""
    conn = sqlite3.connect(directory_store.settings.SQLITE_DB_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO auth_users (user_id, email, password_hash, "
            "company_id, company_name, company_type, business_function, user_name) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("auth_adam", "ADAM@gex.example", "x", "c1", "GEX", "PRODUCER",
             "EXECUTIVE", "Adam Fournier"))
        conn.execute(
            "INSERT OR REPLACE INTO auth_users (user_id, email, password_hash, "
            "company_id, company_name, company_type, business_function, user_name) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("auth_orphan", "nobody@gex.example", "x", "c1", "GEX", "PRODUCER",
             "ENGINEERING", "No Directory Row"))
        conn.commit()
    finally:
        conn.close()

    report = directory_store.reconcile_with_auth_users()
    # Matching is case-insensitive: ADAM@ in the account, adam@ in the directory.
    assert report["members_without_account"] == ["M02"]
    assert report["name_match_candidates"] == []
    assert "auth_orphan" in report["accounts_without_directory_entry"]
    assert "auth_adam" not in report["accounts_without_directory_entry"]

    conn = sqlite3.connect(directory_store.settings.SQLITE_DB_PATH)
    try:
        linked = conn.execute(
            "SELECT auth_user_id FROM directory_members WHERE member_id='M01'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert linked == "auth_adam"


def test_the_same_person_under_two_addresses_is_reported_but_never_linked():
    """The real case, found in the 2026-09-20 import: `felix@etfuels.com` in
    the directory is `felix.leworthy@etfuels.com` in auth_users. An email-only
    reconciliation would call that a gap. Auto-linking on the name would hand
    one person another's account, so it is reported for a human instead."""
    conn = sqlite3.connect(directory_store.settings.SQLITE_DB_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO auth_users (user_id, email, password_hash, "
            "company_id, company_name, company_type, business_function, user_name) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("auth_zoe", "zoe.ndiaye@gex.example", "x", "c1", "GEX", "PRODUCER",
             "COMMERCIAL", "  Zoe   Ndiaye "))  # sloppy whitespace on purpose
        conn.commit()
    finally:
        conn.close()

    report = directory_store.reconcile_with_auth_users()
    candidates = report["name_match_candidates"]
    assert [c["member_id"] for c in candidates] == ["M02"]
    assert candidates[0]["auth_user_id"] == "auth_zoe"
    assert candidates[0]["directory_email"] == "zoe@gex.example"

    # Reported — and still unlinked. The column stays NULL until a human says so.
    conn = sqlite3.connect(directory_store.settings.SQLITE_DB_PATH)
    try:
        linked = conn.execute(
            "SELECT auth_user_id FROM directory_members WHERE member_id='M02'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert linked is None
    assert "M02" in report["members_without_account"]


def test_the_directory_grants_nothing():
    """A directory is not an authority. Nothing in this store is consulted by
    ABAC, entitlements or the permission engine — if that ever changes, the
    dual-identity defect has grown a second head."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = [
        p for p in root.rglob("*.py")
        if "directory_store" in p.read_text(encoding="utf-8")
        and p.name not in {"directory_store.py", "routes_directory.py", "main.py"}
    ]
    assert offenders == [], f"directory_store consulted outside the directory: {offenders}"
