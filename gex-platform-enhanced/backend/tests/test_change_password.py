"""
POST /auth/change-password — the owner changes their own password (JML,
2026-11-03), and GET /auth/password-status says whether a temporary password
chosen by GEX is still in force.

Before this, the route existed with no caller and no test: a password the policy
refused raised PasswordPolicyError out of the handler (a bare 500), the same
password could be "changed" to itself, every other session survived the change,
and nothing reached the ledger.

PostgreSQL only (JML, 2026-11-03): runs in the throwaway PostgreSQL database
(conftest.pg_store), built by the migrations, never the SQLite file. Each test
uses its own account: the database is shared by modules.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OLD = "an old sentence nobody would guess"
NEW = "orange kettle under a quiet bridge"


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.core import auth
    from app.core.db_backend import eventstore_is_postgres, is_postgres

    assert is_postgres() and eventstore_is_postgres()
    conn = auth.auth_db_connection()
    for n in range(1, 8):
        uid = f"u_test_pw_{n}"
        conn.execute(
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
            "business_function, user_name, account_state, is_active, is_platform_admin) "
            "VALUES (?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT (user_id) DO NOTHING",
            (uid, f"{uid}@test.invalid", auth.pwd_context.hash(OLD), "test_pw_co", "TEST Pw Co",
             "PRODUCER", "EXECUTIVE", f"TEST Person {n}", "ACTIVE", 1 if n == 7 else 0))
    conn.commit()
    conn.close()


@pytest.fixture
def client() -> TestClient:
    from app.api.v1.routes_auth import router

    api = FastAPI()
    api.include_router(router, prefix="/api/v1")
    return TestClient(api)


def _bearer(n: int) -> dict:
    from app.core.auth import create_access_token, get_user_payload_by_email

    token, _ = create_access_token(get_user_payload_by_email(f"u_test_pw_{n}@test.invalid"))
    return {"authorization": f"Bearer {token}"}


def _change(client, n, current, new):
    return client.post("/api/v1/auth/change-password", headers=_bearer(n),
                       json={"current_password": current, "new_password": new})


def _signs_in(n: int, password: str) -> bool:
    from app.core.auth import authenticate_user

    return authenticate_user(f"u_test_pw_{n}@test.invalid", password) is not None


def test_no_bearer_is_refused(client):
    assert client.post("/api/v1/auth/change-password",
                       json={"current_password": OLD, "new_password": NEW}).status_code == 401
    assert client.get("/api/v1/auth/password-status").status_code == 401


def test_the_wrong_current_password_changes_nothing(client):
    assert _change(client, 1, "not the password at all", NEW).status_code == 400
    assert _signs_in(1, OLD) and not _signs_in(1, NEW)


def test_the_same_password_is_not_a_change(client):
    r = _change(client, 2, OLD, OLD)
    assert r.status_code == 422 and "differ" in r.json()["detail"]


def test_a_password_the_policy_refuses_is_a_422_with_its_reason(client):
    r = _change(client, 3, OLD, "short")
    assert r.status_code == 422 and "12" in r.json()["detail"]
    assert _signs_in(3, OLD)


def test_a_change_signs_out_every_other_session_and_keeps_this_one(client):
    from app.core.refresh_tokens import issue_refresh_token, rotate_refresh_token

    other_session = issue_refresh_token("u_test_pw_4")[0]
    r = _change(client, 4, OLD, NEW)
    assert r.status_code == 200
    assert _signs_in(4, NEW) and not _signs_in(4, OLD)
    assert rotate_refresh_token(other_session) is None, "another session survived the change"
    assert rotate_refresh_token(r.json()["refresh_token"]) is not None, "this session lost its refresh token"


def test_the_change_is_in_the_ledger(client):
    from app.core.event_store import get_events

    assert _change(client, 5, OLD, NEW).status_code == 200
    kinds = [e["event_type"] for e in get_events(aggregate_type="account", aggregate_id="u_test_pw_5", limit=None)]
    assert "account.password_changed" in kinds


def test_a_temporary_password_reads_in_force_until_its_owner_changes_it(client):
    from app.core.event_store import append_event

    def temporary():
        return client.get("/api/v1/auth/password-status", headers=_bearer(6)).json()["temporary"]

    assert temporary() is False
    append_event(event_type="account.temporary_password_set", aggregate_type="account",
                 aggregate_id="u_test_pw_6", data={"chosen_by": "GEX"}, user_id="TEST")
    assert temporary() is True
    assert _change(client, 6, OLD, NEW).status_code == 200
    assert temporary() is False


def test_the_status_states_the_longer_minimum_for_gex_staff(client):
    assert client.get("/api/v1/auth/password-status", headers=_bearer(7)).json()["policy"]["min_length"] == 16
    assert client.get("/api/v1/auth/password-status", headers=_bearer(1)).json()["policy"]["min_length"] == 12


def test_it_refuses_rather_than_write_the_sqlite_file(client, monkeypatch):
    from app.core.db_backend import PostgresRequired

    headers = _bearer(1)   # signed in while the store is PostgreSQL
    monkeypatch.setenv("AUTH_DB_BACKEND", "sqlite")
    with pytest.raises(PostgresRequired):
        client.post("/api/v1/auth/change-password", headers=headers,
                    json={"current_password": OLD, "new_password": NEW})
    with pytest.raises(PostgresRequired):
        client.get("/api/v1/auth/password-status", headers={"authorization": "Bearer x"})
