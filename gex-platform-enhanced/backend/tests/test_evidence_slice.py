"""
Evidence & bankability slice guardrails.
========================================
Strangler slice 4. Three properties matter, in this order:

1. **The hash chain survives the move.** evidence_ledger is tamper-evident: each
   row's digest covers its own fields, both actors, both state axes, AND the
   previous hash. A chain that cannot be validated in its new store is worse
   than no chain — it reads as integrity while providing none. So the chain is
   built and validated in PostgreSQL, then deliberately tampered with.

2. **Both backends return the same answers.** The whole point of the shim is
   that the SAME SQL runs either side. If the two disagree, the flip is unsafe.

3. **RLS isolates investor-facing data.** The migration plan calls this the
   highest-value slice under RLS.

Postgres tests skip cleanly when no database is reachable.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from pg_support import as_platform_admin, pg_admin as _pg, requires_pg

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

SLICE_TABLES = (
    "bankability_evidence",
    "bankability_snapshots",
    "evidence_documents",
    "evidence_events",
    "evidence_ledger",
)




# ── 1. The hash chain ───────────────────────────────────────────────────────

def _write_chain(cur, n=3, project_id="proj_hamburgone_emethanol", prefix="gtest"):
    from app.api.v1.evidence_ledger import _compute_hash

    prev = None
    for i in range(n):
        eid, ts = f"{prefix}-{i}", f"2026-08-08T10:0{i}:00Z"
        h = _compute_hash(eid, f"ent{i}", "PERMIT", f"doc{i}.pdf", prev, ts,
                          "UNVERIFIED", "asserted", "alice@x.io", None)
        cur.execute("""INSERT INTO evidence_ledger (evidence_id, project_id,
            entity_type, entity_id, category, document_ref, verification_state,
            claim_state, submitted_by, verified_by, hash, prev_hash, timestamp)
            VALUES (%s,%s,'project',%s,'PERMIT',%s,'UNVERIFIED','asserted',
                    'alice@x.io',NULL,%s,%s,%s)""",
                    (eid, project_id, f"ent{i}", f"doc{i}.pdf", h, prev, ts))
        prev = h


def _chain_valid(cur, prefix="gtest") -> bool:
    from app.api.v1.evidence_ledger import _verify_single

    cur.execute("SELECT * FROM evidence_ledger WHERE evidence_id LIKE %s "
                "ORDER BY timestamp", (f"{prefix}-%",))
    expected = None
    for row in cur.fetchall():
        if not _verify_single(row, expected):
            return False
        expected = row["hash"]
    return True


def test_the_hash_chain_validates_in_postgres():
    conn, cur = _pg()
    try:
        _write_chain(cur, prefix="gtest_valid")
        assert _chain_valid(cur, "gtest_valid"), (
            "a chain written to PostgreSQL does not validate — the digest is "
            "not reproducing across the store"
        )
    finally:
        cur.execute("DELETE FROM evidence_ledger WHERE evidence_id LIKE 'gtest_valid-%'")
        conn.commit()
        conn.close()


def test_a_silent_assurance_upgrade_breaks_the_chain():
    """
    The failure this protects against: someone edits verification_state to
    AUDITED in place. The document is unchanged, so a document-only digest would
    still verify — the artifact would be protected but the CLAIM about it would
    not.
    """
    conn, cur = _pg()
    try:
        _write_chain(cur, prefix="gtest_upg")
        assert _chain_valid(cur, "gtest_upg")
        cur.execute("UPDATE evidence_ledger SET verification_state='AUDITED' "
                    "WHERE evidence_id='gtest_upg-1'")
        assert not _chain_valid(cur, "gtest_upg"), (
            "an in-place assurance upgrade did NOT break the chain — the digest "
            "is not covering verification_state"
        )
    finally:
        cur.execute("DELETE FROM evidence_ledger WHERE evidence_id LIKE 'gtest_upg-%'")
        conn.commit()
        conn.close()


def test_rewriting_the_actor_breaks_the_chain():
    """Chain of custody without the custodian is not chain of custody."""
    conn, cur = _pg()
    try:
        _write_chain(cur, prefix="gtest_actor")
        cur.execute("UPDATE evidence_ledger SET submitted_by='mallory@x.io' "
                    "WHERE evidence_id='gtest_actor-1'")
        assert not _chain_valid(cur, "gtest_actor"), (
            "rewriting submitted_by did NOT break the chain"
        )
    finally:
        cur.execute("DELETE FROM evidence_ledger WHERE evidence_id LIKE 'gtest_actor-%'")
        conn.commit()
        conn.close()


def test_a_broken_link_breaks_the_chain():
    """Tampering with prev_hash must be detected even if each row self-verifies."""
    conn, cur = _pg()
    try:
        _write_chain(cur, prefix="gtest_link")
        cur.execute("UPDATE evidence_ledger SET prev_hash='deadbeef' "
                    "WHERE evidence_id='gtest_link-2'")
        assert not _chain_valid(cur, "gtest_link")
    finally:
        cur.execute("DELETE FROM evidence_ledger WHERE evidence_id LIKE 'gtest_link-%'")
        conn.commit()
        conn.close()


# ── 2. Both backends agree ──────────────────────────────────────────────────

def test_both_backends_return_the_same_evidence_counts(monkeypatch):
    """
    Read parity is the precondition for flipping. If the two stores disagree the
    flip is a coin toss, not a migration.
    """
    requires_pg()

    def counts(backend: str):
        monkeypatch.setenv("EVIDENCE_DB_BACKEND", backend)
        from app.api.v1.routes_bankability_proxy import _get_db

        # Whole-store comparison: it must see every row, so it asks as admin
        # explicitly. Since the shim's default became a deny sentinel, an
        # unscoped read on PostgreSQL correctly returns nothing.
        with as_platform_admin():
            conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT status, count(*) AS n FROM bankability_evidence "
                "GROUP BY status ORDER BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()

    try:
        lite, pg = counts("sqlite"), counts("postgres")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend unavailable: {exc}")
    assert lite == pg, f"backends disagree: sqlite={lite} postgres={pg}"


# ── 3. RLS on investor-facing data ──────────────────────────────────────────

def test_rls_is_enabled_and_forced_on_every_evidence_table():
    conn, cur = _pg()
    try:
        cur.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(%s)", (list(SLICE_TABLES),))
        found = {r["relname"]: r for r in cur.fetchall()}
        missing = [t for t in SLICE_TABLES if t not in found]
        assert not missing, f"tables absent from PostgreSQL: {missing}"
        for t, r in found.items():
            assert r["relrowsecurity"], f"{t}: RLS not enabled"
            assert r["relforcerowsecurity"], f"{t}: RLS not FORCED (owner bypasses)"
    finally:
        conn.close()


def test_an_unknown_company_sees_no_evidence():
    """The isolation that matters: investor-facing rows must not leak."""
    conn, cur = _pg()
    try:
        cur.execute("SET ROLE gex_app")
        cur.execute("SET app.current_company_id='acme_totally_unrelated'")
        for t in SLICE_TABLES:
            cur.execute(f"SELECT count(*) AS n FROM {t}")
            assert cur.fetchone()["n"] == 0, f"{t} leaked rows to an unknown company"
    finally:
        conn.rollback()
        conn.close()


def test_a_tenant_sees_less_than_platform_admin():
    conn, cur = _pg()
    try:
        cur.execute("SELECT count(*) AS n FROM bankability_evidence")
        total = cur.fetchone()["n"]
        cur.execute("SET ROLE gex_app")
        cur.execute("SET app.current_company_id='hamburgone_com'")
        cur.execute("SELECT count(*) AS n FROM bankability_evidence")
        tenant = cur.fetchone()["n"]
        assert 0 < tenant < total, (
            f"expected a tenant to see some but not all evidence; "
            f"tenant={tenant} total={total}"
        )
    finally:
        conn.rollback()
        conn.close()


# ── Unattributed evidence must not grow ─────────────────────────────────────

# `bankability_evidence.project_id` defaults to the literal 'default', so rows
# written before a project was supplied belong to a project that does not exist.
# Under RLS they are PLATFORM_ADMIN-only — effectively invisible. 39 such rows
# were migrated (38 evidence + 1 snapshot). This is a RATCHET: the debt may be
# paid down, never added to.
UNATTRIBUTED_BASELINE = 39


def test_unattributed_evidence_does_not_grow():
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT (SELECT count(*) FROM bankability_evidence e
                    WHERE NOT EXISTS (SELECT 1 FROM projects p
                                      WHERE p.project_id = e.project_id))
                 + (SELECT count(*) FROM bankability_snapshots s
                    WHERE NOT EXISTS (SELECT 1 FROM projects p
                                      WHERE p.project_id = s.project_id)) AS n
        """)
        n = cur.fetchone()["n"]
        assert n <= UNATTRIBUTED_BASELINE, (
            f"{n} rows reference a non-existent project (baseline "
            f"{UNATTRIBUTED_BASELINE}). New evidence must name a real project — "
            "unattributed rows are invisible to every tenant under RLS."
        )
    finally:
        conn.close()


# ── Schema ownership ────────────────────────────────────────────────────────

def test_init_db_does_not_create_the_ledger_on_postgres():
    """
    On PostgreSQL the schema (and its RLS) is owned by migration 034. A
    CREATE TABLE IF NOT EXISTS from application code would either no-op or
    create an unprotected table with no policies.
    """
    src = (APP / "api" / "v1" / "evidence_ledger.py").read_text()
    fn = src[src.index("def init_db("):]
    fn = fn[:fn.index("\ndef ") if "\ndef " in fn else len(fn)]
    assert "evidence_is_postgres" in fn and "return" in fn, (
        "init_db must short-circuit on PostgreSQL"
    )


def test_the_two_evidence_axes_are_not_merged():
    """
    verification_state (assurance) and claim_state (lifecycle) are ORTHOGONAL —
    an artifact can be AUDITED and SUPERSEDED at once. The migration must keep
    both columns.
    """
    conn, cur = _pg()
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='evidence_ledger'")
        cols = {r["column_name"] for r in cur.fetchall()}
        for required in ("verification_state", "claim_state", "verified_by",
                         "submitted_by", "valid_until", "superseded_by",
                         "hash", "prev_hash"):
            assert required in cols, f"evidence_ledger lost `{required}`"
    finally:
        conn.close()


def test_the_migration_does_not_silently_drop_columns():
    """Migration 034 must not have quietly narrowed the ledger."""
    mig = (BACKEND / "alembic" / "versions" / "034_evidence_slice.py").read_text()
    assert re.search(r"claim_state", mig), "034 lost the lifecycle axis"
    assert re.search(r"verified_by", mig), "034 lost the custody column"
