"""
Slice 6b-4 guardrails — governance / access control.
====================================================
Seven tables, 16 rows. Small, but they decide **who may approve what**, so they
get auth-slice scrutiny.

The distinguishing property of this slice: **four different RLS shapes**, because
the scopes genuinely differ. Every earlier slice used one. Using one here would
be wrong four different ways — and the tests below assert each is the RIGHT
kind of wrong-proof:

  global rules  -> readable by all (a rule you cannot read is a trap, not a control)
  project rows  -> delegated to the 032 helpers
  user rows     -> ADMIN-ONLY, a known limitation (no app.current_user_id GUC)
  company rows  -> company_id compared directly
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_admin as _pg, pg_as_tenant as _as_tenant, requires_pg

GLOBAL_RULES = ("approval_policies", "sod_conflict_pairs")
PROJECT_SCOPED = ("approval_requests", "sod_action_log")
USER_SCOPED = ("permission_user_overrides", "user_signing_keys")
COMPANY_SCOPED = ("data_residency_policies",)
ALL_TABLES = GLOBAL_RULES + PROJECT_SCOPED + USER_SCOPED + COMPANY_SCOPED






# ── Shape 1: the rules everyone is bound by must be readable ────────────────

def test_approval_rules_are_readable_by_any_tenant():
    """
    Deliberately NOT tenant-isolated. If a user cannot read "payments over X
    need 2 approvers", the UI cannot explain why their action was refused — a
    compliance rule you cannot read is a trap, not a control.
    """
    requires_pg()
    for t in GLOBAL_RULES:
        n = _as_tenant("acme_totally_unrelated", f"SELECT count(*) FROM {t}")
        assert n == 8, f"{t}: a tenant sees {n} rows, expected all 8"


def test_approval_rules_are_not_tenant_writable():
    """Readable by all, curated by admin — a tenant must not edit the rules
    it is judged by."""
    conn, cur = _pg()
    try:
        cur.execute("SELECT tablename, policyname, cmd FROM pg_policies "
                    "WHERE tablename = ANY(%s)", (list(GLOBAL_RULES),))
        pols = {}
        for r in cur.fetchall():
            pols.setdefault(r["tablename"], []).append((r["policyname"], r["cmd"]))
        for t in GLOBAL_RULES:
            names = [p for p, _ in pols.get(t, [])]
            assert any("admin_writes" in n for n in names), (
                f"{t} has no admin-only write policy — a tenant could rewrite "
                "the approval rules that bind it"
            )
    finally:
        conn.close()


# ── Shape 3: user-scoped is admin-only, and that is a KNOWN LIMITATION ──────

def test_user_scoped_tables_are_admin_only():
    """
    `permission_user_overrides` and `user_signing_keys` belong to a USER, but
    the only tenant GUC is app.current_company_id. "A user may read their own
    row" cannot be expressed, so they are admin-only.

    Critically they must NOT be company-scoped: that would let a colleague read
    another user's permission overrides.
    """
    requires_pg()
    conn, cur = _pg()
    try:
        cur.execute("SELECT tablename, qual FROM pg_policies "
                    "WHERE tablename = ANY(%s)", (list(USER_SCOPED),))
        rows = {r["tablename"]: (r["qual"] or "") for r in cur.fetchall()}
        assert set(rows) == set(USER_SCOPED), f"missing policies: {rows.keys()}"
        for t, qual in rows.items():
            assert "PLATFORM_ADMIN" in qual, f"{t}: not admin-scoped"
            assert "company_id =" not in qual.replace("app.current_company_id", ""), (
                f"{t} is COMPANY-scoped — a colleague could read another user's "
                "overrides. It must stay admin-only until an app.current_user_id "
                "GUC exists."
            )
    finally:
        conn.close()


def test_a_tenant_cannot_read_permission_overrides():
    requires_pg()
    for t in USER_SCOPED:
        assert _as_tenant("hamburgone_com", f"SELECT count(*) FROM {t}") == 0, (
            f"{t} is readable by a tenant"
        )


def test_the_missing_user_guc_is_documented_not_forgotten():
    """
    Admin-only here is a limitation, not a design. If someone adds an
    app.current_user_id GUC, these policies should be revisited — the migration
    says so in prose so the constraint is discoverable.
    """
    from pathlib import Path

    mig = (Path(__file__).resolve().parents[1] / "alembic" / "versions" /
           "042_governance_slice.py").read_text()
    assert "app.current_user_id" in mig, (
        "the missing user-scope GUC is no longer documented in migration 042"
    )


# ── Shape 2 and 4 ───────────────────────────────────────────────────────────

def test_project_scoped_governance_is_isolated():
    requires_pg()
    for t in PROJECT_SCOPED:
        assert _as_tenant("acme_totally_unrelated", f"SELECT count(*) FROM {t}") == 0


def test_company_scoped_policies_compare_company_directly():
    conn, cur = _pg()
    try:
        cur.execute("SELECT qual FROM pg_policies "
                    "WHERE tablename='data_residency_policies'")
        qual = (cur.fetchone() or {}).get("qual", "")
        assert "company_id" in qual, "data residency is not company-scoped"
    finally:
        conn.close()


# ── The rules themselves must stay coherent ─────────────────────────────────

def test_no_approval_policy_can_require_fewer_than_one_approver():
    """A policy demanding 0 approvers is not an approval policy."""
    conn, cur = _pg()
    try:
        with pytest.raises(Exception):
            cur.execute("INSERT INTO approval_policies (id, action_type, "
                        "min_approvers) VALUES ('gt_bad','x',0)")
        conn.rollback()
    finally:
        conn.close()


def test_no_sod_pair_conflicts_an_action_with_itself():
    """
    action_a = action_b would mean nobody may ever perform that action twice,
    which is not segregation of duties — it is a lockout.
    """
    conn, cur = _pg()
    try:
        with pytest.raises(Exception):
            cur.execute("INSERT INTO sod_conflict_pairs (id, action_a, action_b) "
                        "VALUES ('gt_bad','APPROVE','APPROVE')")
        conn.rollback()
    finally:
        conn.close()


def test_the_migrated_rules_are_still_enforceable():
    """Row counts prove nothing; the rules must retain usable values."""
    conn, cur = _pg()
    try:
        cur.execute("SELECT count(*) AS n FROM approval_policies "
                    "WHERE active = 1 AND min_approvers >= 1")
        assert cur.fetchone()["n"] > 0, "no enforceable approval policy survived"
        cur.execute("SELECT count(*) AS n FROM sod_conflict_pairs "
                    "WHERE active = 1 AND action_a IS NOT NULL AND action_b IS NOT NULL")
        assert cur.fetchone()["n"] > 0, "no enforceable SoD pair survived"
    finally:
        conn.close()


# ── Backends agree, schema ownership ────────────────────────────────────────

def test_both_backends_return_the_same_rules(monkeypatch):
    requires_pg()

    def snapshot(backend):
        monkeypatch.setenv("GOVERNANCE_DB_BACKEND", backend)
        from app.core.sod import _DB_PATH as sp
        from app.core.sod import _gov_conn as sc
        from app.core.wae import _DB_PATH as wp
        from app.core.wae import _gov_conn as wc

        c = wc(wp)
        pol = sorted((r["id"], r["action_type"], r["min_approvers"])
                     for r in c.execute(
                         "SELECT id, action_type, min_approvers "
                         "FROM approval_policies").fetchall())
        c.close()
        c = sc(sp)
        pairs = sorted((r["action_a"], r["action_b"]) for r in c.execute(
            "SELECT action_a, action_b FROM sod_conflict_pairs").fetchall())
        c.close()
        return pol, pairs

    try:
        lite, pg = snapshot("sqlite"), snapshot("postgres")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend unavailable: {exc}")
    assert lite == pg, "backends disagree on the governance rules"


@pytest.mark.parametrize("module,fn", [
    ("wae", "init_wae_db"), ("sod", "init_sod_db"),
    ("css", "init_css_db"), ("drpl", "init_drpl_db"),
    ("permission_engine", "init_permission_override_store"),
])
def test_init_functions_do_not_run_sqlite_ddl_on_postgres(module, fn):
    """
    These use executescript(), which does not exist on the PostgreSQL adapter —
    unguarded they would error rather than no-op.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           f"{module}.py").read_text()
    body = src[src.index(f"def {fn}("):]
    body = body[:body.index("\ndef ") if "\ndef " in body else len(body)]
    assert "governance_is_postgres" in body, f"{module}.{fn} is unguarded"


def test_rls_is_enabled_and_forced_everywhere():
    conn, cur = _pg()
    try:
        cur.execute("SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(%s)", (list(ALL_TABLES),))
        found = {r["relname"]: r for r in cur.fetchall()}
        missing = [t for t in ALL_TABLES if t not in found]
        assert not missing, f"absent from PostgreSQL: {missing}"
        for t, r in found.items():
            assert r["relrowsecurity"] and r["relforcerowsecurity"], f"{t}: RLS weak"
    finally:
        conn.close()
