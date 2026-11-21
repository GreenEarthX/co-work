"""Migration 126 on PostgreSQL: a workbook import is insert-only for the runtime and readable only by
the owning company or GEX. Every statement runs in one transaction that is rolled back."""
from __future__ import annotations

import json
import uuid

import pytest

from tests.pg_support import pg_connect


def _owned(cur):
    cur.execute("SELECT project_id, owner_tenant_id FROM projects WHERE owner_tenant_id IS NOT NULL LIMIT 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("no owned project in this database")
    return row


def _insert(cur, project_id, owner):
    iid = str(uuid.uuid4())
    cur.execute("INSERT INTO workbook_import (import_id, project_id, owner_tenant_id, tab, template_version, "
                "file_sha256, target_kind, target_ref, declared, imported_by) "
                "VALUES (%s,%s,%s,'offtake','gex-cost-tea-1',%s,'offtake_card',%s,%s,'test')",
                (iid, project_id, owner, "a" * 64, project_id, json.dumps({"buyers": {}})))
    return iid


def test_the_runtime_holds_select_and_insert_only():
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'gex_app' AND table_name = 'workbook_import'")
        assert {r[0] for r in cur.fetchall()} == {"SELECT", "INSERT"}
        cur.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'workbook_import'")
        assert cur.fetchone()[0] is True
    finally:
        conn.close()


def test_an_import_cannot_change_and_only_its_owner_reads_or_writes_it():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned(cur)
        cur.execute("SET LOCAL app.current_company_id = 'some_other_company'")
        cur.execute("SAVEPOINT s0")
        with pytest.raises(Exception):
            _insert(cur, project_id, owner)
        cur.execute("ROLLBACK TO SAVEPOINT s0")
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        iid = _insert(cur, project_id, owner)
        cur.execute("SET LOCAL app.current_company_id = 'some_other_company'")
        cur.execute("SELECT count(*) FROM workbook_import WHERE import_id = %s", (iid,))
        assert cur.fetchone()[0] == 0
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        cur.execute("SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("UPDATE workbook_import SET declared = '{}' WHERE import_id = %s", (iid,))
        cur.execute("ROLLBACK TO SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("DELETE FROM workbook_import WHERE import_id = %s", (iid,))
    finally:
        conn.rollback()
        conn.close()
