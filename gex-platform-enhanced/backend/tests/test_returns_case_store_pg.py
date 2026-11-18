"""
Migration 123 on PostgreSQL: a published returns case is immutable, insert-only for
the runtime, and readable only by the owning company or GEX. Every statement runs
in one transaction that is rolled back; nothing is written to the dev database.
"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.pg_support import pg_connect


def _owned_project(cur):
    cur.execute("SELECT project_id, owner_tenant_id FROM projects WHERE owner_tenant_id IS NOT NULL LIMIT 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("no owned project in this database")
    return row


def _insert(cur, project_id, owner):
    vid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO returns_case_version (version_id, case_id, project_id, owner_tenant_id, case_name, "
        "version_number, scenario, valuation_boundary, model_version, inputs, results, provenance, "
        "content_sha256, published_by) VALUES (%s,%s,%s,%s,'Base case',1,'BASE','FULL_PROJECT','1.3.0',"
        "%s,%s,%s,'h','test')",
        (vid, f"{project_id}:base-case:{vid[:6]}", project_id, owner, json.dumps({}),
         json.dumps({"unlevered_irr": 0.09}), json.dumps({})))
    return vid


def test_the_runtime_holds_select_and_insert_only():
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'gex_app' AND table_name = 'returns_case_version'")
        assert {r[0] for r in cur.fetchall()} == {"SELECT", "INSERT"}
    finally:
        conn.close()


def test_a_published_case_cannot_be_changed_or_deleted_and_only_its_owner_reads_it():
    """Rule: a published case is immutable once published (task 10); permissions
    control disclosure (owner and GEX read the store; others only through a share)."""
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        vid = _insert(cur, project_id, owner)
        cur.execute("SELECT count(*) FROM returns_case_version WHERE version_id = %s", (vid,))
        assert cur.fetchone()[0] == 1
        cur.execute("SET LOCAL app.current_company_id = 'some_other_company'")
        cur.execute("SELECT count(*) FROM returns_case_version WHERE version_id = %s", (vid,))
        assert cur.fetchone()[0] == 0
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        cur.execute("SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("UPDATE returns_case_version SET scenario = 'X' WHERE version_id = %s", (vid,))
        cur.execute("ROLLBACK TO SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("DELETE FROM returns_case_version WHERE version_id = %s", (vid,))
    finally:
        conn.rollback()
        conn.close()


def test_a_tenant_cannot_publish_for_a_project_it_does_not_own():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = 'not_the_owner'")
        with pytest.raises(Exception):
            _insert(cur, project_id, owner)
    finally:
        conn.rollback()
        conn.close()
