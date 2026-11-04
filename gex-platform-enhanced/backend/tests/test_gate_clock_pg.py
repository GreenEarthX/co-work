"""The gate clock on PostgreSQL (migration 080): append-only for the runtime role, and tenant-scoped."""
from pg_support import pg_admin as _pg, requires_pg


def test_the_runtime_role_can_only_read_and_append_and_rls_is_forced():
    """Negative-verified 2026-10-31: re-granting UPDATE or DELETE to gex_app fails this."""
    requires_pg()
    conn, cur = _pg()
    try:
        cur.execute("SELECT string_agg(privilege_type, ',' ORDER BY privilege_type) AS p FROM "
                    "information_schema.role_table_grants WHERE grantee = 'gex_app' AND table_name = 'project_gate_clock'")
        assert cur.fetchone()["p"] == "INSERT,SELECT"
        cur.execute("SELECT relrowsecurity AS rls, relforcerowsecurity AS forced FROM pg_class WHERE relname = 'project_gate_clock'")
        row = cur.fetchone()
        assert row["rls"] and row["forced"]
    finally:
        conn.close()
