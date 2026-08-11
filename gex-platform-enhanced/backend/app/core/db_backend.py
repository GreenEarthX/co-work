"""
Auth-slice database backend — SQLite or PostgreSQL, chosen by configuration.
============================================================================
Strangler slice 2 (docs/postgres-migration-plan.md). The auth modules keep
ONE code path; only the connection they receive changes.

    AUTH_DB_BACKEND=sqlite    (default — no behaviour change)
    AUTH_DB_BACKEND=postgres  (uses DATABASE_URL)

Why a shim rather than a rewrite
--------------------------------
app/core/auth.py is ~900 lines of working, security-critical SQL that already
passes 22 lifecycle tests. Rewriting it to SQLAlchemy in the same change that
moves the data would make any failure ambiguous — copy bug, or rewrite bug?
This adapter lets the EXACT SAME SQL run against both stores, so the two can
be compared row-for-row and the flip is a config change, not a leap.

The shim is deliberately small and deliberately temporary. When the slice is
settled, the modules move to the SQLAlchemy layer and this goes away.

What it adapts
--------------
· Placeholders — sqlite3 uses `?`, psycopg2 uses `%s`.
· Cursors — sqlite3.Connection.execute() exists; psycopg2's does not.
· Rows — sqlite3.Row supports row["col"] and row.keys(); RealDictCursor
  returns dicts, which support both.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from typing import Any

from app.core.config import settings

logger = logging.getLogger("gex.db_backend")

SQLITE = "sqlite"
POSTGRES = "postgres"
from app.core.request_tenant import (  # noqa: E402  (vocabulary lives there)
    NO_TENANT_CONTEXT,
    PLATFORM_ADMIN,
    current_company,
)

# The tenant context a connection gets when the caller supplies none.
#
# WHY THIS EXISTS (2026-08-10)
# ---------------------------
# Every accessor below used to default to PLATFORM_ADMIN, and an audit of all
# 64 call sites found that NOT ONE of them overrode it. 88 of the 93 RLS
# policies grant PLATFORM_ADMIN full visibility, so on the day these switches
# flip to PostgreSQL those 64 sites would have read every tenant's rows — while
# every RLS test still passed, because the tests set their own context.
#
# That is a fail-OPEN default hiding behind correct-looking policies. The
# sentinel below matches no tenant-scoped policy, so an unset context now
# returns nothing instead of everything. Measured under role `gex_app`:
#
#     projects              14 rows as PLATFORM_ADMIN  ->   0 with the sentinel
#     finance_entitlements 838 rows as PLATFORM_ADMIN  ->   0 with the sentinel
#
# Deliberately public data is UNAFFECTED, because its policies do not consult
# the company at all: fuel_catalog (10), fuel_unit_conversions (120),
# approval_policies (8) and sod_conflict_pairs (8) all still read normally.
# Auth tables are not under RLS, so login is unaffected.
#
# Admin access is still available — but it must now be asked for by name, and
# saying so is logged. See _tenant_context().

# One warning per (accessor, caller) rather than per call: these run in hot
# paths and a per-call warning would be ignored within a day.
_announced_admin: set[tuple[str, str]] = set()


def _tenant_context(company_id: str | None, accessor: str) -> str:
    """Resolve the tenant context for a PostgreSQL connection, logging escalation.

    PLATFORM_ADMIN disables tenant isolation for the whole connection, so every
    use of it is recorded with the call site that asked. If this log is noisy,
    that is the finding — it means something is reading as admin that should be
    reading as a tenant.
    """
    if company_id is None:
        # Unspecified — use the caller bound by ABACMiddleware for this request.
        # Absent one (background job, worker thread, unauthenticated path) this
        # is None, and the sentinel below reveals nothing.
        company_id = current_company() or NO_TENANT_CONTEXT

    if company_id != PLATFORM_ADMIN:
        return company_id

    import traceback

    caller = "unknown"
    for frame in reversed(traceback.extract_stack()[:-1]):
        if not frame.filename.endswith("db_backend.py"):
            caller = f"{os.path.basename(frame.filename)}:{frame.lineno}"
            break
    key = (accessor, caller)
    if key not in _announced_admin:
        _announced_admin.add(key)
        logger.warning(
            "RLS tenant isolation disabled: %s() opened a PLATFORM_ADMIN "
            "connection from %s. This connection sees every tenant's rows.",
            accessor, caller,
        )
    logger.debug("PLATFORM_ADMIN connection: %s() from %s", accessor, caller)
    return company_id


def auth_backend() -> str:
    """
    Which store the auth slice is pointed at. Defaults to SQLite.

    An explicit environment variable wins over the config field so a single
    test or one-off command can switch backends without editing .env.
    """
    return (os.getenv("AUTH_DB_BACKEND")
            or getattr(settings, "AUTH_DB_BACKEND", SQLITE)).strip().lower()


def is_postgres() -> bool:
    return auth_backend() == POSTGRES


# `?` placeholders, but not ones inside single-quoted string literals.
_PLACEHOLDER = re.compile(r"\?(?=(?:[^']*'[^']*')*[^']*$)")


def _to_pg(sql: str) -> str:
    """Translate sqlite3 placeholders to psycopg2's, and the one portability
    wart in the auth SQL (`datetime('now')` → `now()`)."""
    sql = _PLACEHOLDER.sub("%s", sql)
    return sql.replace("datetime('now')", "now()")


class _PgCursor:
    """sqlite3-cursor-shaped view over a psycopg2 cursor."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def lastrowid(self):  # pragma: no cover — auth.py uses explicit ids
        return None

    def __iter__(self):
        return iter(self._cur)


class PostgresConnection:
    """
    sqlite3.Connection-shaped adapter over psycopg2.

    Only the surface app/core/auth.py actually uses is implemented — execute(),
    cursor(), commit(), rollback(), close(). Anything else is intentionally
    absent so an unported call fails loudly instead of silently misbehaving.
    """

    def __init__(self, dsn: str, company_id: str | None = None) -> None:
        import psycopg2
        import psycopg2.extras

        self._conn = psycopg2.connect(dsn)
        self._factory = psycopg2.extras.RealDictCursor
        if company_id is not None:
            # Session-scoped SET, not SET LOCAL. These callers commit partway
            # through a request, and SET LOCAL is reset at COMMIT — the tenant
            # context would silently vanish mid-request and RLS would then hide
            # everything. The connection is per-request and closed after.
            self.execute(f"SET app.current_company_id = '{_safe_company(company_id)}'")

    def execute(self, sql: str, params: tuple | list = ()) -> _PgCursor:
        cur = self._conn.cursor(cursor_factory=self._factory)
        cur.execute(_to_pg(sql), tuple(params))
        return _PgCursor(cur)

    def cursor(self) -> _PgCursor:
        return _PgCursor(self._conn.cursor(cursor_factory=self._factory))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0]:
            self.rollback()
        else:
            self.commit()
        self.close()


def _safe_company(company_id: str) -> str:
    """Whitelist before interpolation — SET cannot take a bind parameter."""
    if company_id == PLATFORM_ADMIN or re.fullmatch(r"[a-z0-9_]{1,120}", company_id or ""):
        return company_id
    raise ValueError(f"unsafe company_id for tenant context: {company_id!r}")


def evidence_backend() -> str:
    """
    Which store the evidence/bankability slice is pointed at.

    A SEPARATE switch from the auth slice on purpose: the point of a strangler
    migration is that slices flip independently, so a problem in one does not
    force a rollback of the other.
    """
    return (os.getenv("EVIDENCE_DB_BACKEND")
            or getattr(settings, "EVIDENCE_DB_BACKEND", SQLITE)).strip().lower()


def evidence_is_postgres() -> bool:
    return evidence_backend() == POSTGRES


def evidence_connection(company_id: str | None = None, sqlite_path: str | None = None):
    """
    Connection for the evidence slice, with an RLS tenant context when on
    PostgreSQL.

    Defaults to NO_TENANT_CONTEXT: these endpoints enforce access in the
    application layer (ABAC + project-stakeholder checks), but "the app checks
    it" was also true of every other slice, and it is not a reason for the
    database to hand over every tenant's rows if the app check is wrong. Pass a
    real company_id from request context; pass PLATFORM_ADMIN only for genuine
    platform-internal aggregation, and expect it in the log.
    """
    if evidence_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "evidence_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def capital_backend() -> str:
    """Which store slice 5 (capital bridge + development packages) uses."""
    return (os.getenv("CAPITAL_DB_BACKEND")
            or getattr(settings, "CAPITAL_DB_BACKEND", SQLITE)).strip().lower()


def capital_is_postgres() -> bool:
    return capital_backend() == POSTGRES


def capital_connection(company_id: str | None = None, sqlite_path: str | None = None):
    """Connection for slice 5, with an RLS tenant context on PostgreSQL."""
    if capital_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "capital_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def market_backend() -> str:
    """Which store slice 6 (marketplace / trading tail) uses."""
    return (os.getenv("MARKET_DB_BACKEND")
            or getattr(settings, "MARKET_DB_BACKEND", SQLITE)).strip().lower()


def market_is_postgres() -> bool:
    return market_backend() == POSTGRES


def market_connection(company_id: str | None = None, sqlite_path: str | None = None):
    """
    Connection for slice 6, with an RLS tenant context on PostgreSQL.

    Tenancy here is INDIRECT: capacities.id is the project id, and tokens ->
    offers -> matches chain off it (see migration 036). The policy resolves
    that; this just supplies the context.
    """
    if market_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "market_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def entitlement_backend() -> str:
    """Which store slice 6b-1 (entitlements) uses."""
    return (os.getenv("ENTITLEMENT_DB_BACKEND")
            or getattr(settings, "ENTITLEMENT_DB_BACKEND", SQLITE)).strip().lower()


def entitlement_is_postgres() -> bool:
    return entitlement_backend() == POSTGRES


def entitlement_connection(company_id: str | None = None,
                           sqlite_path: str | None = None):
    """
    Connection for the entitlements slice, with an RLS tenant context on
    PostgreSQL.

    Entitlement checks run WHILE deciding what a caller may see, so they cannot
    themselves be filtered by that decision — a genuine bootstrap. That makes
    PLATFORM_ADMIN legitimate HERE, but it must be passed explicitly (see
    app/core/entitlements.py) rather than arriving as a default that 64
    unrelated call sites also inherited.
    """
    if entitlement_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "entitlement_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def eventstore_backend() -> str:
    """Which store slice 6b-2 (the platform event ledger) uses."""
    return (os.getenv("EVENTSTORE_DB_BACKEND")
            or getattr(settings, "EVENTSTORE_DB_BACKEND", SQLITE)).strip().lower()


def eventstore_is_postgres() -> bool:
    return eventstore_backend() == POSTGRES


def eventstore_connection(company_id: str | None = None,
                          sqlite_path: str | None = None):
    """
    Connection for the event ledger.

    append_event() is called from inside operations that have already
    authorised themselves, and the ledger must be able to record an event for
    any project — so the WRITE path passes PLATFORM_ADMIN explicitly (see
    app/core/event_store.py). Readers should pass a real company_id.
    """
    if eventstore_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "eventstore_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fuelref_backend() -> str:
    """Which store slice 6b-3 (fuel reference data) uses."""
    return (os.getenv("FUELREF_DB_BACKEND")
            or getattr(settings, "FUELREF_DB_BACKEND", SQLITE)).strip().lower()


def fuelref_is_postgres() -> bool:
    return fuelref_backend() == POSTGRES


def fuelref_connection(company_id: str | None = None, sqlite_path: str | None = None):
    """Connection for the fuel reference tables — readable by any tenant.

    Needs no tenant context: the reference-data policies do not consult the
    company, so the default sentinel reads all 10 fuels and 120 conversions.
    """
    if fuelref_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "fuelref_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def governance_backend() -> str:
    """Which store slice 6b-4 (governance / access control) uses."""
    return (os.getenv("GOVERNANCE_DB_BACKEND")
            or getattr(settings, "GOVERNANCE_DB_BACKEND", SQLITE)).strip().lower()


def governance_is_postgres() -> bool:
    return governance_backend() == POSTGRES


def governance_connection(company_id: str | None = None,
                          sqlite_path: str | None = None):
    """
    Connection for approval policies, SoD, permission overrides, signing keys
    and data-residency policies.

    These tables are read WHILE deciding whether an action is permitted, so
    they cannot be filtered by that decision — the same bootstrap as
    entitlements. The policy-evaluation callers pass PLATFORM_ADMIN explicitly;
    anything else gets no tenant context and sees only the globally-readable
    rules (approval_policies, sod_conflict_pairs), which is correct.
    """
    if governance_is_postgres():
        return PostgresConnection(settings.DATABASE_URL,
                                  company_id=_tenant_context(company_id, "governance_connection"))
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def auth_connection(sqlite_path: str | None = None):
    """Open a connection to whichever store the auth slice is pointed at."""
    if is_postgres():
        return PostgresConnection(settings.DATABASE_URL)
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
