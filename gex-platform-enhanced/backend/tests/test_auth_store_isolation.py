"""
`isolated_store` must isolate the auth slice too.
=================================================
`tests/conftest.py` `isolated_store` repoints `settings.SQLITE_DB_PATH`. Until 2026-09-14
`app/core/auth.py` and `app/core/refresh_tokens.py` each captured
`DB_PATH = settings.SQLITE_DB_PATH` at import and called `auth_connection(DB_PATH)`, and an
explicit path beats `settings` — so the fixture never reached them. Every auth lookup ran
`init_auth_db()` (DDL, 17 seed upserts, commit), so a real lookup under the fixture wrote the
dev `gex_platform.db`. The reverse held too: a first import while the fixture was active
pinned the auth slice to a throwaway file for the rest of the process.

Measured before the fix (full suite, all-SQLite, 401 passed): 0 dev-database opens during
the 84 `isolated_store` tests. Latent, not exercised — the one auth-adjacent module stubs its
lookup. These tests exercise it.

The dev database is refused at `sqlite3.connect`, so a regression fails at the open, before
any statement runs: this file run against the old code does not write the dev database either.

Importing the slice writes nothing (2026-09-15). `auth.py` ended with a module-level
`init_auth_db()`, so every pytest process opened the dev database at collection, before any
fixture existed, and ran 41 write statements re-salting all 17 demo password hashes. Schema,
seeds and grandfathering are now one explicit step run by `app.main` at startup, and lookups
no longer re-run it.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.db_backend import is_postgres

APP = Path(__file__).resolve().parents[1] / "app"

sqlite_auth_only = pytest.mark.skipif(
    is_postgres(), reason="AUTH_DB_BACKEND=postgres: the auth slice has no SQLite path to isolate"
)


@pytest.fixture
def dev_db_opens(isolated_store, monkeypatch) -> list[str]:
    """Refuse, and record, any connection to the configured dev database."""
    # A fresh Settings reads env and .env as the app does. The shared singleton cannot say
    # where the dev database is — it is the very object isolated_store repoints.
    dev = os.path.realpath(type(settings)().SQLITE_DB_PATH)
    assert os.path.realpath(isolated_store) != dev
    real_connect = sqlite3.connect
    opened: list[str] = []

    def guarded(database, *args, **kwargs):
        if isinstance(database, (str, os.PathLike)) and os.path.realpath(os.fspath(database)) == dev:
            opened.append(dev)
            raise AssertionError(f"the dev database was opened under isolated_store: {dev}")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded)
    return opened


@sqlite_auth_only
@pytest.mark.parametrize("lookup", ["get_user_payload_by_email", "authenticate_user"])
def test_an_auth_lookup_under_isolated_store_leaves_the_dev_database_untouched(
    lookup, isolated_store, dev_db_opens
):
    from app.core import auth

    # Positive control: a user that exists ONLY in the isolated store. Finding it proves the
    # lookup ran there, so the test cannot pass by never touching a database. ACTIVE with
    # is_active=1, so authenticate_user admits it.
    email = f"isolation-{uuid.uuid4().hex[:8]}@example.com"
    conn = sqlite3.connect(isolated_store)
    try:
        conn.execute(
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name,"
            " company_type, business_function, user_name, account_state, is_active)"
            " VALUES (?, ?, ?, 'isolation_co', 'Isolation Co', 'PRODUCER', 'EXECUTIVE',"
            " 'Isolation Probe', 'ACTIVE', 1)",
            (email.split("@")[0], email, auth.pwd_context.hash("isolation-pw")),
        )
        conn.commit()
    finally:
        conn.close()

    if lookup == "authenticate_user":
        payload = auth.authenticate_user(email, "isolation-pw")
    else:
        payload = auth.get_user_payload_by_email(email)

    assert dev_db_opens == [], "an auth lookup under isolated_store opened the dev database"
    assert payload is not None and payload["email"] == email, (
        "the lookup did not find a user that exists only in the isolated store"
    )


@sqlite_auth_only
def test_refresh_tokens_under_isolated_store_leave_the_dev_database_untouched(
    isolated_store, dev_db_opens
):
    from app.core import refresh_tokens

    refresh_tokens.ensure_refresh_token_table()

    assert dev_db_opens == []
    conn = sqlite3.connect(isolated_store)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "refresh_tokens" in tables, "the refresh-token DDL did not reach the isolated store"


@sqlite_auth_only
@pytest.mark.parametrize("module", ["auth", "refresh_tokens"])
def test_the_auth_slice_resolves_its_store_at_call_time(
    module, isolated_store, dev_db_opens, tmp_path, monkeypatch
):
    """Both directions: a path frozen at import — dev or throwaway — fails one of the two."""
    mod = importlib.import_module(f"app.core.{module}")
    for target in (isolated_store, str(tmp_path / "elsewhere.db")):
        monkeypatch.setattr(settings, "SQLITE_DB_PATH", target)
        conn = mod._get_conn()
        try:
            opened = conn.execute("PRAGMA database_list").fetchone()[2]
        finally:
            conn.close()
        assert os.path.realpath(opened) == os.path.realpath(target), (
            f"app.core.{module} opened {opened} while settings pointed at {target}"
        )


def test_no_shim_accessor_is_handed_a_path_captured_at_import():
    """AST, not text: this file's docstring names the pattern it forbids."""
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        captured = {
            target.id
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
            and ast.unparse(node.value) == "settings.SQLITE_DB_PATH"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        if not captured:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            args = [*node.args, *(k.value for k in node.keywords)]
            if name.endswith("_connection") and any(
                isinstance(a, ast.Name) and a.id in captured for a in args
            ):
                offenders.append(f"{path.relative_to(APP.parent)}:{node.lineno} {ast.unparse(node)}")
    assert not offenders, (
        "a db_backend accessor is passed a path captured from settings at import, so "
        "isolated_store (and any runtime repoint) cannot reach it — call it with no path:\n"
        + "\n".join(offenders)
    )


# ── Seeding is a startup step, not an import or lookup side effect ───────────────────────

# Runs in a fresh interpreter: this process imported app.core.auth at collection.
_IMPORT_PROBE = r"""
import json, os, sqlite3, sys
from app.core import db_backend
from app.core.config import settings

assert "app.core.auth" not in sys.modules, "auth already imported: the probe would prove nothing"
dev = os.path.realpath(type(settings)().SQLITE_DB_PATH)
opened = []
real_auth_connection = db_backend.auth_connection
real_connect = sqlite3.connect

def guarded_connect(database, *args, **kwargs):
    if isinstance(database, (str, os.PathLike)) and os.path.realpath(os.fspath(database)) == dev:
        opened.append("sqlite3.connect(dev)")
        raise AssertionError("the dev database was opened")
    return real_connect(database, *args, **kwargs)

def guarded_auth_connection(*args, **kwargs):
    opened.append("auth_connection()")
    raise AssertionError("the auth store was opened")

sqlite3.connect = guarded_connect
db_backend.auth_connection = guarded_auth_connection
result = {"postgres": db_backend.is_postgres()}
try:
    import app.core.auth as auth
except AssertionError:
    auth = None
result["import"] = list(opened)
opened.clear()

# Positive controls: each guard catches the slice's own way of opening its store, so an empty
# import list means nothing was opened, not that nothing was watched. Neither lets a
# connection through.
if auth is not None:
    try:
        auth.init_auth_db()
    except AssertionError:
        pass
    result["init_auth_db"] = list(opened)
    opened.clear()
    db_backend.auth_connection = real_auth_connection
    if not result["postgres"]:
        try:
            auth._get_conn().close()
        except AssertionError:
            pass
        result["get_conn"] = list(opened)
print("PROBE " + json.dumps(result))
"""


def test_importing_auth_opens_no_connection_to_the_dev_database():
    run = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=APP.parent, capture_output=True, text=True, timeout=120,
    )
    line = next((l for l in run.stdout.splitlines() if l.startswith("PROBE ")), None)
    assert line, f"the import probe did not finish (exit {run.returncode}):\n{run.stderr[-3000:]}"
    result = json.loads(line.removeprefix("PROBE "))

    assert result["import"] == [], (
        f"importing app.core.auth opened its store {result['import']}: schema and seeds are an "
        "app-startup step (app.main), not an import side effect"
    )
    assert result["init_auth_db"] == ["auth_connection()"], (
        "control: the store guard did not see init_auth_db() open the store"
    )
    if not result["postgres"]:
        assert result["get_conn"] == ["sqlite3.connect(dev)"], (
            "control: the sqlite3.connect guard did not see the auth slice open the dev database"
        )


def _auth_rows(db_path: str) -> tuple[list, list]:
    conn = sqlite3.connect(db_path)
    try:
        return (
            conn.execute(
                "SELECT email, password_hash, account_state, updated_at FROM auth_users ORDER BY email"
            ).fetchall(),
            conn.execute(
                "SELECT user_id, project_id, actor_type FROM auth_user_project_roles ORDER BY 1, 2, 3"
            ).fetchall(),
        )
    finally:
        conn.close()


@sqlite_auth_only
def test_an_auth_lookup_does_not_reseed_the_store(isolated_store, dev_db_opens, monkeypatch):
    """Every login, x-demo-user request and vetting call re-ran init_auth_db(): 17 upserts with
    fresh salts, role rows deleted and reinserted — and a demo user's changed password was reset
    before its own check."""
    from app.core import auth

    monkeypatch.setattr(auth, "SEED_DEMO_USERS", True)  # so a re-seed cannot hide
    auth.init_auth_db()
    before = _auth_rows(isolated_store)
    seeded = auth.DEMO_USER_SEEDS[0]["email"]
    assert seeded in {row[0] for row in before[0]}, "control: init_auth_db() did not seed the store"

    assert auth.authenticate_user(seeded, auth.DEMO_PASSWORD) is not None
    assert auth.get_user_payload_by_email(seeded) is not None
    assert auth.get_user_payload_by_email(f"absent-{uuid.uuid4().hex[:8]}@example.com") is None
    auth.auth_db_connection().close()

    assert dev_db_opens == []
    assert _auth_rows(isolated_store) == before, "an auth lookup rewrote the auth store"


@sqlite_auth_only
def test_one_init_auth_db_call_leaves_every_seeded_account_able_to_log_in(
    isolated_store, dev_db_opens, tmp_path, monkeypatch
):
    """Startup calls it once. Grandfathering ran BEFORE seeding, so a fresh store kept the seeds
    PENDING until a second call — which only the per-lookup call supplied. Measured on a scratch
    store 2026-09-15: 17 PENDING after one call, 17 ACTIVE after the first lookup."""
    from app.core import auth

    monkeypatch.setattr(auth, "SEED_DEMO_USERS", True)
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "fresh.db"))
    auth.init_auth_db()

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT account_state, activated_by, phone_verified_at, agreement_signed_at,"
            " agreement_ref FROM auth_users"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == len(auth.DEMO_USER_SEEDS)
    # Grandfathered honestly (HANDOFF §2.1): ACTIVE, marked, and no vetting evidence invented.
    assert set(rows) == {("ACTIVE", "SEED_GRANDFATHERED", None, None, None)}, set(rows)
    assert auth.authenticate_user(auth.DEMO_USER_SEEDS[0]["email"], auth.DEMO_PASSWORD) is not None
    assert dev_db_opens == []


def test_the_app_runs_init_auth_db_at_startup():
    """AST, not text. Nothing creates the auth tables on import any more, so startup must."""
    tree = ast.parse((APP / "main.py").read_text())
    startup = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(ast.unparse(d) == "app.on_event('startup')" for d in node.decorator_list)
    ]
    assert any(
        isinstance(call, ast.Call) and ast.unparse(call.func).split(".")[-1] == "init_auth_db"
        for handler in startup
        for call in ast.walk(handler)
    ), (
        "no app.main startup handler calls init_auth_db(), so a fresh store has no auth tables "
        "and no seeded accounts (if startup moved to a lifespan, move this check with it)"
    )
