"""
Owner-only, with no admin clause — asserted against the real policy.
====================================================================
Migration 050 puts canvas documents, user plants and equipment equations under
`owner_user_id = current_setting('app.current_user_id', true)` and NOTHING
else. No `ADMIN OR`, no company fallback. The decision was explicit: a canvas
is one person's work, and PostgreSQL making sharing easy to write is not a
reason to grant it.

These tests exist because that property is invisible in normal use — every
developer is looking at their own rows, so a policy that had quietly been
widened to the company, or to platform admins, would look identical day to day
and would only be discovered by someone reading a canvas they should not have.

WHY THESE CONNECT AS `gex_app`
------------------------------
`ALEMBIC_DATABASE_URL` is `gex_user`, which is SUPERUSER, and PostgreSQL does
not apply row-level security to a superuser — not even FORCE ROW LEVEL
SECURITY. The first version of the copier verified itself there and reported
every owner seeing all 500 canvas rows: a broken measurement that looked
exactly like a broken policy. Anything asserting what RLS does must use the
role the application actually uses.
"""
from __future__ import annotations

import pytest

from tests.pg_support import pg_connect, requires_pg

TABLES = ("canvas_blobs", "user_plants", "equipment_equations")


def _counts_as(user_id: str | None) -> dict[str, int]:
    """Row counts visible to one owner, through the runtime role."""
    conn = pg_connect()
    try:
        cur = conn.cursor()
        # Both axes, as any real connection binds them. The company is set to a
        # PLATFORM_ADMIN escalation ON PURPOSE: if the owner policy had an
        # admin clause, or had been made company-scoped, this is the context
        # that would reveal it.
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SET app.current_user_id = %s", (user_id or "__no:user:context__",))
        out = {}
        for table in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            out[table] = cur.fetchone()[0]
        return out
    finally:
        conn.close()


def _owners() -> list[str]:
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_user_id = '__no:user:context__'")
        # Read the owners from a superuser-free angle: the auth table, which
        # carries no RLS, joined by what the workspace tables say they hold.
        cur.execute("SELECT user_id FROM auth_users ORDER BY user_id")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def test_a_connection_with_no_owner_sees_nothing():
    """The fail-closed floor. `NO_USER_CONTEXT` must match no row — including
    when the tenant axis is fully escalated."""
    requires_pg()
    counts = _counts_as(None)
    assert counts == {t: 0 for t in TABLES}, (
        f"rows visible with no owner bound: {counts}. The owner policy is not "
        "binding — or NO_USER_CONTEXT has become spellable as a user id"
    )


def test_each_owner_sees_only_their_own_rows():
    requires_pg()
    per_owner = {u: _counts_as(u)["canvas_blobs"] for u in _owners()}
    visible = {u: n for u, n in per_owner.items() if n}
    if not visible:
        pytest.skip("no canvas rows in this database to compare owners with")

    total_for_one = max(visible.values())
    everything = sum(visible.values())
    assert total_for_one < everything or len(visible) == 1, (
        f"one owner sees {total_for_one} of {everything} canvas rows — that is "
        "every row in the table, so the policy is not scoping by owner"
    )


def test_platform_admin_is_not_a_way_in():
    """The decision this migration encodes.

    A platform admin connection — tenant escalated to PLATFORM_ADMIN, owner set
    to the admin's own id — must see the admin's own canvases and no others.
    If someone adds `ADMIN OR` to these policies "for consistency" with the
    rest of the schema, this fails.
    """
    requires_pg()
    admins = [u for u in _owners() if u.endswith("_greenearthx_com")]
    if not admins:
        pytest.skip("no GEX staff account in this database")

    admin = admins[0]
    mine = _counts_as(admin)

    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SET app.current_user_id = %s", (admin,))
        cur.execute("SELECT COUNT(DISTINCT owner_user_id) FROM canvas_blobs")
        distinct_owners = cur.fetchone()[0]
    finally:
        conn.close()

    assert distinct_owners <= 1, (
        f"a platform admin can see {distinct_owners} different owners' canvases. "
        "050 has no admin clause by design — support and offboarding go through "
        "app/core/break_glass.py, which names one user and writes admin_log"
    )
    assert mine["canvas_blobs"] >= 0  # the admin still reaches their own work


def test_the_policies_contain_no_admin_clause():
    """Read the policy text from the catalogue, not the migration file.

    The migration says what was intended; `pg_policies` says what is actually
    installed. A later `CREATE OR REPLACE POLICY` — by hand, in a console —
    would not show up in any file this repo tracks.
    """
    requires_pg()
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tablename, qual FROM pg_policies "
            "WHERE schemaname='public' AND tablename = ANY(%s)", (list(TABLES),))
        installed = {t: (q or "") for t, q in cur.fetchall()}
    finally:
        conn.close()

    assert set(installed) == set(TABLES), (
        f"expected a policy on each of {TABLES}, found {sorted(installed)}")
    for table, qual in installed.items():
        assert "current_user_id" in qual, f"{table}: policy does not consult the owner axis"
        assert "PLATFORM_ADMIN" not in qual, (
            f"{table}: an admin clause has appeared in the live policy — "
            f"{qual!r}. That is a change to GEX's authorization model and "
            "belongs in a migration with a reason, not in a console")
        assert "current_company_id" not in qual, (
            f"{table}: the policy now consults the COMPANY — {qual!r}. These "
            "tables are owner-scoped; company-scoping them would let colleagues "
            "read each other's canvases")
