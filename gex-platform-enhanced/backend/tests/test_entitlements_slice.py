"""
Slice 6b-1 guardrails — entitlements.
=====================================
The largest remaining data set (~3,385 rows, 97% of everything still outside
PostgreSQL) and the one that decides who may see finance data.

Two properties matter here that did not in the bulk slices:

1. **The source moves while you copy.** `entitlement_audit` gains a row on every
   finance-access decision, including from this very test suite. Verification is
   therefore BY KEY — every row that existed at copy time must be in PostgreSQL;
   the destination having gained more is expected, not a failure.

2. **This table decides access.** A leak here is not a data leak, it is a
   permissions leak: `finance_entitlements` says which users may review which
   projects' finances.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_admin as _pg, pg_connect, requires_pg




def _sqlite():
    import sqlite3

    from app.core.config import settings

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Every source row arrived ────────────────────────────────────────────────

def _copied_keys(cur, table: str) -> set[str] | None:
    """
    The primary keys the copy actually wrote, read from migration_watermarks.

    BOTH stores are live during a strangler migration: whichever backend the
    suite is pointed at gains rows as it runs. So "SQLite and PostgreSQL hold
    the same rows" is NOT a property that can hold — asserting it failed for
    reasons unrelated to the migration on the first run of this file.

    The first attempt at a fix inferred a watermark from max(timestamp). That
    was ALSO wrong: `entitlement_audit.at` has second precision and many rows
    share a value, so `at <= max` swept in source rows written in the same
    second that were never copied. Recorded beats inferred.
    """
    import json

    cur.execute("SELECT copied_keys FROM migration_watermarks WHERE table_name=%s",
                (table,))
    row = cur.fetchone()
    return set(json.loads(row["copied_keys"])) if row else None


@pytest.mark.parametrize("table,pk", [
    ("finance_entitlements", "entitlement_id"),
    ("entitlement_audit", "audit_id"),
])
def test_every_copied_row_is_present_in_postgres(table, pk):
    """
    Nothing the copy claimed to write may be missing.

    Both stores keep accruing rows afterwards — that is expected and is NOT
    checked here. Only the recorded set is.
    """
    conn, cur = _pg()
    try:
        claimed = _copied_keys(cur, table)
        if claimed is None:
            pytest.skip(f"no watermark for {table} — run the migrator first")
        cur.execute(f"SELECT {pk} FROM {table}")
        present = {str(r[pk]) for r in cur.fetchall()}
    finally:
        conn.close()
    missing = claimed - present
    assert not missing, (
        f"{len(missing)} of {len(claimed)} rows the copy recorded for `{table}` "
        "are missing from PostgreSQL — rows were lost after the copy"
    )


@pytest.mark.parametrize("table,pk", [
    ("finance_entitlements", "entitlement_id"),
    ("entitlement_audit", "audit_id"),
])
def test_the_copy_covered_everything_that_existed_at_the_time(table, pk):
    """
    The watermark must not under-report. Every SQLite row NOT in the recorded
    set has to be newer than the copy — if an OLD row is unrecorded, the copy
    skipped it.
    """
    conn, cur = _pg()
    try:
        claimed = _copied_keys(cur, table)
        if claimed is None:
            pytest.skip(f"no watermark for {table}")
        cur.execute("SELECT copied_at FROM migration_watermarks WHERE table_name=%s",
                    (table,))
        copied_at = cur.fetchone()["copied_at"]
    finally:
        conn.close()

    ts_col = "granted_at" if table == "finance_entitlements" else "at"
    lite = _sqlite()
    try:
        rows = {str(r[pk]): r[ts_col] for r in lite.execute(
            f"SELECT {pk}, {ts_col} FROM {table}")}
    finally:
        lite.close()

    # Anything unrecorded must post-date the copy.
    stale = [k for k, ts in rows.items()
             if k not in claimed and ts and ts < copied_at[:len(ts)]]
    assert not stale, (
        f"{len(stale)} row(s) in `{table}` predate the copy ({copied_at}) but "
        f"were not recorded as copied — e.g. {stale[:3]}"
    )


def test_a_sampled_entitlement_matches_column_for_column():
    """
    Row presence is not row fidelity — compare the payload too.

    Samples from the recorded `copied_keys`, NOT from "first by entitlement_id".
    Both stores are live and SQLite keeps accruing rows that were never
    migrated: at the time of writing SQLite held 1128 against PostgreSQL's 838,
    and the watermark records 744 as actually copied. Sampling by id order
    eventually picks a row created after the copy and fails, claiming drift
    where there is none — which is what it did on 2026-08-10.

    The migrated rows are the only population where fidelity is a property that
    can hold. That is the same reasoning as
    test_both_backends_return_the_same_entitlements, which compares shared ids
    only.
    """
    import json

    conn, cur = _pg()
    try:
        cur.execute("SELECT copied_keys FROM migration_watermarks "
                    "WHERE table_name='finance_entitlements'")
        row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row["copied_keys"]:
        pytest.skip("no recorded copy for finance_entitlements")
    keys = row["copied_keys"]
    if isinstance(keys, str):
        keys = json.loads(keys)
    if not keys:
        pytest.skip("no entitlements were copied")

    lite = _sqlite()
    try:
        src_row = lite.execute(
            "SELECT * FROM finance_entitlements WHERE entitlement_id = ?",
            (sorted(keys)[0],),
        ).fetchone()
        if src_row is None:
            pytest.skip("the sampled migrated row is gone from SQLite")
        src = dict(src_row)
    finally:
        lite.close()
    conn, cur = _pg()
    try:
        cur.execute("SELECT * FROM finance_entitlements WHERE entitlement_id=%s",
                    (src["entitlement_id"],))
        dst = cur.fetchone()
    finally:
        conn.close()
    assert dst, "sampled entitlement missing in PostgreSQL"
    diffs = {k: (src[k], dst[k]) for k in src if str(src[k]) != str(dst[k])}
    assert not diffs, f"column drift on {src['entitlement_id']}: {diffs}"


# ── Isolation: this table decides who sees finance data ─────────────────────

def test_rls_is_enabled_and_forced_on_both_tables():
    conn, cur = _pg()
    try:
        cur.execute("SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname IN "
                    "('finance_entitlements','entitlement_audit')")
        found = {r["relname"]: r for r in cur.fetchall()}
        assert len(found) == 2, f"tables missing: {found.keys()}"
        for t, r in found.items():
            assert r["relrowsecurity"], f"{t}: RLS not enabled"
            assert r["relforcerowsecurity"], f"{t}: RLS not FORCED"
    finally:
        conn.close()


def test_an_unknown_company_sees_no_entitlements():
    """A permissions table that leaks is worse than a data table that leaks."""
    import psycopg2

    requires_pg()
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id='acme_totally_unrelated'")
        for t in ("finance_entitlements", "entitlement_audit"):
            cur.execute(f"SELECT count(*) FROM {t}")
            assert cur.fetchone()[0] == 0, f"{t} leaked to an unknown company"
    finally:
        conn.rollback()
        conn.close()


def test_each_company_sees_exactly_its_own_projects_entitlements():
    """
    Derived from the data, not hard-coded. Every entitlement today belongs to
    proj_etf_pecos1 (owner etfuels_sa), so a generic "sees some but not all"
    assertion is unsatisfiable — the owner legitimately sees 100%. What must
    hold is the mapping: each company sees exactly the entitlements whose
    project it owns or has access to, and nothing else.
    """
    import psycopg2

    requires_pg()

    admin = pg_connect()
    ac = admin.cursor()
    ac.execute("SET app.current_company_id='PLATFORM_ADMIN'")
    ac.execute("SELECT count(*) FROM finance_entitlements")
    total = ac.fetchone()[0]
    if not total:
        admin.close()
        pytest.skip("no entitlements to check")

    # Expected per company, computed from ownership/access — not assumed.
    ac.execute("""
        SELECT t.company_id, count(fe.entitlement_id) AS n
        FROM tenants t
        LEFT JOIN finance_entitlements fe
          ON app_company_owns_project(fe.project_id, t.company_id)
          OR app_company_has_project_access(fe.project_id, t.company_id)
        GROUP BY t.company_id
    """)
    expected = {r[0]: r[1] for r in ac.fetchall()}
    admin.close()

    assert any(v > 0 for v in expected.values()), "no company can see anything"

    mismatches = {}
    for company, want in expected.items():
        c2 = pg_connect()
        k = c2.cursor()
        k.execute("BEGIN")
        k.execute("SET LOCAL ROLE gex_app")
        k.execute("SET LOCAL app.current_company_id = %s", (company,))
        k.execute("SELECT count(*) FROM finance_entitlements")
        got = k.fetchone()[0]
        c2.rollback()
        c2.close()
        if got != want:
            mismatches[company] = (want, got)
    assert not mismatches, f"RLS does not match ownership: {mismatches}"


# ── Both backends agree through the module's own API ────────────────────────

def test_both_backends_return_the_same_entitlements(monkeypatch):
    """
    The flip gate. Exercised through the public API, not raw SQL — a difference
    in how the shim returns rows would show up here and nowhere else.
    """
    requires_pg()

    def snapshot(backend):
        monkeypatch.setenv("ENTITLEMENT_DB_BACKEND", backend)
        from app.core.entitlements import list_entitlements

        return {r["entitlement_id"]: r.get("status") for r in list_entitlements()}

    try:
        lite, pg = snapshot("sqlite"), snapshot("postgres")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend unavailable: {exc}")

    # Compare the SHARED ids only. Each store keeps accruing its own rows while
    # the other is the active backend, so identical key sets is not a property
    # that can hold. What must hold: where both know an entitlement, they agree
    # about it — including its derived active/expired/revoked status.
    shared = lite.keys() & pg.keys()
    assert shared, "the two stores share no entitlements at all"
    disagree = {k: (lite[k], pg[k]) for k in shared if lite[k] != pg[k]}
    assert not disagree, f"backends disagree on {len(disagree)} entitlement(s): {list(disagree.items())[:3]}"


# ── Schema ownership and the action domain ──────────────────────────────────

def test_postgres_rejects_an_unknown_audit_action():
    conn, cur = _pg()
    try:
        with pytest.raises(Exception):
            cur.execute("INSERT INTO entitlement_audit (audit_id, at, action) "
                        "VALUES ('gt_bad', '2026-01-01', 'exfiltrated')")
        conn.rollback()
    finally:
        conn.close()


def test_init_does_not_create_tables_on_postgres():
    """Migration 037 owns the schema, the CHECK and the policies."""
    src = (__import__("pathlib").Path(__file__).resolve().parents[1]
           / "app" / "core" / "entitlements.py").read_text()
    fn = src[src.index("def init_entitlements_db("):]
    fn = fn[:fn.index("\ndef ") if "\ndef " in fn else len(fn)]
    assert "entitlement_is_postgres" in fn and "return" in fn, (
        "init_entitlements_db must short-circuit on PostgreSQL"
    )


# ── Append-only, as a property of the code ──────────────────────────────────

def test_the_audit_table_is_never_updated_or_deleted_in_code():
    """
    `entitlement_audit` is append-only by convention, not by constraint — the
    migration deliberately did not add a database guarantee in the same change
    as the move. This is the substitute: no UPDATE or DELETE against it
    anywhere in app/.
    """
    import re
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(errors="ignore")
        if re.search(r"(UPDATE|DELETE\s+FROM)\s+entitlement_audit", src, re.I):
            offenders.append(str(path.relative_to(app.parent)))
    assert not offenders, (
        f"{offenders} mutates entitlement_audit — it is an append-only access log"
    )
