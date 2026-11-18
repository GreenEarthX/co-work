"""
Demo-account seeding (JML, 2026-11-18, finding D).

Every backend start used to UPSERT the 17 demo accounts: the demo password,
roles, profile and `is_active=1` were written back over the stored rows, so a
changed password did not survive a restart and a disabled account came back.
The rule now:

- seeding is OFF unless `GEX_SEED_DEMO_USERS` is explicitly enabled;
- when on, it CREATES a missing demo account and leaves an existing one exactly
  as it is: password, roles, permissions, approval and disabled state;
- a production environment refuses to start with it enabled.

No database: an in-memory SQLite store built by the module's own DDL.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import app.core.auth as auth
import app.core.db_backend as dbb
from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
SEED = auth.DEMO_USER_SEEDS[0]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(dbb, "is_postgres", lambda: False)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    auth._ensure_tables(conn)
    yield conn
    conn.close()


def _row(conn, email):
    return dict(conn.execute("SELECT * FROM auth_users WHERE email = ?", (email.lower(),)).fetchone())


def _roles(conn, user_id):
    return sorted(tuple(r) for r in conn.execute(
        "SELECT project_id, actor_type FROM auth_user_project_roles WHERE user_id = ?", (user_id,)))


def test_seeding_is_off_unless_explicitly_enabled():
    assert Settings.model_fields["GEX_SEED_DEMO_USERS"].default is False


def test_a_missing_demo_account_is_created(store):
    assert auth._seed_user(store, SEED) is True
    row = _row(store, SEED["email"])
    assert auth.pwd_context.verify(auth.DEMO_PASSWORD, row["password_hash"])
    assert row["kyc_status"] == "SEED"


def test_an_existing_account_is_left_exactly_as_it_is(store):
    auth._seed_user(store, SEED)
    user_id = _row(store, SEED["email"])["user_id"]
    new_hash = auth.pwd_context.hash("a-changed-passphrase-2026")
    store.execute(
        "UPDATE auth_users SET password_hash = ?, is_active = 0, account_state = 'SUSPENDED', "
        "is_platform_admin = 0, clearance_level = 'RESTRICTED', user_name = 'Renamed' WHERE user_id = ?",
        (new_hash, user_id))
    store.execute("DELETE FROM auth_user_project_roles WHERE user_id = ?", (user_id,))
    store.execute("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES (?, 'P_X', 'BANK')",
                  (user_id,))
    before_row, before_roles = _row(store, SEED["email"]), _roles(store, user_id)

    assert auth._seed_user(store, SEED) is False                 # a second start
    assert _row(store, SEED["email"]) == before_row
    assert _roles(store, user_id) == before_roles == [("P_X", "BANK")]
    assert not auth.pwd_context.verify(auth.DEMO_PASSWORD, before_row["password_hash"])


def test_an_account_holding_the_seed_user_id_under_another_email_is_not_touched(store):
    auth._seed_user(store, SEED)
    user_id = _row(store, SEED["email"])["user_id"]
    store.execute("UPDATE auth_users SET email = 'moved@example.com' WHERE user_id = ?", (user_id,))
    before = _row(store, "moved@example.com")
    assert auth._seed_user(store, SEED) is False
    assert _row(store, "moved@example.com") == before
    assert store.execute("SELECT count(*) FROM auth_users").fetchone()[0] == 1


def test_startup_seeds_nothing_when_seeding_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "SEED_DEMO_USERS", False)
    monkeypatch.setattr(auth, "_seed_user", lambda conn, seed: calls.append(seed))

    class Conn:
        def execute(self, *a, **k):
            return self

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(auth, "_get_conn", lambda: Conn())
    monkeypatch.setattr(auth, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(auth, "_grandfather_pre_policy_accounts", lambda conn: None)
    auth.init_auth_db()
    assert calls == []


def _start_config(**env):
    base = {k: v for k, v in os.environ.items() if not k.startswith("GEX_SEED")}
    base.update(ENVIRONMENT="production", SECRET_KEY="not-the-dev-default-" + "x" * 32, GEX_DEMO_MODE="false", **env)
    return subprocess.run([sys.executable, "-c", "import app.core.config"], cwd=BACKEND, env=base,
                          capture_output=True, text=True)


def test_production_refuses_to_start_with_seeding_enabled():
    refused = _start_config(GEX_SEED_DEMO_USERS="true")
    assert refused.returncode != 0 and "GEX_SEED_DEMO_USERS" in refused.stderr
    assert _start_config().returncode == 0, _start_config().stderr
