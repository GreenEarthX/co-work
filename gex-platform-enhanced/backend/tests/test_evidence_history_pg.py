"""
Evidence history cannot be rewritten by the runtime, and stays tenant-scoped.

Found 2026-09-26: the runtime role gex_app could DELETE from
bankability_evidence_archive (migration 055) and UPDATE/DELETE the
"append-only" evidence_events log, because migration 031's DEFAULT PRIVILEGES
hand every new table full DML. Migration 056 revokes it.

Runs as gex_app against PostgreSQL; skips when it is unconfigured or down.
Writes nothing: every statement is inside a transaction that is rolled back,
and the writes under test are expected to be refused before touching a row.
"""

from __future__ import annotations

import pytest

from pg_support import pg_as_tenant, pg_connect


def _refused(sql: str, company: str = "hamburgone_com") -> bool:
    import psycopg2

    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))
        try:
            cur.execute(sql)
        except psycopg2.errors.InsufficientPrivilege:
            return True
        except psycopg2.errors.UndefinedTable:
            pytest.skip("migration 055 not applied")
        return False
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("sql", [
    "DELETE FROM bankability_evidence_archive",
    "UPDATE bankability_evidence_archive SET notes = 'rewritten'",
    "INSERT INTO bankability_evidence_archive (original_id, project_id, evidence_key, archived_at, "
    "archived_by, archive_reason, disposition) VALUES (0, 'p', 'k', 'now', 'x', 'x', 'REMOVED')",
])
def test_the_runtime_cannot_rewrite_the_evidence_archive(sql):
    assert _refused(sql), f"gex_app was allowed to run: {sql}"


@pytest.mark.parametrize("sql", [
    "DELETE FROM evidence_events",
    "UPDATE evidence_events SET actor = 'someone else'",
])
def test_the_runtime_cannot_rewrite_the_evidence_audit_log(sql):
    assert _refused(sql), f"gex_app was allowed to run: {sql}"


def test_the_runtime_can_still_append_to_the_audit_log():
    """The revoke must not break the write path: every evidence write appends here."""
    assert not _refused(
        "INSERT INTO evidence_events (project_id, evidence_key, new_status, actor, at) "
        "VALUES ('proj_hamburgone_emethanol', 'k', 'NOT_STARTED', 'test', 'now')")


def test_the_archive_is_tenant_scoped():
    if pg_as_tenant("PLATFORM_ADMIN", "SELECT count(*) FROM bankability_evidence_archive") == 0:
        pytest.skip("archive is empty on this database")
    assert pg_as_tenant("acme_totally_unrelated", "SELECT count(*) FROM bankability_evidence_archive") == 0
    assert pg_as_tenant("NO_TENANT_CONTEXT", "SELECT count(*) FROM bankability_evidence_archive") == 0
