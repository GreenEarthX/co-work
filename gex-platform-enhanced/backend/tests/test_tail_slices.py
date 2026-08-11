"""
Slices 6b-5 and 6b-6 guardrails — chained ledgers and the domain tail.
======================================================================
42 live tables migrated together: 7 hash-chained ledgers (6b-5) and 35 plain
domain tables (6b-6). All but four are empty, so this is mostly schema.

Two things are worth guarding beyond "the rows arrived":

1. **Each chained ledger must be verifiable in PostgreSQL.** They are empty
   today, which is the cheap moment — a chain that cannot be validated in its
   new store is worse than no chain, and the package-event log already showed
   how a chain can be broken in a way nobody notices for months.

2. **Nothing without a project_id may be tenant-readable.** 9 of the 35 have no
   project column, so no honest tenant policy exists for them. They are
   admin-only, and that must not quietly become "open".

Also pinned: the 12 tables deliberately NOT migrated, so a later slice cannot
sweep them in without a decision.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from pg_support import pg_admin as _pg, pg_connect, requires_pg

CHAINED = [
    "carbon_attribution_event_log",
    "dfi_criteria_events",
    "drawdown_schedule_events",
    "mass_balance_allocations",
    "settlement_event_log",
    "sovereign_instrument_events",
    "spend_wave_events",
]

# No reference anywhere in app/ — no DDL, no query. Excluded on purpose.
DELIBERATELY_NOT_MIGRATED = [
    "covenant_compliance", "drawdown_tranches", "equity_contributions",
    "financial_metrics", "pre_cod_metric_snapshots", "project_events",
    "project_stakeholders", "project_states", "reserve_accounts",
    "service_calls", "state_transitions", "workflow_checkpoints",
]




# ── 6b-5: every chained ledger verifies, and detects tampering ──────────────

@pytest.mark.parametrize("table", CHAINED)
def test_each_chained_ledger_validates_and_detects_tampering(table):
    """
    Writes a 3-link chain into the real PostgreSQL table, validates it, then
    mutates the link and confirms the chain no longer verifies.

    Everything is DERIVED from the schema — primary key, digest column name,
    and the NOT NULL columns that must be filled. Hardcoding them was the first
    version of this test and it failed on five of seven ledgers, because each
    carries its own required foreign key (criterion_id, drawdown_id,
    settlement_id, instrument_id, spend_wave_id, lot_id) and one names its
    digest `allocation_hash` rather than `event_hash`.

    The property under test is the one `development_package_events` lacks: a
    stored row's digest must be reproducible from the stored values.
    """
    conn, cur = _pg()
    prefix = f"gt_{table[:14]}"
    try:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns WHERE table_name=%s
        """, (table,))
        meta = {r["column_name"]: r for r in cur.fetchall()}
        assert meta, f"{table} is absent from PostgreSQL"

        cur.execute("""
            SELECT a.attname FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid
                               AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary
        """, (table,))
        pks = [r["attname"] for r in cur.fetchall()]
        pk = pks[0]

        hashcol = next(c for c in meta if c.endswith("_hash") and c != "prev_hash")
        required = [c for c, m in meta.items()
                    if m["is_nullable"] == "NO" and c not in (pk, hashcol, "prev_hash")]

        def digest(i, prev):
            return hashlib.sha256(f"{prefix}{i}{prev or ''}".encode()).hexdigest()

        def filler(col):
            if col == "project_id":
                return "proj_bremen_h2"
            t = meta[col]["data_type"]
            if t in ("integer", "bigint", "smallint"):
                return 1
            if t in ("double precision", "numeric", "real"):
                return 1.0
            if t == "boolean":
                return False
            return "gt"

        prev = None
        for i in range(3):
            row = {pk: f"{prefix}-{i}", hashcol: digest(i, prev), "prev_hash": prev}
            for c in required:
                row[c] = filler(c)
            names = ", ".join(f'"{c}"' for c in row)
            binds = ", ".join(f"%({c})s" for c in row)
            cur.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", row)
            prev = row[hashcol]
        conn.commit()

        def valid():
            cur.execute(f'SELECT "{pk}", "{hashcol}", prev_hash FROM {table} '
                        f'WHERE "{pk}"::text LIKE %s ORDER BY "{pk}"',
                        (f"{prefix}-%",))
            exp = None
            for i, r in enumerate(cur.fetchall()):
                if r[hashcol] != digest(i, exp) or r["prev_hash"] != exp:
                    return False
                exp = r[hashcol]
            return True

        assert valid(), f"{table}: a freshly written chain does not validate"
        cur.execute(f'UPDATE {table} SET prev_hash=%s WHERE "{pk}"=%s',
                    ("tampered", f"{prefix}-1"))
        assert not valid(), f"{table}: tampering with prev_hash went undetected"
    finally:
        cur.execute(f'DELETE FROM {table} WHERE "{pk}"::text LIKE %s', (f"{prefix}-%",))
        conn.commit()
        conn.close()


def test_every_chained_ledger_has_both_chain_columns():
    """A ledger missing prev_hash is not chained, whatever it is called."""
    conn, cur = _pg()
    try:
        for t in CHAINED:
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_name=%s", (t,))
            cols = {r["column_name"] for r in cur.fetchall()}
            assert cols, f"{t} is absent from PostgreSQL"
            assert "prev_hash" in cols, f"{t} lost prev_hash"
            # The digest column is not uniformly named — mass_balance_allocations
            # calls it allocation_hash. What matters is that one exists.
            digests = {c for c in cols if c.endswith("_hash") and c != "prev_hash"}
            assert digests, f"{t} lost its digest column"
    finally:
        conn.close()


# ── 6b-6: nothing unscoped may be tenant-readable ───────────────────────────

def test_tables_without_a_project_id_are_admin_only():
    """
    9 of the 35 have no project column, so no honest tenant policy exists. They
    are admin-only — the same call made for tb_* in 036. A policy that only
    appears to isolate is worse than none.
    """
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT p.tablename, p.qual
            FROM pg_policies p
            WHERE p.schemaname = 'public'
              AND p.policyname LIKE '%_tenant_isolation'
              AND NOT EXISTS (
                  SELECT 1 FROM information_schema.columns c
                  WHERE c.table_name = p.tablename AND c.column_name = 'project_id')
        """)
        for r in cur.fetchall():
            qual = r["qual"] or ""
            assert "PLATFORM_ADMIN" in qual, (
                f"{r['tablename']} has no project_id yet its policy is not "
                f"admin-scoped: {qual[:120]}"
            )
            assert "true" != qual.strip().lower(), (
                f"{r['tablename']} is wide open"
            )
    finally:
        conn.close()


def test_an_unknown_company_sees_nothing_in_the_tail():
    import psycopg2

    requires_pg()
    sample = ["gateway_registry", "pre_cod_snapshots", "risk_flag_events",
              "risk_flag_status", "settlement_events", "pathway_claims"]
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id='acme_totally_unrelated'")
        for t in sample:
            cur.execute(f"SELECT count(*) FROM {t}")
            assert cur.fetchone()[0] == 0, f"{t} leaked to an unknown company"
    finally:
        conn.rollback()
        conn.close()


def test_rls_is_forced_on_every_migrated_tail_table():
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
              AND EXISTS (SELECT 1 FROM pg_policies p
                          WHERE p.tablename = c.relname
                            AND p.policyname LIKE '%_tenant_isolation')
        """)
        weak = [r["relname"] for r in cur.fetchall()
                if not (r["relrowsecurity"] and r["relforcerowsecurity"])]
        assert not weak, f"RLS enabled but not FORCED on {weak} — the owner bypasses"
    finally:
        conn.close()


# ── The exclusion is a decision, and must stay one ──────────────────────────

def test_the_dead_tables_were_not_migrated():
    """
    12 tables have no reference anywhere in app/ — no DDL, no query. Migrating
    them would make them look alive. They are slice 6b-7's create-or-drop
    decision, and a later bulk sweep must not quietly adopt them.
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name = ANY(%s)",
                    (DELIBERATELY_NOT_MIGRATED,))
        adopted = [r["table_name"] for r in cur.fetchall()]
        assert not adopted, (
            f"{adopted} were migrated despite having no reference in app/. "
            "Either they are live (fix the exclusion list) or they should be "
            "dropped — but they must not be migrated by default."
        )
    finally:
        conn.close()


QUARANTINE_SUFFIX = "_quarantined_20260809"


def test_the_dead_tables_are_quarantined_not_dropped():
    """
    2026-08-09: the 6b-7 decision was taken — quarantine, not DROP.

    All 12 were renamed with a dated suffix rather than deleted. Reversible,
    costs nothing (they were empty), and it proves the absence of callers over
    a real release cycle rather than by grep alone. Backup:
    data/db_backups/gex_platform.pre-quarantine.20260809.db

    Drop them at the next release if nothing breaks — and delete this test then.
    """
    import sqlite3

    from app.core.config import settings

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

    missing = [t for t in DELIBERATELY_NOT_MIGRATED
               if t + QUARANTINE_SUFFIX not in names]
    assert not missing, (
        f"{missing} are neither live nor quarantined — they were DROPPED. The "
        "decision was to quarantine so the change stays reversible."
    )
    revived = [t for t in DELIBERATELY_NOT_MIGRATED if t in names]
    assert not revived, (
        f"{revived} exist under their original name again. If they are genuinely "
        "needed, migrate them properly and remove them from this list — do not "
        "let a dead table come back by accident."
    )
