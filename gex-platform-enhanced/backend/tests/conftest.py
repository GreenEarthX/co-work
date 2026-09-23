"""
Shared test fixtures.

`isolated_store` exists because it was missing. `capital_connection()` and
`auth_connection()` resolve `settings.SQLITE_DB_PATH` at call time, and that path is the
real development database. Test modules that WRITE — billing, throughput, open interest —
were therefore accumulating rows in `gex_platform.db` on every run: 94 terms versions, 62
acceptances, 54 invoices and 22 throughput charges before anyone noticed.

Characterization tests that only READ the live store are unaffected and must keep reading
it — that is the point of them. This fixture is for tests that write.

Request it from a module-scoped autouse fixture:

    @pytest.fixture(scope="module", autouse=True)
    def _schema(isolated_store):
        my_module.init_db()
"""
from __future__ import annotations

import os
import sqlite3

import pytest


@pytest.fixture(scope="module")
def isolated_store(tmp_path_factory):
    """Point the SQLite-backed accessors at a throwaway database for this module."""
    from app.core.config import settings

    original = settings.SQLITE_DB_PATH
    db_path = tmp_path_factory.mktemp("store") / "test_gex_platform.db"

    settings.SQLITE_DB_PATH = str(db_path)

    # Swapping the path is not isolation on its own. Once a slice switch says
    # `postgres` the store ignores SQLITE_DB_PATH entirely and writes the
    # DEVELOPMENT PostgreSQL database — measured on 2026-09-22, a full run added
    # rows to auth_users, auth_user_project_roles, finance_entitlements and
    # entitlement_audit. So the switches are pinned to sqlite here too, in both
    # places the accessors read them: os.environ (which `set -a && source .env`
    # populates) and `settings`. A test that genuinely wants PostgreSQL asks for
    # it explicitly — `requires_pg()` and `as_platform_admin()` in pg_support —
    # rather than inheriting whatever the developer's .env happens to say.
    # DERIVED from Settings, never hand-listed. A hardcoded list was wrong
    # twice in one day: DOMAIN (the 043/044 tail) and then WORKSPACE (the
    # owner-scoped canvas tables) were each added to config.py and forgotten
    # here, and each time the first test to exercise that slice went straight
    # at the development PostgreSQL — once writing it, once failing because the
    # store had correctly refused to create a table the migration owns. Reading
    # the field names means the next switch is covered the moment it exists.
    switch_names = sorted(
        name for name in type(settings).model_fields if name.endswith("_DB_BACKEND"))
    assert switch_names, "no *_DB_BACKEND fields found on Settings — the scan is broken"
    saved_env: dict[str, str | None] = {}
    saved_settings: dict[str, str] = {}
    for name in switch_names:
        saved_env[name] = os.environ.get(name)
        saved_settings[name] = getattr(settings, name, "sqlite")
        os.environ[name] = "sqlite"
        setattr(settings, name, "sqlite")

    try:
        # The auth slice shares SQLITE_DB_PATH, so the temporary store gets the REAL
        # auth schema from its owner. A hand-written stand-in used to live here; it
        # lacked `is_active`, `password_hash` and the other columns `init_auth_db()`
        # needs, so any test running a real auth lookup under this fixture crashed.
        # Schema only, no demo seeds. Importing `auth` writes nothing (since 2026-09-15
        # seeding is an app-startup step), so import order no longer matters here.
        from app.core import auth

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            auth._ensure_tables(conn)
        finally:
            conn.close()
        yield str(db_path)
    finally:
        settings.SQLITE_DB_PATH = original
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
            setattr(settings, name, saved_settings[name])
