"""
Slice 6 guardrails — marketplace / trading tail.
================================================
The plan calls this slice "mechanical". The copy was; the RLS was not, because
none of these tables has a `project_id`.

TENANCY IS IMPLICIT IN AN OVERLOADED PRIMARY KEY
    capacities.id IS a project id — nothing in the schema says so. The chain
    tokens -> offers -> matches hangs off it, so isolation has to be resolved
    three joins deep via app_company_can_see_capacity().

That indirection is the thing most likely to be broken by a later edit, and the
thing least likely to be noticed — which is what these tests are for. `tokens`
carries the green claim, so a leak here is the worst kind in the platform.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_admin as _pg, pg_connect

MARKET_TABLES = ("capacities", "tokens", "offers", "matches", "buyer_mandates")
TB_TABLES = (
    "tb_asset", "tb_counterparty", "tb_index_definition", "tb_index_history",
    "tb_contract", "tb_contract_fixed_price", "tb_contract_index_linked",
    "tb_project_finance_link",
)




def _seed_chain(cur):
    """capacity(proj_bremen_h2) -> token -> offer -> match."""
    cur.execute("INSERT INTO tokens (id, capacity_id, lifecycle_state) "
                "VALUES ('gt_tk','proj_bremen_h2','MINTED') ON CONFLICT (id) DO NOTHING")
    cur.execute("INSERT INTO offers (id, token_id) VALUES ('gt_of','gt_tk') "
                "ON CONFLICT (id) DO NOTHING")
    cur.execute("INSERT INTO matches (id, offer_id) VALUES ('gt_mt','gt_of') "
                "ON CONFLICT (id) DO NOTHING")


def _drop_chain(cur):
    cur.execute("DELETE FROM matches WHERE id='gt_mt'")
    cur.execute("DELETE FROM offers WHERE id='gt_of'")
    cur.execute("DELETE FROM tokens WHERE id='gt_tk'")


def _counts_as(dsn_company: str):
    import psycopg2

    conn = pg_connect()
    cur = conn.cursor()
    cur.execute("BEGIN")
    cur.execute("SET LOCAL ROLE gex_app")
    cur.execute("SET LOCAL app.current_company_id = %s", (dsn_company,))
    out = {}
    for t in MARKET_TABLES[:4]:
        cur.execute(f"SELECT count(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    conn.rollback()
    conn.close()
    return out


# ── The indirect chain actually isolates ────────────────────────────────────

def test_the_marketplace_chain_isolates_three_joins_deep():
    """
    proj_bremen_h2 is owned by heliosnord_gmbh, with allianz as an associated
    company. An unrelated tenant must see NONE of the chain — not the capacity,
    not the token, not the offer, not the match.
    """
    conn, cur = _pg()
    try:
        _seed_chain(cur)
        conn.commit()

        owner = _counts_as("heliosnord_gmbh")
        granted = _counts_as("allianz")
        stranger = _counts_as("etfuels_sa")
        unknown = _counts_as("acme_totally_unrelated")

        assert owner["capacities"] >= 1 and owner["tokens"] == 1, owner
        assert owner["offers"] == 1 and owner["matches"] == 1, owner
        assert granted["tokens"] == 1, "a company WITH project access lost the chain"

        for label, counts in (("etfuels_sa", stranger), ("unknown", unknown)):
            assert all(v == 0 for v in counts.values()), (
                f"{label} can see marketplace rows for a project it has no "
                f"access to: {counts}"
            )
    finally:
        _drop_chain(cur)
        conn.commit()
        conn.close()


def test_a_token_with_no_capacity_is_visible_to_nobody_but_admin():
    """
    Fails closed. An orphan token (capacity_id NULL or dangling) resolves to no
    project, so no tenant may see it — a token whose provenance cannot be
    established must not leak.
    """
    conn, cur = _pg()
    try:
        cur.execute("INSERT INTO tokens (id, capacity_id, lifecycle_state) "
                    "VALUES ('gt_orphan', NULL, 'MINTED') ON CONFLICT (id) DO NOTHING")
        conn.commit()
        for company in ("heliosnord_gmbh", "allianz", "etfuels_sa"):
            import psycopg2

            c2 = pg_connect()
            k = c2.cursor()
            k.execute("BEGIN")
            k.execute("SET LOCAL ROLE gex_app")
            k.execute("SET LOCAL app.current_company_id = %s", (company,))
            k.execute("SELECT count(*) FROM tokens WHERE id='gt_orphan'")
            assert k.fetchone()[0] == 0, f"{company} can see an orphan token"
            c2.rollback()
            c2.close()
    finally:
        cur.execute("DELETE FROM tokens WHERE id='gt_orphan'")
        conn.commit()
        conn.close()


def test_rls_is_enabled_and_forced_on_every_marketplace_table():
    conn, cur = _pg()
    try:
        cur.execute("SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(%s)",
                    (list(MARKET_TABLES + TB_TABLES),))
        found = {r["relname"]: r for r in cur.fetchall()}
        missing = [t for t in MARKET_TABLES + TB_TABLES if t not in found]
        assert not missing, f"absent from PostgreSQL: {missing}"
        for t, r in found.items():
            assert r["relrowsecurity"], f"{t}: RLS not enabled"
            assert r["relforcerowsecurity"], f"{t}: RLS not FORCED"
    finally:
        conn.close()


def test_trading_book_tables_are_admin_only_until_assets_name_a_project():
    """
    tb_asset has no external reference — the same gap that makes the
    trading-book cashflow endpoint reject GEX project slugs. There is no honest
    tenant policy to write, so they are locked to PLATFORM_ADMIN rather than
    left open or given a policy that only appears to isolate.

    When the asset-to-project bridge lands, this test should be replaced with a
    real isolation test.
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT tablename, policyname, qual FROM pg_policies "
                    "WHERE schemaname='public' AND tablename = ANY(%s)",
                    (list(TB_TABLES),))
        pols = {r["tablename"]: r for r in cur.fetchall()}
        assert set(pols) == set(TB_TABLES), (
            f"trading-book tables without a policy: {set(TB_TABLES) - set(pols)}"
        )
        for t, p in pols.items():
            assert "PLATFORM_ADMIN" in (p["qual"] or ""), f"{t}: not admin-scoped"
            assert "app_company" not in (p["qual"] or ""), (
                f"{t}: claims project-based isolation, but tb_asset cannot name "
                "a project — that policy would be decorative"
            )
    finally:
        conn.close()


# ── The overloaded key is documented, not just relied upon ──────────────────

def test_every_capacity_id_is_a_real_project():
    """
    The premise the whole RLS chain rests on. If a capacity id stops being a
    project id, isolation silently degrades to "nobody sees it" — fail-closed,
    but broken.
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT c.id FROM capacities c WHERE NOT EXISTS "
                    "(SELECT 1 FROM projects p WHERE p.project_id = c.id)")
        orphans = [r["id"] for r in cur.fetchall()]
        assert not orphans, (
            f"capacity ids that are not projects: {orphans}. The RLS chain "
            "resolves capacities.id AS a project id — these rows are invisible "
            "to every tenant."
        )
    finally:
        conn.close()


def test_the_capacity_resolver_exists_and_is_hardened():
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT prosecdef, proconfig FROM pg_proc
            WHERE proname = 'app_company_can_see_capacity'
        """)
        row = cur.fetchone()
        assert row, "app_company_can_see_capacity is missing — the chain is broken"
        assert row["prosecdef"], "must be SECURITY DEFINER or the policy recurses"
        assert any("search_path" in c for c in (row["proconfig"] or [])), (
            "SECURITY DEFINER without a pinned search_path is a privilege-"
            "escalation vector"
        )
    finally:
        conn.close()


# ── Token lifecycle survived the move ───────────────────────────────────────

def test_the_token_lifecycle_domain_is_constrained_in_postgres():
    """
    The 2026-08-07 ruling — a green claim is made once — is enforced in Python
    by TOKEN_TRANSITIONS. The database should not accept a state outside the
    domain either.
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
                    "WHERE conname = 'ck_tokens_lifecycle_state'")
        row = cur.fetchone()
        assert row, "tokens lost its lifecycle_state CHECK constraint"
        for state in ("MINTED", "RESERVED", "MATCHED", "SETTLED", "RETIRED",
                      "ANNULLED", "VOIDED"):
            assert state in row["def"], f"{state} missing from the CHECK"
    finally:
        conn.close()


def test_postgres_rejects_an_unknown_token_state():
    conn, cur = _pg()
    try:
        with pytest.raises(Exception):
            cur.execute("INSERT INTO tokens (id, lifecycle_state) "
                        "VALUES ('gt_bad', 'UNRETIRED')")
        conn.rollback()
    finally:
        conn.close()


def test_the_annulment_columns_survived_the_migration():
    """The accountability columns added on 2026-08-07 must all be present."""
    conn, cur = _pg()
    try:
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='tokens'")
        cols = {r["column_name"] for r in cur.fetchall()}
        for c in ("retired_by", "retired_at", "retirement_evidence_ref",
                  "annulment_event_id", "annulled_by", "annulment_reason",
                  "annulment_authority_ref", "supersedes_retirement_event_id"):
            assert c in cols, f"tokens lost `{c}` in the migration"
    finally:
        conn.close()


# ── Known gap, pinned so it is not forgotten ────────────────────────────────

def test_the_contracts_table_is_still_missing_on_BOTH_backends():
    """
    ⚠ PINNED DEFECT. `contracts_sqlite.py` is routed and queries a `contracts`
    table that has NO DDL anywhere in app/ and exists in neither store.
    /api/v1/contracts/summary returns 500 today.

    It was NOT created during the migration: doing so would make PostgreSQL
    work while SQLite still failed, breaking the backend-parity gate every
    slice is verified against. Fix it as its own change — then delete this test.

    Pinned symmetrically so the two backends cannot silently diverge.
    """
    import sqlite3

    from app.core.config import settings

    lite = sqlite3.connect(settings.SQLITE_DB_PATH)
    in_sqlite = lite.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='contracts'"
    ).fetchone() is not None
    lite.close()

    conn, cur = _pg()
    try:
        cur.execute("SELECT to_regclass('public.contracts') AS t")
        in_pg = cur.fetchone()["t"] is not None
    finally:
        conn.close()

    assert in_sqlite == in_pg, (
        f"`contracts` exists in only one store (sqlite={in_sqlite}, "
        f"postgres={in_pg}) — the backends have diverged"
    )
    assert not in_sqlite, (
        "`contracts` now exists — good. Fix contracts_sqlite.py, confirm "
        "/api/v1/contracts/summary returns 200, and delete this test."
    )
