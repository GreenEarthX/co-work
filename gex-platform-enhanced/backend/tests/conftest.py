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

# The auth slice shares SQLITE_DB_PATH, so anything reading `auth_users` through
# `auth_connection()` needs the table to exist in the temporary store too. Only the
# columns writing tests actually touch — this is a stand-in, not a schema mirror.
_AUTH_USERS_DDL = """
CREATE TABLE IF NOT EXISTS auth_users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT,
    company_id    TEXT,
    company_name  TEXT,
    jurisdiction  TEXT,
    credit_rating TEXT,
    account_state TEXT DEFAULT 'ACTIVE',
    is_platform_admin INTEGER DEFAULT 0
)
"""


@pytest.fixture(scope="module")
def isolated_store(tmp_path_factory):
    """Point the SQLite-backed accessors at a throwaway database for this module."""
    from app.core.config import settings

    original = settings.SQLITE_DB_PATH
    db_path = tmp_path_factory.mktemp("store") / "test_gex_platform.db"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_AUTH_USERS_DDL)
        conn.commit()
    finally:
        conn.close()

    settings.SQLITE_DB_PATH = str(db_path)
    try:
        yield str(db_path)
    finally:
        settings.SQLITE_DB_PATH = original
