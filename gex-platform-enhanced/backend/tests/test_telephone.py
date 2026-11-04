"""
An account's telephone number is a field its owner may change (JML, 2026-11-03;
alembic 081). Registration writes it; GET/PUT /auth/telephone read and change the
signed-in account's own number; each change is an account.telephone_changed
event that carries no numbers.

PostgreSQL only (JML, 2026-11-03): runs in the throwaway PostgreSQL database
(conftest.pg_store), never the SQLite file. Each test uses its own account.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.core import auth
    from app.core.db_backend import eventstore_is_postgres, is_postgres

    assert is_postgres() and eventstore_is_postgres()
    conn = auth.auth_db_connection()
    for n in range(1, 6):
        uid = f"u_test_tel_{n}"
        conn.execute(
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
            "business_function, user_name, account_state, is_active, telephone) VALUES (?,?,?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT (user_id) DO NOTHING",
            (uid, f"{uid}@test.invalid", "TEST-not-a-hash", "test_tel_co", "TEST Tel Co",
             "PRODUCER", "EXECUTIVE", f"TEST Person {n}", "ACTIVE", "+49 30 000000" if n == 4 else None))
    conn.commit()
    conn.close()


@pytest.fixture
def client() -> TestClient:
    from app.api.v1.routes_account_vetting import router as vetting
    from app.api.v1.routes_auth import router

    api = FastAPI()
    api.include_router(router, prefix="/api/v1")
    api.include_router(vetting, prefix="/api/v1/account")
    return TestClient(api)


def _bearer(n: int) -> dict:
    from app.core.auth import create_access_token, get_user_payload_by_email

    token, _ = create_access_token(get_user_payload_by_email(f"u_test_tel_{n}@test.invalid"))
    return {"authorization": f"Bearer {token}"}


def _stored(n: int):
    from app.core.auth import auth_db_connection

    conn = auth_db_connection()
    try:
        return conn.execute("SELECT telephone FROM auth_users WHERE user_id = ?", (f"u_test_tel_{n}",)).fetchone()["telephone"]
    finally:
        conn.close()


def _events(n: int) -> list[dict]:
    from app.core.event_store import get_events

    return [e for e in get_events(aggregate_type="account", aggregate_id=f"u_test_tel_{n}", limit=None)
            if e["event_type"] == "account.telephone_changed"]


def test_no_bearer_is_refused(client):
    assert client.get("/api/v1/auth/telephone").status_code == 401
    assert client.put("/api/v1/auth/telephone", json={"telephone": "+49 160 1234567"}).status_code == 401


def test_the_owner_sets_their_number_and_the_ledger_records_the_change_without_it(client):
    assert client.get("/api/v1/auth/telephone", headers=_bearer(1)).json() == {"telephone": None}
    r = client.put("/api/v1/auth/telephone", headers=_bearer(1), json={"telephone": "  +49 160   1234567 "})
    assert r.status_code == 200 and r.json() == {"telephone": "+49 160 1234567", "changed": True}
    assert _stored(1) == "+49 160 1234567"
    events = _events(1)
    assert len(events) == 1
    assert "1234567" not in json.dumps(events[0]), "the ledger must not carry the number"


@pytest.mark.parametrize("bad", ["call me", "12345", "+49 160 abc 1234", "+" + "1" * 45])
def test_something_that_is_not_a_number_is_refused_and_nothing_changes(client, bad):
    r = client.put("/api/v1/auth/telephone", headers=_bearer(2), json={"telephone": bad})
    assert r.status_code == 422
    assert _stored(2) is None and _events(2) == []


def test_the_same_number_again_is_not_a_change(client):
    r = client.put("/api/v1/auth/telephone", headers=_bearer(4), json={"telephone": "+49 30 000000"})
    assert r.json() == {"telephone": "+49 30 000000", "changed": False}
    assert _events(4) == []


def test_an_account_changes_its_own_number_only(client):
    client.put("/api/v1/auth/telephone", headers=_bearer(3), json={"telephone": "+33 1 23 45 67 89"})
    assert _stored(3) == "+33 1 23 45 67 89"
    assert _stored(4) == "+49 30 000000" and _stored(5) is None


def test_registration_writes_the_number_to_the_field(client):
    from app.core.auth import auth_db_connection

    r = client.post("/api/v1/account/register", json={
        "email": "u_test_tel_registered@test.invalid", "password": "orange kettle under a quiet bridge",
        "user_name": "TEST Registrant", "company_name": "TEST Tel Co", "company_type": "PRODUCER",
        "business_function": "EXECUTIVE", "telephone": " +49 160 97 000 000 "})
    assert r.status_code == 201
    conn = auth_db_connection()
    try:
        row = conn.execute("SELECT telephone, account_state FROM auth_users WHERE email = ?",
                           ("u_test_tel_registered@test.invalid",)).fetchone()
    finally:
        conn.close()
    assert row["telephone"] == "+49 160 97 000 000" and row["account_state"] == "PENDING"


def test_it_refuses_rather_than_write_the_sqlite_file(client, monkeypatch):
    from app.core.db_backend import PostgresRequired

    headers = _bearer(5)   # signed in while the store is PostgreSQL
    monkeypatch.setenv("AUTH_DB_BACKEND", "sqlite")
    with pytest.raises(PostgresRequired):
        client.put("/api/v1/auth/telephone", headers=headers, json={"telephone": "+49 160 1234567"})
    with pytest.raises(PostgresRequired):
        client.post("/api/v1/account/register", json={
            "email": "u_test_tel_sqlite@test.invalid", "password": "orange kettle under a quiet bridge",
            "user_name": "TEST Registrant", "company_name": "TEST Tel Co", "company_type": "PRODUCER",
            "business_function": "EXECUTIVE", "telephone": "+49 160 97 000 000"})
