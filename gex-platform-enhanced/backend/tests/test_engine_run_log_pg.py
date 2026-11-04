"""
Migration 082 — the PF engine's run log in PostgreSQL (JML, 2026-11-04).

The engine logs every pricing run and parameter change to engine_model_runs and
engine_param_change_events, as its own role gex_engine. That role may INSERT and
SELECT those two tables and nothing else; the runtime role gex_app may not touch
them at all. Each statement runs as the role under test (SET LOCAL ROLE from the
migration credential) inside a transaction that is ROLLED BACK: the development
database is not written.
"""
from __future__ import annotations

import pytest

from pg_support import pg_bypassrls_connect, requires_pg

RUN = ("INSERT INTO engine_model_runs (run_id, endpoint, model_version, calibration_id, "
       "calibration_status, input_hash, computed_at) VALUES "
       "('TEST_run_082', 'TEST', 'TEST', 'TEST', 'SEED', 'TEST', '2026-11-04T00:00:00Z')")


def _as(role: str, sql: str):
    """('ok', rowcount) or ('refused', None); always rolled back."""
    import psycopg2

    requires_pg()
    conn = pg_bypassrls_connect()
    if conn is None:
        pytest.skip("ALEMBIC_DATABASE_URL not exported")
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regclass('engine_model_runs'), "
                    "EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gex_engine')")
        table, role_exists = cur.fetchone()
        if table is None or not role_exists:
            pytest.skip("migration 082 not applied")
        cur.execute(f"SET LOCAL ROLE {role}")
        try:
            cur.execute(sql)
        except psycopg2.errors.InsufficientPrivilege:
            return "refused", None
        return "ok", cur.rowcount
    finally:
        conn.rollback()
        conn.close()


def test_the_engine_writes_and_reads_its_run_log():
    assert _as("gex_engine", RUN) == ("ok", 1)
    assert _as("gex_engine", "SELECT count(*) FROM engine_model_runs")[0] == "ok"
    assert _as("gex_engine", "INSERT INTO engine_param_change_events (molecule, new_calibration_id, "
               "changed_fields_json, n_observations, source, at) VALUES "
               "('TEST', 'TEST', '{}', 0, 'TEST', '2026-11-04T00:00:00Z')") == ("ok", 1)


@pytest.mark.parametrize("sql", [
    "UPDATE engine_model_runs SET endpoint = 'rewritten'",
    "DELETE FROM engine_model_runs",
    "TRUNCATE engine_model_runs",
    "DELETE FROM engine_param_change_events",
])
def test_the_run_log_is_append_only_even_for_the_engine(sql):
    assert _as("gex_engine", sql) == ("refused", None)


@pytest.mark.parametrize("table", ["projects", "bankability_evidence", "auth_users", "fuel_catalog"])
def test_the_engine_role_reads_no_platform_data(table):
    assert _as("gex_engine", f"SELECT 1 FROM {table} LIMIT 1") == ("refused", None)


@pytest.mark.parametrize("sql", [
    "SELECT 1 FROM engine_model_runs LIMIT 1",
    RUN,
    "SELECT 1 FROM engine_param_change_events LIMIT 1",
])
def test_the_runtime_role_has_no_access_to_the_run_log(sql):
    assert _as("gex_app", sql) == ("refused", None)
