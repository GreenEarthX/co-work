"""
The shim's default tenant context must fail CLOSED.
===================================================
Every `*_connection()` accessor in app/core/db_backend.py used to default to
`company_id=PLATFORM_ADMIN`, and an audit of all 64 call sites found that not
one of them overrode it. 88 of the 93 RLS policies grant PLATFORM_ADMIN full
visibility.

So on the day the eight backend switches flip to PostgreSQL, those 64 sites
would have read every tenant's rows — and every RLS test would still have
passed, because the tests set their own context rather than using the
application's. Policies existing is not the same as policies binding.

The default is now `NO_TENANT_CONTEXT`, a sentinel that matches no
tenant-scoped policy. Admin is still reachable, but only by asking for it by
name, and asking is logged.

These tests pin the three properties that make that true:

  1. no accessor defaults to PLATFORM_ADMIN         (static, AST)
  2. the sentinel really denies tenant data, and    (live, as gex_app)
     really does NOT deny deliberately-public data
  3. explicit admin still works, and is logged      (live + caplog)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pg_support import pg_connect, requires_pg

BACKEND = Path(__file__).resolve().parents[1]
SHIM = BACKEND / "app" / "core" / "db_backend.py"

ACCESSORS = ["evidence_connection", "capital_connection", "market_connection",
             "entitlement_connection", "eventstore_connection",
             "fuelref_connection", "governance_connection"]

# Tenant-scoped: an unset context must see NOTHING here.
TENANT_SCOPED = ["projects", "finance_entitlements", "platform_events"]

# Deliberately public: their policies do not consult the company at all, so the
# sentinel must NOT break them. A "fail closed" change that also blackholes the
# fuel catalogue would be traded for a different outage.
PUBLIC = {"fuel_catalog": 10, "fuel_unit_conversions": 120,
          "approval_policies": 8, "sod_conflict_pairs": 8}


def _as_role_and_company(company: str, table: str) -> int:
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()


# ── 1. Static: the default may never be PLATFORM_ADMIN again ────────────────

def test_no_accessor_defaults_to_platform_admin():
    """
    Over the AST, not the text — this file and the shim both discuss
    PLATFORM_ADMIN at length, and guardrails in this repo have matched their own
    prose before.
    """
    tree = ast.parse(SHIM.read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ACCESSORS:
            continue
        args = node.args
        defaults = dict(zip([a.arg for a in args.args[-len(args.defaults):]],
                            args.defaults)) if args.defaults else {}
        defaults.update({a.arg: d for a, d in zip(args.kwonlyargs, args.kw_defaults) if d})
        d = defaults.get("company_id")
        if isinstance(d, ast.Name) and d.id == "PLATFORM_ADMIN":
            offenders.append(f"{node.name} (line {node.lineno})")
        elif isinstance(d, ast.Constant) and d.value == "PLATFORM_ADMIN":
            offenders.append(f"{node.name} (line {node.lineno}, literal)")

    assert not offenders, (
        "these accessors default to PLATFORM_ADMIN, which disables tenant "
        f"isolation for every caller that does not override it: {offenders}. "
        "Default to NO_TENANT_CONTEXT and pass PLATFORM_ADMIN explicitly where "
        "a genuine bootstrap needs it."
    )


def test_every_accessor_still_has_a_company_id_parameter():
    """Deleting the parameter would 'fix' the test above while removing the
    ability to scope at all."""
    tree = ast.parse(SHIM.read_text())
    found = {n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in ACCESSORS
             and any(a.arg == "company_id" for a in n.args.args + n.args.kwonlyargs)}
    assert found == set(ACCESSORS), f"missing company_id: {set(ACCESSORS) - found}"


def test_admin_escalation_is_routed_through_the_logging_helper():
    """Constructing PostgresConnection directly would bypass the audit log."""
    src = SHIM.read_text()
    tree = ast.parse(src)
    unlogged = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ACCESSORS:
            continue
        seg = ast.get_source_segment(src, node) or ""
        if "PostgresConnection(" in seg and "_tenant_context(" not in seg:
            unlogged.append(node.name)
    assert not unlogged, f"{unlogged} open a connection without _tenant_context()"


# ── 2. Live: the sentinel denies the right things, and only those ───────────

@pytest.mark.parametrize("table", TENANT_SCOPED)
def test_the_sentinel_sees_no_tenant_scoped_rows(table):
    from app.core.db_backend import NO_TENANT_CONTEXT

    n = _as_role_and_company(NO_TENANT_CONTEXT, table)
    assert n == 0, (
        f"{table}: an unset tenant context sees {n} rows. The default must "
        "reveal nothing tenant-scoped."
    )


@pytest.mark.parametrize("table", TENANT_SCOPED)
def test_the_sentinel_is_measurably_more_restrictive_than_admin(table):
    """
    Zero rows is only meaningful if admin would have seen some. Without this,
    an empty table would make the test above pass vacuously.
    """
    from app.core.db_backend import NO_TENANT_CONTEXT

    admin = _as_role_and_company("PLATFORM_ADMIN", table)
    if admin == 0:
        pytest.skip(f"{table} is empty — nothing to withhold")
    assert _as_role_and_company(NO_TENANT_CONTEXT, table) < admin


@pytest.mark.parametrize("table,expected", sorted(PUBLIC.items()))
def test_deliberately_public_data_survives_the_sentinel(table, expected):
    from app.core.db_backend import NO_TENANT_CONTEXT

    n = _as_role_and_company(NO_TENANT_CONTEXT, table)
    assert n == expected, (
        f"{table}: the sentinel reduced a deliberately-public table to {n} of "
        f"{expected} rows. Failing closed must not blackhole reference data."
    )


def test_the_sentinel_is_not_a_value_any_real_company_could_hold():
    """
    If a tenant could be named `__no_tenant_context__` it would inherit whatever
    the sentinel can reach. Company slugs are `[a-z0-9_]`, so this is a real
    (if unlikely) collision — assert no tenant holds it.
    """
    from app.core.db_backend import NO_TENANT_CONTEXT

    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM tenants WHERE company_id = %s",
                    (NO_TENANT_CONTEXT,))
        assert cur.fetchone()[0] == 0, "a real tenant is using the sentinel value"
    finally:
        conn.close()


# ── 3. Explicit admin still works, and says so ──────────────────────────────

def test_explicit_admin_still_reaches_everything(monkeypatch):
    # Reaches PostgreSQL through the app shim, not psycopg2 directly, so the
    # reachability check has to be explicit — an outage must skip, not fail.
    requires_pg()
    monkeypatch.setenv("ENTITLEMENT_DB_BACKEND", "postgres")
    from app.core.db_backend import PLATFORM_ADMIN, entitlement_connection

    conn = entitlement_connection(company_id=PLATFORM_ADMIN)
    try:
        n = conn.execute("SELECT count(*) AS n FROM finance_entitlements").fetchone()["n"]
    finally:
        conn.close()
    assert n > 0, "explicit PLATFORM_ADMIN no longer reaches the data"


def test_admin_escalation_is_logged(monkeypatch, caplog):
    """An unlogged escalation is an escalation nobody will find."""
    import logging

    requires_pg()
    monkeypatch.setenv("ENTITLEMENT_DB_BACKEND", "postgres")
    import app.core.db_backend as dbb

    dbb._announced_admin.clear()  # the warning is deduplicated per call site
    with caplog.at_level(logging.WARNING, logger="gex.db_backend"):
        conn = dbb.entitlement_connection(company_id=dbb.PLATFORM_ADMIN)
        conn.close()
    assert any("tenant isolation disabled" in r.message.lower() or
               "PLATFORM_ADMIN" in r.getMessage() for r in caplog.records), (
        "opening a PLATFORM_ADMIN connection produced no warning"
    )
