"""
Reference data registry on PostgreSQL (migration 061) — the WP1 acceptance tests.

  (a) the schema is what 061 says: RLS forced, grants exact, seed as reviewed;
  (b) a tenant reads and cannot write; PLATFORM_ADMIN writes;
  (c) approving supersedes the old row and publishes a new version, and the old
      row is still what `as_of` returns for a date before the new one;
  (d) starting the backend changes nothing in the registry.

Runs as gex_app and writes nothing: every statement is in a transaction that is
rolled back. Skips when PostgreSQL is unconfigured or down, or 061 is not applied.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pg_support import pg_bypassrls_connect, pg_connect

BACKEND = Path(__file__).resolve().parents[1]


class _Tx:
    """The slice of the shim's connection the registry uses, over a test
    connection whose transaction is always rolled back."""

    def __init__(self, company: str) -> None:
        import psycopg2.extras

        self._conn = pg_connect()
        self._factory = psycopg2.extras.RealDictCursor
        cur = self._conn.cursor()
        cur.execute("SELECT to_regclass('public.reference_parameter')")
        if cur.fetchone()[0] is None:
            self._conn.close()
            pytest.skip("migration 061 not applied")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))

    def execute(self, sql, params=()):
        from app.core.db_backend import _PgCursor, _to_pg

        cur = self._conn.cursor(cursor_factory=self._factory)
        cur.execute(_to_pg(sql), tuple(params))
        return _PgCursor(cur)

    def close(self) -> None:
        self._conn.rollback()
        self._conn.close()


@pytest.fixture
def admin():
    tx = _Tx("PLATFORM_ADMIN")
    yield tx
    tx.close()


@pytest.fixture
def tenant():
    tx = _Tx("etfuels_sa")
    yield tx
    tx.close()


def _proposal(**over):
    p = dict(parameter_key="electrolyser_installed_capex", pathway="H2_PEM", region="US",
             value_low=1400.0, value_base=1900.0, value_high=2400.0, unit="USD/kW",
             currency="USD", price_base_date="2025-01-01", source_class="public_source",
             source_name="TEST — not a real source", valid_from="2026-11-01")
    p.update(over)
    return p


# ── (a) schema ──────────────────────────────────────────────────────────────

def test_rls_is_forced_and_grants_are_exact(admin):
    rows = admin.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname IN ('reference_parameter', 'reference_version')").fetchall()
    assert {r["relname"] for r in rows} == {"reference_parameter", "reference_version"}
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)

    table = {r["table_name"]: r["p"] for r in admin.execute(
        "SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS p "
        "FROM information_schema.role_table_grants WHERE grantee = 'gex_app' "
        "AND table_name IN ('reference_parameter', 'reference_version') "
        "GROUP BY 1").fetchall()}
    # 031's DEFAULT PRIVILEGES would have given full DML; 061 revokes it.
    assert table == {"reference_parameter": "INSERT,SELECT",
                     "reference_version": "INSERT,SELECT"}
    cols = {r["column_name"] for r in admin.execute(
        "SELECT column_name FROM information_schema.column_privileges "
        "WHERE grantee = 'gex_app' AND table_name = 'reference_parameter' "
        "AND privilege_type = 'UPDATE'").fetchall()}
    assert cols == {"state", "supersedes_ref_id", "approved_by", "approved_at",
                    "rejected_by", "rejected_at"}


def test_the_seed_is_as_reviewed(admin):
    rows = admin.execute(
        "SELECT parameter_key, pathway, region FROM reference_parameter "
        "WHERE proposed_by = 'MIGRATION_061'").fetchall()
    assert len(rows) == 13
    # Not confirmed against their sources on 2026-10-19, so seeded proposed: the
    # migration approved none of them. A later approval names a person, never
    # MIGRATION_061 (debt_gearing: JML, 2026-10-19).
    seeded_approved = {(r["parameter_key"], r["pathway"], r["region"]) for r in admin.execute(
        "SELECT parameter_key, pathway, region FROM reference_parameter "
        "WHERE proposed_by = 'MIGRATION_061' AND approved_by = 'MIGRATION_061'").fetchall()}
    assert {(r["parameter_key"], r["pathway"], r["region"]) for r in rows} - seeded_approved == {
        ("electrolyser_installed_capex", "ANY", "ROW"),
        ("electrolyser_installed_capex", "ANY", "CN"),
        ("subsidy_45v_max", "H2", "US"),
        ("debt_gearing", "ANY", "ANY"),
    }
    from app.core import reference_registry as reg

    v1 = admin.execute("SELECT * FROM reference_version WHERE version_number = 1").fetchone()
    assert v1 is not None
    approved = {r["ref_id"] for r in admin.execute(
        "SELECT ref_id FROM reference_parameter WHERE proposed_by = 'MIGRATION_061' "
        "AND approved_by = 'MIGRATION_061'").fetchall()}
    assert set(reg._version(v1)["ref_ids"]) == approved


def test_every_monetary_row_is_dated_and_in_its_units_currency(admin):
    from app.core.reference_catalog import MONETARY_FAMILIES, UNIT_FAMILIES, family_of

    for r in admin.execute("SELECT * FROM reference_parameter").fetchall():
        family = family_of(r["parameter_key"])
        assert family, f"{r['parameter_key']} is not in the catalog"
        assert r["unit"] in UNIT_FAMILIES[family], f"{r['parameter_key']}: unit {r['unit']}"
        if family in MONETARY_FAMILIES:
            assert r["currency"] == r["unit"].split("/")[0], r["parameter_key"]
            assert r["price_base_date"], f"{r['parameter_key']}: monetary but undated"


# ── (b) RLS: tenants read, only PLATFORM_ADMIN writes ───────────────────────

def test_a_tenant_reads_the_registry(tenant):
    from app.core import reference_registry as reg

    row = reg.resolve(tenant, "electrolyser_system_sec", "H2_PEM", "DE")
    assert row and row["value_base"] == pytest.approx(57.0)
    assert reg.latest_version(tenant)["version_number"] >= 1


def test_a_tenant_cannot_write(tenant):
    import psycopg2

    from app.core import reference_registry as reg

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        reg.propose(tenant, _proposal(), actor="usr_tenant")


def test_a_tenant_cannot_approve(tenant):
    """The lifecycle UPDATE is granted by column, but RLS gives a tenant no row
    to update: the approval silently matches nothing, and the version is refused."""
    import psycopg2

    pending = tenant.execute("SELECT ref_id FROM reference_parameter "
                             "WHERE state = 'proposed' LIMIT 1").fetchone()
    assert pending, "the seed carries proposed rows"
    cur = tenant.execute(
        "UPDATE reference_parameter SET state = 'approved', approved_by = 'usr_tenant', "
        "approved_at = '2026-10-19' WHERE ref_id = ?", (pending["ref_id"],))
    assert cur.rowcount == 0
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        tenant.execute(
            "INSERT INTO reference_version (version_id, version_number, created_at, "
            "created_by, ref_ids_json) VALUES ('x', 999, '2026-10-19', 'usr_tenant', '[]')")


def test_platform_admin_can_propose(admin):
    from app.core import reference_registry as reg

    row = reg.propose(admin, _proposal(), actor="usr_analyst")
    assert row["state"] == "proposed" and row["proposed_by"] == "usr_analyst"


# ── (c) approval supersedes, versions, and as_of ────────────────────────────

def test_approval_supersedes_and_the_old_value_stays_readable(admin):
    from app.core import reference_registry as reg

    key = ("electrolyser_installed_capex", "H2_PEM", "US")
    old = reg.in_force(admin, *key)
    v_before = reg.latest_version(admin)
    assert old and old["value_base"] == pytest.approx(2000.0)

    new = reg.propose(admin, _proposal(), actor="usr_analyst")
    out = reg.approve(admin, new["ref_id"], actor="usr_reviewer")

    assert out["parameter"]["state"] == "approved"
    assert out["parameter"]["supersedes_ref_id"] == old["ref_id"]
    assert reg.get_row(admin, old["ref_id"])["state"] == "superseded"

    v = out["version"]
    assert v["version_number"] == v_before["version_number"] + 1
    assert new["ref_id"] in v["ref_ids"] and old["ref_id"] not in v["ref_ids"]
    assert set(v["ref_ids"]) == set(v_before["ref_ids"]) - {old["ref_id"]} | {new["ref_id"]}
    # The old version is unchanged — it is what a pinned project still points at.
    assert reg.get_version(admin, v_before["version_id"])["ref_ids"] == v_before["ref_ids"]

    assert reg.in_force(admin, *key, as_of="2026-10-25")["ref_id"] == old["ref_id"]
    assert reg.in_force(admin, *key, as_of="2026-11-02")["ref_id"] == new["ref_id"]
    assert reg.in_force(admin, *key, as_of="2026-10-18") is None  # before GEX held it


def test_the_approver_must_not_be_the_proposer(admin):
    from app.core import reference_registry as reg

    new = reg.propose(admin, _proposal(), actor="usr_analyst")
    with pytest.raises(reg.RegistryError) as exc:
        reg.approve(admin, new["ref_id"], actor="usr_analyst")
    assert exc.value.status == 403


def test_a_successor_must_start_after_its_predecessor(admin):
    from app.core import reference_registry as reg

    new = reg.propose(admin, _proposal(valid_from="2026-10-19"), actor="usr_analyst")
    with pytest.raises(reg.RegistryError) as exc:
        reg.approve(admin, new["ref_id"], actor="usr_reviewer")
    assert exc.value.status == 409


def test_a_rejected_row_is_kept_and_never_in_force(admin):
    from app.core import reference_registry as reg

    new = reg.propose(admin, _proposal(), actor="usr_analyst")
    assert reg.reject(admin, new["ref_id"], actor="usr_reviewer")["state"] == "rejected"
    assert reg.in_force(admin, "electrolyser_installed_capex", "H2_PEM", "US",
                        as_of="2027-01-01")["ref_id"] != new["ref_id"]
    with pytest.raises(reg.RegistryError):
        reg.approve(admin, new["ref_id"], actor="usr_reviewer")


@pytest.mark.parametrize("sql", [
    "UPDATE reference_parameter SET value_base = value_base + 1",
    "UPDATE reference_parameter SET note = 'rewritten'",
    "DELETE FROM reference_parameter",
    "UPDATE reference_version SET reason = 'rewritten'",
    "DELETE FROM reference_version",
])
def test_the_runtime_cannot_rewrite_history(admin, sql):
    import psycopg2

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        admin.execute(sql)


@pytest.mark.parametrize("sql", [
    "UPDATE reference_parameter SET value_base = value_base + 1",
    "UPDATE reference_parameter SET state = 'proposed' WHERE state = 'approved'",
    "DELETE FROM reference_parameter",
    "UPDATE reference_version SET reason = 'rewritten'",
    "DELETE FROM reference_version",
])
def test_not_even_the_owner_can_rewrite_history(sql):
    """The trigger binds every role, superuser included, not just the grants."""
    import psycopg2

    conn = pg_bypassrls_connect()
    if conn is None:
        pytest.skip("ALEMBIC_DATABASE_URL not exported")
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.reference_parameter')")
        if cur.fetchone()[0] is None:
            pytest.skip("migration 061 not applied")
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute(sql)
    finally:
        conn.rollback()
        conn.close()


# ── (d) startup changes nothing ─────────────────────────────────────────────

def _fingerprint() -> str:
    conn = pg_bypassrls_connect()
    if conn is None:
        pytest.skip("ALEMBIC_DATABASE_URL not exported")
    try:
        cur = conn.cursor()
        h = hashlib.sha256()
        for table, order in (("reference_parameter", "ref_id"),
                             ("reference_version", "version_id"),
                             ("fuel_defaults", "fuel_type")):
            cur.execute(f"SELECT to_regclass('public.{table}')")
            if cur.fetchone()[0] is None:
                pytest.skip(f"{table} absent")
            cur.execute(f"SELECT t::text FROM {table} t ORDER BY {order}")
            for (row,) in cur.fetchall():
                h.update(row.encode())
        return h.hexdigest()
    finally:
        conn.close()


def test_starting_the_backend_changes_nothing_in_the_registry():
    before = _fingerprint()
    env = dict(os.environ)
    subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, env=env,
                   check=True, capture_output=True, timeout=180)
    assert _fingerprint() == before
