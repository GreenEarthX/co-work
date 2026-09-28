"""
The bankability evidence path must work on PostgreSQL — the configured store.

Found 2026-09-26. routes_bankability_proxy._ensure_tables ran SQLite DDL
unconditionally, and every read and write in the module calls it first. On
PostgreSQL that DDL raised `syntax error at or near "AUTOINCREMENT"`, so under
EVIDENCE_DB_BACKEND=postgres — the live configuration since the evidence slice
was cut over — every evidence operation failed: evaluate, update, list, document
upload, the audit trail and the health check.

It stayed invisible for two reasons, and this test answers both:
  * the UI showed ABAC's 403 before the handler ever ran, so the failure looked
    like an access decision rather than a crash;
  * every other test of this module runs on SQLite via `isolated_store`, where
    the DDL is valid. The defect only exists on the database it runs against.

So these tests deliberately do NOT use isolated_store. They skip when
PostgreSQL is unconfigured or unreachable, and fail only when a reachable
PostgreSQL rejects the evidence path. They write nothing: every call here reads,
and the only DDL involved is the guard that must now return before issuing any.
"""

from __future__ import annotations

import pytest

from pg_support import as_platform_admin, requires_pg


@pytest.fixture
def evidence_on_postgres(monkeypatch):
    requires_pg()
    from app.core.config import settings

    monkeypatch.setenv("EVIDENCE_DB_BACKEND", "postgres")
    monkeypatch.setattr(settings, "EVIDENCE_DB_BACKEND", "postgres", raising=False)
    from app.core.db_backend import evidence_is_postgres

    if not evidence_is_postgres():
        pytest.skip("evidence slice could not be pointed at PostgreSQL")


def test_ensure_tables_issues_no_sqlite_ddl_on_postgres(evidence_on_postgres):
    from app.api.v1 import routes_bankability_proxy as proxy

    conn = proxy._get_db()
    try:
        proxy._ensure_tables(conn)  # raised SyntaxError on AUTOINCREMENT before the fix
    finally:
        conn.close()


def test_evidence_can_be_read_on_postgres(evidence_on_postgres):
    from app.api.v1 import routes_bankability_proxy as proxy

    with as_platform_admin():
        rows = proxy._load_evidence("proj_etf_pecos1")
        proxy._get_project_state("proj_etf_pecos1")
        proxy._existing_maturity("proj_etf_pecos1", "curtailment_assessment")
    # Every row carries the maturity key the engine reads (migration 054).
    assert all("maturity" in r for r in rows)


def test_the_health_check_reports_the_database_honestly(evidence_on_postgres):
    """
    The health route swallows any exception and reports `platform_db: error`.
    It read `error` on every call under PostgreSQL, which is how the defect was
    finally seen — the only symptom anywhere that was not a 403.
    """
    from app.api.v1 import routes_bankability_proxy as proxy

    conn = proxy._get_db()
    try:
        proxy._ensure_tables(conn)
        ok = True
    except Exception:
        ok = False
    finally:
        conn.close()
    assert ok
