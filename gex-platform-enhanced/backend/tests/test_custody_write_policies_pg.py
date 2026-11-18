"""
Who may write custody lots and deliveries (GreenMesh Phase 2, Step 1 — gap G-21, migration 100).

`mass_balance_lots` and `deliveries` each carried ONE `FOR ALL` policy from 044 with no WITH
CHECK, whose read rule includes `app_company_has_project_access`. PostgreSQL then uses the
read rule as the write rule, so a company that may only READ a project — a reviewer, a lender
— could create, rewrite or delete its lots and deliveries. Since 100: reads unchanged; writes
need the project's owner or GEX (PLATFORM_ADMIN), as the 097 custody tables already do.

Since 103 `deliveries` is the delivery record: only the operator connection writes it, after the
application authorises the seller or the buyer (tests/test_delivery_record_pg.py), so its cases
here were retired; what remains pins the lots, and that 103 still refuses a reader.

Runs as gex_app in the throwaway database of conftest.pg_store, never the development store.
"""
from __future__ import annotations

import os
import uuid

import pytest

OWNER = "test_cwp_owner"
READER = "test_cwp_reader"          # holds a project_access row: reads, must not write
STRANGER = "test_cwp_stranger"
PROJECT = "proj_TEST_custody_write_policies"


def _superuser(pg_url: str):
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = _superuser(pg_store)
    try:
        cur = conn.cursor()
        for c in (OWNER, READER, STRANGER):
            cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                        "ON CONFLICT DO NOTHING", (c, f"TEST {c}"))
        cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                    "VALUES (%s, 'TEST custody write policies', %s, 'H2') ON CONFLICT DO NOTHING", (PROJECT, OWNER))
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) "
                    "VALUES (%s, %s, 'LENDER', 'REVIEWER') ON CONFLICT DO NOTHING", (PROJECT, READER))
        conn.commit()
    finally:
        conn.close()
    return pg_store


def _as(pg_url: str, company: str, sql: str, params=()):
    """One statement as gex_app bound to `company`, always rolled back.
    Returns 'refused' when RLS rejects it, else the row count."""
    import psycopg2

    from pg_support import connect_dsn

    conn = connect_dsn(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (company,))
        try:
            cur.execute(sql, params)
        except psycopg2.Error as exc:
            if "row-level security" in str(exc) or "permission denied" in str(exc):
                return "refused"
            raise
        return cur.rowcount
    finally:
        conn.rollback()
        conn.close()


def _lot_insert():
    return ("INSERT INTO mass_balance_lots (lot_id, project_id, molecule, production_date, total_volume_kg, "
            "allocated_volume_kg, remaining_volume_kg, status, audit_hash, created_by, created_at, updated_at) "
            "VALUES (%s, %s, 'H2', '2026-02-01', 10, 0, 10, 'OPEN', 'h', 'x', 'now', 'now')",
            (f"lot-{uuid.uuid4().hex[:8]}", PROJECT))


def _delivery_insert():
    # Fails on 103's columns before RLS is even asked, for every caller; RLS is checked first
    # for an INSERT policy, so a reader is refused by RLS, not by the missing columns.
    return ("INSERT INTO deliveries (id, project_id, contract_id) VALUES (%s, %s, gen_random_uuid())",
            (f"del-{uuid.uuid4().hex[:8]}", PROJECT))


@pytest.mark.parametrize("insert", [_lot_insert, _delivery_insert], ids=["lot", "delivery"])
def test_a_company_that_may_only_read_cannot_insert(seeded, insert):
    sql, params = insert()
    assert _as(seeded, READER, sql, params) == "refused"
    assert _as(seeded, STRANGER, sql, params) == "refused"


@pytest.mark.parametrize("insert", [_lot_insert])
def test_the_owner_and_gex_still_insert(seeded, insert):
    sql, params = insert()
    assert _as(seeded, OWNER, sql, params) == 1
    sql, params = insert()
    assert _as(seeded, "PLATFORM_ADMIN", sql, params) == 1


@pytest.mark.parametrize("table,key", [("mass_balance_lots", "lot_id")])
def test_a_reader_reads_but_cannot_change_or_delete(seeded, table, key):
    sql, params = (_lot_insert if table == "mass_balance_lots" else _delivery_insert)()
    conn = _superuser(seeded)
    try:
        conn.cursor().execute(sql, params)
        conn.commit()
    finally:
        conn.close()
    rid = params[0]
    assert _as(seeded, READER, f"SELECT 1 FROM {table} WHERE {key} = %s", (rid,)) == 1
    assert _as(seeded, STRANGER, f"SELECT 1 FROM {table} WHERE {key} = %s", (rid,)) == 0
    # An UPDATE or DELETE the policy does not admit touches no row (USING filters it out).
    col = "total_volume_kg" if table == "mass_balance_lots" else "volume_mt"
    assert _as(seeded, READER, f"UPDATE {table} SET {col} = 1e9 WHERE {key} = %s", (rid,)) in (0, "refused")
    assert _as(seeded, READER, f"DELETE FROM {table} WHERE {key} = %s", (rid,)) in (0, "refused")
    assert _as(seeded, OWNER, f"UPDATE {table} SET {col} = 2 WHERE {key} = %s", (rid,)) == 1


@pytest.mark.parametrize("table", ["mass_balance_lots"])
def test_the_policy_set_is_split_and_rls_stays_forced(seeded, table):
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SELECT cmd FROM pg_policies WHERE tablename = %s", (table,))
        cmds = sorted((r["cmd"] if isinstance(r, dict) else r[0]) for r in cur.fetchall())
        cur.execute("SELECT relrowsecurity AND relforcerowsecurity AS f FROM pg_class WHERE relname = %s", (table,))
        row = cur.fetchone()
        forced = row["f"] if isinstance(row, dict) else row[0]
    finally:
        conn.close()
    assert cmds == ["DELETE", "INSERT", "SELECT", "UPDATE"], cmds
    assert forced
