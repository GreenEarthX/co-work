"""
Who may write project_access (migration 062, 2026-10-21).

project_access decides, through app_company_has_project_access, what every
tenant-scoped policy lets a company read: evidence, cards, context, projects.
Until 062 its one FOR ALL policy had no WITH CHECK, so the read rule doubled as
the write rule, and that rule includes `company_id = current company`. A tenant
could INSERT a row naming ITSELF on any project. Reproduced 2026-10-21 as
madrid2_com on proj_hamburgone_emethanol: no access, one INSERT, then 47 of
HamburgOne's evidence rows readable (rolled back).

Since 062 only PLATFORM_ADMIN writes it (GEX administration: tenant_admin and
reviewer appointments). Reads are unchanged. Every statement here runs as gex_app
in a transaction that is ROLLED BACK — the development database is not written.
"""
from __future__ import annotations

import pytest

from pg_support import pg_connect

PID = "proj_hamburgone_emethanol"     # owner hamburgone_com; nordlb holds a row on it


def _as(company: str, sql: str, params=()):
    """Run one statement as gex_app bound to `company`. Returns ('refused', None)
    when RLS rejects it, else ('ok', rowcount); always rolled back."""
    import psycopg2

    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))
        if cur.execute("SELECT to_regclass('project_access')") or cur.fetchone()[0] is None:
            pytest.skip("project_access absent")
        try:
            cur.execute(sql, params)
        except psycopg2.errors.InsufficientPrivilege:
            return "refused", None
        return "ok", cur.rowcount
    finally:
        conn.rollback()
        conn.close()


GRANT = ("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) "
         "VALUES (%s, %s, 'PRODUCER', 'STAKEHOLDER', 'TEST')")


def test_a_tenant_cannot_grant_itself_access_to_another_companys_project():
    assert _as("madrid2_com", GRANT, (PID, "madrid2_com")) == ("refused", None)


def test_the_owner_cannot_grant_access_either():
    """Granting access is GEX administration (JML, 2026-10-21: GEX staff appoint)."""
    assert _as("hamburgone_com", GRANT, (PID, "madrid2_com")) == ("refused", None)


@pytest.mark.parametrize("sql", [
    "UPDATE project_access SET access_role = 'OWNER' WHERE project_id = %s AND company_id = %s",
    "DELETE FROM project_access WHERE project_id = %s AND company_id = %s",
])
def test_a_tenant_can_neither_rewrite_nor_remove_its_own_row(sql):
    outcome = _as("nordlb", sql, (PID, "nordlb"))
    assert outcome in (("ok", 0), ("refused", None)), outcome


def test_platform_admin_still_grants():
    assert _as("PLATFORM_ADMIN", GRANT, (PID, "madrid2_com")) == ("ok", 1)


def test_reads_are_unchanged():
    status, n = _as("nordlb", "SELECT 1 FROM project_access WHERE project_id = %s AND company_id = %s",
                    (PID, "nordlb"))
    assert status == "ok" and n >= 1                # a company still sees its own access
