"""
POST /auth/refresh — the account comes from the auth slice's own store, under the
sign-in vetting rule (found 2026-10-21).

The route used to open the SQLite file directly and check only `is_active`. With
AUTH_DB_BACKEND=postgres that copy had frozen: 19 accounts against 23 in
PostgreSQL, all marked active. Newer accounts could not refresh, and an account
suspended in PostgreSQL kept renewing its session from the stale row.

In this throwaway store the SQLite file IS the auth store, so the wrong-store half
is pinned structurally (no sqlite3 in the route, by AST) and the vetting half by
data: a SUSPENDED account whose legacy is_active flag still says 1.
"""
from __future__ import annotations

import ast
import inspect
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings

ACCOUNTS = {   # user_id -> account_state; is_active stays 1 for all, as in the stale copy
    "u_TEST_refresh_active": "ACTIVE",
    "u_TEST_refresh_suspended": "SUSPENDED",
    "u_TEST_refresh_pending": "PENDING",
}


@pytest.fixture(scope="module", autouse=True)
def _store(isolated_store):
    from app.core import auth
    from app.core.db_backend import is_postgres
    from app.core.refresh_tokens import ensure_refresh_token_table

    assert settings.SQLITE_DB_PATH == isolated_store and not is_postgres()
    conn = auth.auth_db_connection()
    auth._ensure_tables(conn)
    for uid, state in ACCOUNTS.items():
        conn.execute(
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
            "business_function, user_name, account_state, is_active) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (uid, f"{uid}@test.invalid", "TEST-not-a-hash", "test_refresh_co", "TEST Refresh Co",
             "PRODUCER", "EXECUTIVE", f"TEST {uid}", state))
    conn.commit()
    conn.close()
    ensure_refresh_token_table()


@pytest.fixture
def client() -> TestClient:
    from app.api.v1.routes_auth import router

    api = FastAPI()
    api.include_router(router, prefix="/api/v1")   # the router carries /auth itself
    return TestClient(api)


def _issue(uid: str) -> str:
    from app.core.refresh_tokens import issue_refresh_token

    return issue_refresh_token(uid)[0]


def _refresh(client, token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def _claims(response) -> dict:
    from app.core.auth import decode_access_token

    return decode_access_token(response.json()["access_token"])


def test_an_active_account_renews_its_session(client):
    r = _refresh(client, _issue("u_TEST_refresh_active"))
    assert r.status_code == 200, r.text
    assert _claims(r)["sub"] == "u_TEST_refresh_active"
    assert _refresh(client, r.json()["refresh_token"]).status_code == 200   # the rotated token works


@pytest.mark.parametrize("uid,state", [("u_TEST_refresh_suspended", "SUSPENDED"),
                                       ("u_TEST_refresh_pending", "PENDING")])
def test_an_account_that_may_not_sign_in_may_not_renew_either(client, uid, state):
    spare = _issue(uid)                              # a second session the account holds
    r = _refresh(client, _issue(uid))
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["account_state"] == state
    assert _refresh(client, spare).status_code == 401    # every refresh token revoked with it


def test_an_unknown_account_cannot_renew(client):
    assert _refresh(client, _issue("u_TEST_refresh_nobody")).status_code == 401


def test_a_renewed_session_carries_roles_granted_since_sign_in(client):
    """A reviewer appointed after sign-in gets the appointment at the next refresh."""
    from app.core.auth import auth_db_connection

    uid, pid = "u_TEST_refresh_active", "proj_TEST_refresh"
    conn = auth_db_connection()
    conn.execute("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES (?,?,?)",
                 (uid, pid, "INDEPENDENT_ENGINEER"))
    conn.execute("UPDATE auth_users SET assigned_audits_json = ? WHERE user_id = ?", (json.dumps([pid]), uid))
    conn.commit()
    conn.close()
    claims = _claims(_refresh(client, _issue(uid)))
    assert claims["actor_type_per_project"][pid] == ["INDEPENDENT_ENGINEER"]
    assert pid in claims["assigned_audits"]


def test_the_refresh_route_opens_no_database_of_its_own():
    """The account store is auth's (auth_db_connection / load_user_for_refresh). A raw
    sqlite3 connection here is exactly the defect: it reads whatever SQLite file is
    configured, whichever store the auth slice actually uses."""
    from app.api.v1 import routes_auth

    tree = ast.parse(inspect.getsource(routes_auth.refresh_token))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "sqlite3" not in names | consts and "SQLITE_DB_PATH" not in attrs
