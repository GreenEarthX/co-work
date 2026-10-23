"""
The single PostgreSQL entry point for the test suite.
=====================================================
Every test that touches PostgreSQL must obtain its connection from here.

WHY THIS MODULE EXISTS
----------------------
Before it, seven test files each defined their own `_pg()` and there were 24
scattered copies of

    if not (os.environ.get("DATABASE_URL") or "").startswith("postgres"):
        pytest.skip(...)

That guard checks the DSN *string*. It does not check that anything is
listening. So the suite had two populations: helpers built on `_pg()`, which
caught the connection error and skipped, and raw `psycopg2.connect` call sites,
which raised it and FAILED.

Observed 2026-08-10 with the database container stopped:

    8 failed, 209 passed, 70 skipped

An outage was indistinguishable at a glance from a regression — which is
exactly the wrong signal, because it burns the reviewer's attention on the one
thing that is not a code defect. A test that cannot run has not found a bug.

THE RULE
--------
"PostgreSQL is absent or unreachable" is a SKIP. Only a reachable database that
answers incorrectly is a FAILURE. Every function below enforces that by routing
through `pg_connect()`, which is the only place in the suite that calls
`psycopg2.connect`.

Reachability is probed once per session and cached: with the database down, 70+
tests would otherwise each pay the connect timeout.
"""
from __future__ import annotations

import os

import pytest

__all__ = [
    "pg_dsn",
    "pg_connect",
    "pg_admin",
    "pg_as_tenant",
    "requires_pg",
    "as_platform_admin",
    "pg_bypassrls_connect",
    "throwaway_pg_database",
    "connect_dsn",
]

_CONNECT_TIMEOUT = 3

# None = not yet probed; "" = reachable; str = the reason it is not.
_unreachable_reason: str | None = None


def pg_dsn() -> str:
    """The DSN, or skip if PostgreSQL is not the configured target.

    This is the *configuration* check only. It says nothing about whether the
    server is up — use `pg_connect()` for that.
    """
    dsn = os.environ.get("DATABASE_URL") or ""
    if not dsn.startswith("postgres"):
        pytest.skip("DATABASE_URL not set to PostgreSQL")
    return dsn


def pg_connect(**kwargs):
    """A psycopg2 connection, or SKIP.

    The only `psycopg2.connect` call site in the suite. A connection error is
    converted to a skip here so it can never surface as a test failure.
    """
    global _unreachable_reason

    dsn = pg_dsn()
    if _unreachable_reason:
        pytest.skip(_unreachable_reason)

    import psycopg2

    kwargs.setdefault("connect_timeout", _CONNECT_TIMEOUT)
    try:
        conn = psycopg2.connect(dsn, **kwargs)
    except Exception as exc:  # noqa: BLE001 — any failure to connect is a skip
        _unreachable_reason = f"PostgreSQL unreachable: {exc}"
        pytest.skip(_unreachable_reason)
    _unreachable_reason = ""
    return conn


def requires_pg() -> None:
    """Skip unless PostgreSQL is configured AND reachable.

    For tests that reach the database indirectly — through the application's
    backend shim rather than psycopg2 — where there is no connection object to
    obtain from here, but an outage must still read as a skip.
    """
    pg_connect().close()


def pg_admin():
    """`(conn, cur)` as PLATFORM_ADMIN, with a RealDictCursor — or skip.

    The former per-file `_pg()`. This sets the company GUC only.

    Since migration 045 DATABASE_URL connects as `gex_app`, which has no
    BYPASSRLS — so RLS binds here too, and PLATFORM_ADMIN is a *policy* grant
    rather than a role exemption. `SET LOCAL ROLE gex_app` in `pg_as_tenant` is
    now a no-op in practice, and is kept so those tests stay correct if the
    connecting role is ever changed back.
    """
    import psycopg2.extras

    conn = pg_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET app.current_company_id='PLATFORM_ADMIN'")
    return conn, cur


def pg_as_tenant(company: str, sql: str, params=None):
    """Run one statement as `gex_app` scoped to `company`; return its first column.

    Always rolled back, so it is safe for reads against live data.

    `SET LOCAL ROLE gex_app` was load-bearing while the runtime connected as a
    superuser: without it every isolation test passed whether the policies were
    correct or not. Since migration 045 the connection is already `gex_app`, so
    it is belt-and-braces — deliberately kept, because a future change to
    DATABASE_URL must not silently make these tests vacuous again.
    """
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.rollback()
        conn.close()


# ── The application's tenant context, for tests ─────────────────────────────

import contextlib  # noqa: E402


@contextlib.contextmanager
def as_platform_admin():
    """Bind PLATFORM_ADMIN as the caller for the duration of the block.

    Needed by whole-store comparisons — "is the copy faithful?" is a question
    about ALL rows, so it cannot be asked as a tenant. Before the shim defaulted
    to a deny sentinel these tests worked by accident, because the default WAS
    admin; that same accident meant 64 production call sites read as admin too.

    Declaring it here is the point: a test that needs to see everything says so,
    exactly as the seven production bootstrap call sites now do.
    """
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company("PLATFORM_ADMIN")
    try:
        yield
    finally:
        reset_current_company(token)


def pg_bypassrls_connect():
    """A psycopg2 connection that RLS does not bind, or None.

    ALEMBIC_DATABASE_URL is `gex_user` — superuser and BYPASSRLS — so it is the
    only honest answer to "how many rows actually exist", which RLS deliberately
    hides from `gex_app` (migration 045). A test comparing what PLATFORM_ADMIN
    sees against the true total needs that, and cannot get it from pg_connect().

    Returns None rather than skipping when ALEMBIC_DATABASE_URL is not exported,
    so a caller keeps its other assertions instead of going dark — the failure
    mode that left test_rls_isolation's selectivity check dead from 045 onward.

    Lives here because this module is the suite's ONLY psycopg2.connect site,
    which test_architecture_guardrails enforces against the AST.
    """
    dsn = os.getenv("ALEMBIC_DATABASE_URL")
    if not dsn:
        return None

    import psycopg2

    try:
        return psycopg2.connect(dsn, connect_timeout=_CONNECT_TIMEOUT)
    except Exception:
        return None


# ── A throwaway PostgreSQL database, built by the migrations ────────────────

def connect_dsn(dsn: str):
    """A psycopg2 connection to an explicit DSN (a throwaway database's)."""
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, connect_timeout=_CONNECT_TIMEOUT,
                            cursor_factory=psycopg2.extras.RealDictCursor)


@contextlib.contextmanager
def throwaway_pg_database(name: str):
    """Create `name` in the dev cluster, migrate it to auth_slice@head, yield the
    RUNTIME dsn (gex_app), and drop it afterwards.

    For tests whose code under test commits (the market engine, the event
    ledger): a rolled-back transaction cannot hold them, and writing the dev
    database is forbidden. Same roles, same migrations, same RLS as live — but
    nothing it holds survives the test. Skips when PostgreSQL or either
    exported URL is missing, like everything else in this module.
    """
    import subprocess
    import sys
    from pathlib import Path

    runtime, admin = os.getenv("DATABASE_URL") or "", os.getenv("ALEMBIC_DATABASE_URL") or ""
    if not (runtime.startswith("postgres") and admin.startswith("postgres")):
        pytest.skip("DATABASE_URL and ALEMBIC_DATABASE_URL must both be exported")
    assert name.startswith("gex_test_"), "throwaway databases are named gex_test_*"
    swap = lambda dsn: dsn.rsplit("/", 1)[0] + "/" + name  # noqa: E731
    pg_connect().close()                                   # reachable, or skip

    import psycopg2

    def admin_sql(*statements):
        conn = psycopg2.connect(swap(admin).rsplit("/", 1)[0] + "/postgres", connect_timeout=_CONNECT_TIMEOUT)
        conn.autocommit = True
        try:
            for sql in statements:
                conn.cursor().execute(sql)
        finally:
            conn.close()

    admin_sql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)", f"CREATE DATABASE {name}",
              f"ALTER DATABASE {name} SET app.current_company_id = 'GUEST'",
              f"GRANT CONNECT ON DATABASE {name} TO gex_app")
    try:
        backend = Path(__file__).resolve().parent.parent
        run = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "auth_slice@head"], cwd=backend,
                             env={**os.environ, "ALEMBIC_DATABASE_URL": swap(admin)},
                             capture_output=True, text=True)
        assert run.returncode == 0, f"migrating {name} failed:\n{run.stderr[-2000:]}"
        yield swap(runtime)
    finally:
        admin_sql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")

