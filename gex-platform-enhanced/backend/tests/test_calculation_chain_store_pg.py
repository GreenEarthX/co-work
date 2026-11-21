"""
Migration 124 on PostgreSQL: a saved cost basis and a financing case are immutable,
insert-only for the runtime, and readable only by the owning company or GEX. Every
statement runs in one transaction that is rolled back; nothing reaches the dev database.
"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.pg_support import pg_connect

TABLES = ("cost_basis_version", "financing_case_version")


def _owned_project(cur):
    cur.execute("SELECT project_id, owner_tenant_id FROM projects WHERE owner_tenant_id IS NOT NULL LIMIT 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("no owned project in this database")
    return row


def _insert_cost_basis(cur, project_id, owner):
    vid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO cost_basis_version (version_id, project_id, owner_tenant_id, version_number, molecule, "
        "configuration, result, catalogue_sha256, content_sha256, saved_by, status) "
        "VALUES (%s,%s,%s,(SELECT coalesce(max(version_number),0)+1 FROM cost_basis_version WHERE project_id=%s),"
        "'E_METHANOL',%s,%s,'c','h','test','READY')",
        (vid, project_id, owner, project_id, json.dumps({}), json.dumps({})))
    return vid


@pytest.mark.parametrize("table", TABLES)
def test_the_runtime_holds_select_and_insert_only(table):
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'gex_app' AND table_name = %s", (table,))
        assert {r[0] for r in cur.fetchall()} == {"SELECT", "INSERT"}
        cur.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", (table,))
        assert cur.fetchone()[0] is True
    finally:
        conn.close()


def test_a_saved_cost_basis_cannot_change_and_only_its_owner_reads_it():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        vid = _insert_cost_basis(cur, project_id, owner)
        cur.execute("SET LOCAL app.current_company_id = 'some_other_company'")
        cur.execute("SELECT count(*) FROM cost_basis_version WHERE version_id = %s", (vid,))
        assert cur.fetchone()[0] == 0
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        cur.execute("SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("UPDATE cost_basis_version SET molecule = 'X' WHERE version_id = %s", (vid,))
        cur.execute("ROLLBACK TO SAVEPOINT s1")
        with pytest.raises(Exception):
            cur.execute("DELETE FROM cost_basis_version WHERE version_id = %s", (vid,))
    finally:
        conn.rollback()
        conn.close()


def test_a_tenant_cannot_save_for_a_project_it_does_not_own():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = 'some_other_company'")
        with pytest.raises(Exception):
            _insert_cost_basis(cur, project_id, owner)
    finally:
        conn.rollback()
        conn.close()


def _financing_insert(cur, project_id, owner, status, debt, limitations="[]"):
    cur.execute(
        "INSERT INTO financing_case_version (version_id, project_id, owner_tenant_id, version_number, "
        "tea_claim_id, tea_cost_basis_hash, fci_eur, debt_eur, interest_rate, debt_tenor_years, grant_eur, "
        "terms, content_sha256, saved_by, case_id, status, limitations) "
        "VALUES (%s,%s,%s,(SELECT coalesce(max(version_number),0)+1 FROM financing_case_version WHERE project_id=%s),"
        "'c','h',100,%s,0.05,10,20,'{}','h','t',%s,%s,%s)",
        (str(uuid.uuid4()), project_id, owner, project_id, debt, str(uuid.uuid4()), status, limitations))


def test_financing_debt_plus_grant_cannot_exceed_fci():
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))
        cur.execute("SAVEPOINT s1")
        with pytest.raises(Exception) as e:
            _financing_insert(cur, project_id, owner, "ELIGIBLE", 90)          # 90 + 20 > 100
        assert "financing_case_version_eligible_complete" in str(e.value)       # the rule, not a missing column
        cur.execute("ROLLBACK TO SAVEPOINT s1")
        _financing_insert(cur, project_id, owner, "ELIGIBLE", 80)               # within fixed capital
        _financing_insert(cur, project_id, owner, "DRAFT", 90,                  # a draft may exceed it, said
                          '[{"code": "DEBT_EXCEEDS_FCI", "detail": "x"}]')
    finally:
        conn.rollback()
        conn.close()


def test_an_eligible_case_is_bounded_by_its_defined_uses_not_by_fixed_capital():
    """128: with uses defined, debt + grant may exceed fixed capital (100) up to the uses (150)."""
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
        project_id, owner = _owned_project(cur)
        cur.execute("SET LOCAL app.current_company_id = %s", (owner,))

        def eligible(debt, uses):
            cur.execute(
                "INSERT INTO financing_case_version (version_id, project_id, owner_tenant_id, version_number, "
                "tea_claim_id, tea_cost_basis_hash, fci_eur, debt_eur, interest_rate, debt_tenor_years, grant_eur, "
                "terms, content_sha256, saved_by, case_id, status, limitations, uses_total_eur) "
                "VALUES (%s,%s,%s,(SELECT coalesce(max(version_number),0)+1 FROM financing_case_version WHERE "
                "project_id=%s),'c','h',100,%s,0.05,10,20,'{}','h','t',%s,'ELIGIBLE','[]',%s)",
                (str(uuid.uuid4()), project_id, owner, project_id, debt, str(uuid.uuid4()), uses))

        eligible(120, 150)                                   # 140 > 100 fixed capital, within 150 uses
        cur.execute("SAVEPOINT s1")
        with pytest.raises(Exception) as e:
            eligible(140, 150)                               # 160 > 150 uses
        assert "financing_case_version_eligible_complete" in str(e.value)
    finally:
        conn.rollback()
        conn.close()
