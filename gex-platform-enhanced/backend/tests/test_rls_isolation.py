"""
RLS guardrails — proof that tenant isolation actually engages.
==============================================================
Slice 3 (docs/postgres-migration-plan.md). The migration plan calls RLS the
"final backstop" and slice 3 "the slice that turns RLS on for real".

WHAT THIS CAUGHT
----------------
Migration 020 enables RLS on `projects`/`project_access`, marks both FORCE ROW
LEVEL SECURITY, and writes correct tenant-isolation policies. Every one of
those facts was true, and isolation still did not happen:

    connected as : gex_user   SUPERUSER=True

Superusers bypass RLS unconditionally; FORCE does not apply to them. Measured
before the fix — a company that does not exist could read every project:

    SET LOCAL app.current_company_id = 'acme_totally_unrelated';
    SELECT count(*) FROM projects;   →  12   (all of them)

"RLS is enabled" is therefore NOT evidence that RLS works. The only evidence
is a query, run as the role the application actually uses, that comes back
filtered. That is what these tests are.

Migration 031 adds the least-privilege role `gex_app`. The application must
connect as it (or SET ROLE to it). Connecting as a superuser silently disables
every policy in the database.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_connect

DSN = os.getenv("DATABASE_URL", "")
APP_ROLE = "gex_app"

psycopg2 = pytest.importorskip("psycopg2", reason="Postgres driver not installed")


def _connect():
    """Connect, or skip. Delegates so the suite has ONE connect site — see
    pg_support: an absent or unreachable database must always read as a skip."""
    return pg_connect()


@pytest.fixture()
def conn():
    c = _connect()
    yield c
    c.rollback()
    c.close()


def _tables_exist(cur) -> bool:
    cur.execute("SELECT to_regclass('public.projects') IS NOT NULL")
    return bool(cur.fetchone()[0])


def _visible_projects(cur, company: str | None, as_app_role: bool = True) -> int:
    cur.execute("BEGIN")
    if as_app_role:
        cur.execute(f"SET LOCAL ROLE {APP_ROLE}")
    if company is not None:
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))
    cur.execute("SELECT count(*) FROM projects")
    n = cur.fetchone()[0]
    cur.execute("ROLLBACK")
    return n


# ── The role that makes any of this real ────────────────────────────────────

def test_the_least_privilege_app_role_exists(conn):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    assert cur.fetchone(), (
        f"role {APP_ROLE!r} is missing — run migration 031. Without it the "
        "application connects as a superuser and every RLS policy is inert."
    )


def test_the_app_role_is_not_a_superuser_and_cannot_bypass_rls(conn):
    """
    The whole mechanism rests on this. A well-meaning `ALTER ROLE gex_app
    SUPERUSER` while debugging a permissions error would silently disable
    tenant isolation across the entire database and nothing else would notice.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (APP_ROLE,)
    )
    row = cur.fetchone()
    if row is None:
        pytest.skip("app role not created yet (migration 031 not applied)")
    is_super, bypass = row
    assert not is_super, f"{APP_ROLE} is a SUPERUSER — RLS does not apply to it"
    assert not bypass, f"{APP_ROLE} has BYPASSRLS — RLS does not apply to it"


def test_rls_is_enabled_and_forced_on_the_tenant_tables(conn):
    cur = conn.cursor()
    if not _tables_exist(cur):
        pytest.skip("projects table not migrated yet")
    cur.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname IN ('projects','project_access')"
    )
    rows = cur.fetchall()
    assert rows, "projects/project_access not found"
    for name, enabled, forced in rows:
        assert enabled, f"RLS not enabled on {name}"
        assert forced, f"RLS not FORCEd on {name} — the owner would bypass it"


# ── Isolation, measured ─────────────────────────────────────────────────────

def test_an_unknown_company_sees_no_projects(conn):
    """
    THE test. Before migration 031 this returned 12 — every project in the
    database — for a company that does not exist.
    """
    cur = conn.cursor()
    if not _tables_exist(cur):
        pytest.skip("projects table not migrated yet")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if not cur.fetchone():
        pytest.skip("app role not created yet (migration 031 not applied)")

    assert _visible_projects(cur, "acme_totally_unrelated") == 0


def test_an_unset_tenant_context_reveals_nothing(conn):
    """A connection that forgot to set the GUC must fail closed, not open."""
    cur = conn.cursor()
    if not _tables_exist(cur):
        pytest.skip("projects table not migrated yet")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if not cur.fetchone():
        pytest.skip("app role not created yet (migration 031 not applied)")

    assert _visible_projects(cur, None) == 0


def test_platform_admin_sees_everything_and_a_tenant_sees_less(conn):
    """
    Isolation is only meaningful if it is selective: the admin sentinel must
    see strictly more than an ordinary tenant, and the tenant must see some.
    """
    cur = conn.cursor()
    if not _tables_exist(cur):
        pytest.skip("projects table not migrated yet")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if not cur.fetchone():
        pytest.skip("app role not created yet (migration 031 not applied)")

    cur.execute("SELECT count(*) FROM projects")
    total = cur.fetchone()[0]
    if total == 0:
        pytest.skip("no projects seeded")

    admin = _visible_projects(cur, "PLATFORM_ADMIN")
    owner = _visible_projects(cur, "etfuels_sa")

    assert admin == total, "PLATFORM_ADMIN must see every project"
    assert owner > 0, "the owning tenant must see its own projects"
    assert owner < total, (
        "the owning tenant sees every project in the database — isolation is "
        "not filtering. Check that the connection is not a superuser."
    )


# ── The configuration mistake that silently disables everything ─────────────

def test_the_configured_database_user_should_not_be_a_superuser(conn):
    """
    Advisory, and deliberately not a hard failure: `gex_user` is legitimately a
    superuser because it owns the schema and runs migrations. What matters is
    that the APPLICATION does not connect as it. This test states the
    requirement loudly so the day someone points DATABASE_URL at a superuser in
    a deployed environment, the reason is already written down.
    """
    cur = conn.cursor()
    cur.execute("SELECT current_user, usesuper FROM pg_user WHERE usename = current_user")
    user, is_super = cur.fetchone()
    if is_super:
        pytest.skip(
            f"connected as superuser {user!r} — fine for migrations, NEVER for the "
            f"application. Deploy with DATABASE_URL pointing at {APP_ROLE}."
        )
    assert not is_super
