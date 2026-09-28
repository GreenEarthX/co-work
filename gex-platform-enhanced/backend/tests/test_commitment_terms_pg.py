"""
Commitment cards on PostgreSQL: tenant-scoped, and history the runtime cannot
rewrite (migration 058).

The cards hold what a producer says it signed — commitment forms, damages caps,
EPC price. Another tenant must not read them, and nobody must be able to rewrite
the record of how they changed. 031's default privileges give every new table
full DML to the runtime role, so this checks the REVOKEs actually took.

Runs as gex_app; skips when PostgreSQL is unconfigured or down. Writes nothing:
each statement runs in a transaction that is rolled back.
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
            pytest.skip("migration 058 not applied")
        return False
    finally:
        conn.rollback()
        conn.close()


def test_rls_is_forced_on_both_card_tables():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('commitment_terms', 'commitment_terms_events')")
        rows = cur.fetchall()
    finally:
        conn.close()
    if len(rows) < 2:
        pytest.skip("migration 058 not applied")
    for name, enabled, forced in rows:
        assert enabled and forced, f"RLS not enabled and forced on {name}"


@pytest.mark.parametrize("sql", [
    "DELETE FROM commitment_terms",
    "DELETE FROM commitment_terms_events",
    "UPDATE commitment_terms_events SET actor = 'someone else'",
])
def test_the_runtime_cannot_delete_cards_or_rewrite_their_history(sql):
    assert _refused(sql), f"gex_app was allowed to run: {sql}"


def test_the_runtime_can_save_a_card_and_append_its_history():
    """The revokes must not break the write path."""
    assert not _refused(
        "INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, updated_at) "
        "VALUES ('proj_hamburgone_emethanol', 'offtake', '{}', 'test', 'now')")
    assert not _refused(
        "INSERT INTO commitment_terms_events (project_id, card_type, new_json, actor, at) "
        "VALUES ('proj_hamburgone_emethanol', 'offtake', '{}', 'test', 'now')")


def test_another_tenant_cannot_write_into_a_project_it_does_not_own():
    """RLS refuses the row itself (insufficient privilege on the policy check)."""
    assert _refused(
        "INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, updated_at) "
        "VALUES ('proj_hamburgone_emethanol', 'offtake', '{}', 'intruder', 'now')",
        company="etfuels_sa")


def test_an_unknown_company_sees_no_cards():
    assert pg_as_tenant("acme_totally_unrelated", "SELECT count(*) FROM commitment_terms") == 0
    assert pg_as_tenant("NO_TENANT_CONTEXT", "SELECT count(*) FROM commitment_terms_events") == 0
