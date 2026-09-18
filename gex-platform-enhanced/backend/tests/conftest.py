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

import sqlite3

import pytest


@pytest.fixture(scope="module")
def isolated_store(tmp_path_factory):
    """Point the SQLite-backed accessors at a throwaway database for this module."""
    from app.core.config import settings

    original = settings.SQLITE_DB_PATH
    db_path = tmp_path_factory.mktemp("store") / "test_gex_platform.db"

    settings.SQLITE_DB_PATH = str(db_path)
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
