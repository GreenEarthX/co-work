"""
The runtime credential must be constrained by RLS, not exempt from it.
======================================================================
Migration 031 created `gex_app` and left it NOLOGIN, so the only way to use it
was `SET ROLE` from a superuser session. The application went on connecting as
`gex_user` — SUPERUSER, BYPASSRLS — which means no policy was ever evaluated in
production. "89 tables under forced RLS" described the schema, not the running
system.

Migration 045 grants LOGIN and `DATABASE_URL` now points at `gex_app`.

These tests assert against **whatever DATABASE_URL is actually configured**, not
against a hypothetical role. That is the point: if someone repoints DATABASE_URL
at a superuser — the quickest way to make a permissions error disappear — these
fail, loudly, instead of the system silently returning to a state where tenant
isolation is decorative.

The privilege probes are written as "this must be REFUSED". A test that only
checks the happy path would still pass on a superuser connection.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_connect

TENANT_SCOPED = ["projects", "finance_entitlements"]


def _autocommit():
    conn = pg_connect()
    conn.autocommit = True
    return conn


def _refused(sql: str) -> bool:
    """True if the configured runtime role is refused this statement."""
    conn = _autocommit()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return False
    except Exception:
        return True
    finally:
        conn.close()


def _count(table: str, company: str | None) -> int:
    conn = _autocommit()
    cur = conn.cursor()
    try:
        if company is not None:
            cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]
    finally:
        conn.close()


# ── The connected identity ──────────────────────────────────────────────────

def test_the_runtime_role_is_not_a_superuser():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT current_user, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
            FROM pg_roles WHERE rolname = current_user
        """)
        user, super_, bypass, createdb, createrole = cur.fetchone()
    finally:
        conn.close()

    assert not super_, (
        f"DATABASE_URL connects as {user!r}, which is a SUPERUSER. Every RLS "
        "policy in this database is then decorative — the runtime sees every "
        "tenant's rows regardless of what the policies say."
    )
    assert not bypass, f"{user!r} holds BYPASSRLS — tenant isolation does not apply"
    assert not createdb, f"{user!r} may create databases"
    assert not createrole, f"{user!r} may create roles, so it can grant itself more"


def test_the_runtime_role_is_the_one_the_migration_created():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT current_user")
        assert cur.fetchone()[0] == "gex_app", (
            "the runtime is not connecting as gex_app — if the role was renamed, "
            "update this test deliberately rather than widening it"
        )
    finally:
        conn.close()


# ── What it must be refused ─────────────────────────────────────────────────

@pytest.mark.parametrize("what,sql", [
    ("create a table", "CREATE TABLE gex_app_should_not_exist (x int)"),
    ("disable RLS", "ALTER TABLE projects DISABLE ROW LEVEL SECURITY"),
    ("escalate by SET ROLE", "SET ROLE gex_user"),
    ("read password hashes", "SELECT count(*) FROM pg_authid"),
    ("drop a table", "DROP TABLE projects"),
])
def test_the_runtime_role_is_refused(what, sql):
    assert _refused(sql), (
        f"the runtime role was ALLOWED to {what}. A compromised request path "
        "could then bypass every tenant policy in the database."
    )


def test_the_runtime_cannot_create_an_unprotected_table():
    """
    The subtle escalation: not reading data directly, but creating a table with
    no RLS and copying data into it. Refused because gex_app has USAGE but not
    CREATE on schema public.
    """
    assert _refused("CREATE TABLE exfil AS SELECT * FROM projects")


# ── RLS actually binds now ──────────────────────────────────────────────────

@pytest.mark.parametrize("table", TENANT_SCOPED)
def test_no_tenant_context_reveals_nothing(table):
    assert _count(table, None) == 0, (
        f"{table}: a connection with no tenant context returned rows. The "
        "runtime must fail closed when it cannot establish a caller."
    )


def test_a_tenant_sees_less_than_platform_admin():
    """
    THE test for this slice. Before migration 045 this could not be written:
    the runtime connected as a superuser, so both numbers were the same and
    tenant isolation was unfalsifiable.
    """
    admin = _count("projects", "PLATFORM_ADMIN")
    if admin == 0:
        pytest.skip("no projects to isolate")
    tenant = _count("projects", "hamburgone_com")
    assert 0 < tenant < admin, (
        f"tenant sees {tenant} of {admin} projects — expected a strict subset. "
        "Equal means RLS is not binding; zero means the tenant cannot see its "
        "own data."
    )


def test_one_tenant_cannot_see_another_tenants_projects():
    conn = _autocommit()
    cur = conn.cursor()
    try:
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SELECT company_id FROM tenants ORDER BY company_id")
        companies = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    if len(companies) < 2:
        pytest.skip("need two tenants to compare")

    seen = {c: _count("projects", c) for c in companies}
    total = _count("projects", "PLATFORM_ADMIN")
    assert sum(seen.values()) <= total * len(companies), "impossible counts"
    assert any(n < total for n in seen.values()), (
        f"every tenant sees all {total} projects — isolation is not binding"
    )


def test_public_reference_data_is_still_readable():
    """Failing closed must not blackhole data that is deliberately shared."""
    assert _count("fuel_catalog", None) == 10
    assert _count("fuel_unit_conversions", None) == 120


# ── Credential separation ───────────────────────────────────────────────────

def test_alembic_prefers_its_own_credential():
    from pathlib import Path

    env = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text()
    idx_alembic = env.find("ALEMBIC_DATABASE_URL")
    idx_database = env.find('os.getenv("DATABASE_URL")')
    assert idx_alembic != -1, (
        "alembic/env.py no longer reads ALEMBIC_DATABASE_URL — migrations would "
        "run with the runtime credential, which has no DDL rights, or worse "
        "would require giving the runtime DDL rights"
    )
    assert idx_alembic < idx_database, "DATABASE_URL takes precedence over ALEMBIC_DATABASE_URL"


def test_the_two_credentials_are_different_roles():
    """
    If both variables point at the same role, the separation is nominal. This
    catches the most likely regression: copying DATABASE_URL into
    ALEMBIC_DATABASE_URL to make a migration work.
    """
    runtime = os.environ.get("DATABASE_URL") or ""
    migrator = os.environ.get("ALEMBIC_DATABASE_URL") or ""
    if not migrator:
        pytest.skip("ALEMBIC_DATABASE_URL not exported in this shell")

    def role(dsn: str) -> str:
        from urllib.parse import urlparse
        return urlparse(dsn).username or ""

    assert role(runtime) != role(migrator), (
        f"both credentials use role {role(runtime)!r}. The migrator needs DDL; "
        "the runtime must not have it."
    )
