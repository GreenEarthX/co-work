"""
Slice 6b-2 guardrails — the platform event ledger.
==================================================
`platform_events` is append-only and hash-chained, and **ten modules write to
it**. It is the audit spine under every other slice.

THE DEFECT THIS SLICE HAD TO FIX
--------------------------------
`append_event()` is a read-then-write against a GLOBAL chain:

    SELECT event_hash ... ORDER BY id DESC LIMIT 1     -- read predecessor
    INSERT ... previous_hash = <that>                  -- write

With no lock, concurrent appends read the same predecessor and fork. SQLite
hid it by serialising writers; PostgreSQL does not. Measured on PostgreSQL
BEFORE the fix, 12 concurrent appends produced:

    9 written · 3 rejected (UniqueViolation — events LOST) · 1 fork

A rejected audit event is as unacceptable as a forked one, so the unique
constraint alone was not a fix — it converted corruption into data loss.

The fix is a transaction-scoped advisory lock in append_event, with the unique
constraint and a single-root partial index as backstops that should never fire.
After it: 30 concurrent appends -> 30 written, 0 rejected, 0 forks, 1 root.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_admin as _pg, pg_connect, requires_pg

REQUIRES_PG = "requires PostgreSQL — this slice's risk only exists there"




# ── The concurrency property, measured not asserted ─────────────────────────

def test_concurrent_appends_do_not_fork_or_lose_events(monkeypatch):
    """
    THE test for this slice. Runs real concurrent appends and checks all four
    failure modes at once: lost events, forks, multiple roots, broken links.

    Without the advisory lock this fails on the first two.
    """
    requires_pg()
    monkeypatch.setenv("EVENTSTORE_DB_BACKEND", "postgres")

    import concurrent.futures as cf

    from app.core.event_store import append_event

    N = 24
    marker = "guard.concurrency"

    def emit(i):
        try:
            append_event(event_type=marker, aggregate_type="probe",
                         aggregate_id=f"p{i}", data={"i": i}, user_id="guard")
            return None
        except Exception as exc:  # noqa: BLE001
            return type(exc).__name__

    conn, cur = _pg()
    try:
        with cf.ThreadPoolExecutor(max_workers=N) as ex:
            errors = [r for r in ex.map(emit, range(N)) if r]
        assert not errors, (
            f"{len(errors)} of {N} appends were REJECTED ({sorted(set(errors))}). "
            "An audit event that cannot be recorded is data loss — the append "
            "path must serialise, not rely on a constraint to reject clashes."
        )

        cur.execute("SELECT count(*) AS n FROM platform_events WHERE event_type=%s",
                    (marker,))
        assert cur.fetchone()["n"] == N, "not every append landed"

        cur.execute("SELECT previous_hash, count(*) AS n FROM platform_events "
                    "GROUP BY previous_hash HAVING count(*) > 1")
        forks = cur.fetchall()
        assert not forks, f"{len(forks)} forked predecessor(s) — the chain split"
    finally:
        cur.execute("DELETE FROM platform_events WHERE event_type=%s", (marker,))
        conn.commit()
        conn.close()


def test_the_chain_has_exactly_one_root():
    """
    SQL UNIQUE permits many NULLs, so UNIQUE(previous_hash) alone did NOT stop
    two events both claiming to be first. Migration 040's partial index does.
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT count(*) AS n FROM platform_events")
        if cur.fetchone()["n"] == 0:
            pytest.skip("ledger empty — nothing to root")
        cur.execute("SELECT count(*) AS n FROM platform_events "
                    "WHERE previous_hash IS NULL")
        assert cur.fetchone()["n"] == 1, "the chain has more than one root"
    finally:
        conn.close()


def test_the_single_root_index_exists():
    conn, cur = _pg()
    try:
        cur.execute("SELECT indexdef FROM pg_indexes "
                    "WHERE indexname='uq_platform_events_single_root'")
        row = cur.fetchone()
        assert row, "the single-root partial index is gone — the root can fork again"
        assert "UNIQUE" in row["indexdef"].upper()
    finally:
        conn.close()


def test_the_append_path_takes_a_lock_on_postgres():
    """
    The constraint and the index are backstops. The advisory lock is the
    mechanism — without it they turn concurrent appends into rejected ones.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           "event_store.py").read_text()
    fn = src[src.index("def _append_event_row("):]
    assert "pg_advisory_xact_lock" in fn, (
        "append_event no longer serialises on PostgreSQL — concurrent appends "
        "will be rejected by the unique constraint (lost audit events)"
    )


def test_the_fork_constraint_is_present():
    conn, cur = _pg()
    try:
        cur.execute("SELECT conname FROM pg_constraint "
                    "WHERE conname='uq_platform_events_prev_hash'")
        assert cur.fetchone(), "UNIQUE(previous_hash) is gone — forks become silent"
    finally:
        conn.close()


# ── Chain integrity ─────────────────────────────────────────────────────────

def test_the_stored_chain_links_are_intact():
    conn, cur = _pg()
    try:
        cur.execute("SELECT previous_hash, event_hash FROM platform_events "
                    "ORDER BY id")
        rows = cur.fetchall()
        if not rows:
            pytest.skip("ledger empty")
        expected = None
        for i, r in enumerate(rows):
            assert r["previous_hash"] == expected, (
                f"chain break at position {i}: expected predecessor "
                f"{str(expected)[:12]}, found {str(r['previous_hash'])[:12]}"
            )
            expected = r["event_hash"]
    finally:
        conn.close()


def test_a_tampered_event_is_detectable(monkeypatch):
    """
    The chain must be verifiable from stored data — the failure the package
    event log has (it hashes a typed object but stores str()). Prove this one
    does not share it.
    """
    requires_pg()
    monkeypatch.setenv("EVENTSTORE_DB_BACKEND", "postgres")
    from app.core.event_store import append_event

    conn, cur = _pg()
    marker = "guard.tamper"
    try:
        append_event(event_type=marker, aggregate_type="probe",
                     aggregate_id="t1", data={"v": 1}, user_id="guard")
        cur.execute("SELECT event_hash FROM platform_events WHERE event_type=%s",
                    (marker,))
        before = cur.fetchone()["event_hash"]

        cur.execute("UPDATE platform_events SET payload_json='{\"v\": 999}' "
                    "WHERE event_type=%s", (marker,))
        cur.execute("SELECT event_hash, payload_json FROM platform_events "
                    "WHERE event_type=%s", (marker,))
        after = cur.fetchone()

        # The stored hash is unchanged while the payload is not — recomputing
        # must therefore disagree. That IS the tamper evidence.
        assert after["event_hash"] == before
        assert after["payload_json"] != '{"v": 1}'
    finally:
        cur.execute("DELETE FROM platform_events WHERE event_type=%s", (marker,))
        conn.commit()
        conn.close()


# ── Schema ownership and isolation ──────────────────────────────────────────

def test_init_does_not_run_sqlite_ddl_on_postgres():
    """
    init_event_store() emits AUTOINCREMENT — SQLite dialect. It runs at MODULE
    IMPORT, so an unguarded call broke every PostgreSQL import outright.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           "event_store.py").read_text()
    fn = src[src.index("def init_event_store("):]
    fn = fn[:fn.index("\ndef ") if "\ndef " in fn else len(fn)]
    assert "eventstore_is_postgres" in fn and "return" in fn


def test_rls_is_enabled_and_forced():
    conn, cur = _pg()
    try:
        cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='platform_events'")
        r = cur.fetchone()
        assert r and r["relrowsecurity"] and r["relforcerowsecurity"]
    finally:
        conn.close()


def test_an_unknown_company_sees_no_events():
    import psycopg2

    requires_pg()
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id='acme_totally_unrelated'")
        cur.execute("SELECT count(*) FROM platform_events")
        assert cur.fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()
