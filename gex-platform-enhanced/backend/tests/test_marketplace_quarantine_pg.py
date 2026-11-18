"""
D-A (JML 2026-11-16; R6, F07; alembic 120): no confirmation without evidence, and history kept.

A Marketplace record (sales detail, input line, input classification) becomes CONFIRMED or AUDITED
only with a recorded document (`evidence_sha256`) and a confirmer other than its importer. Every
change of state is written to `marketplace_record_history` by the trigger, with the confirmation it
replaced; the runtime cannot write or alter that history, and nobody can change or delete it.
"""
from __future__ import annotations

import os

import psycopg2
import pytest

from app.core import project_registry as reg
from pg_support import connect_dsn

PID, OTHER_PID = "proj_TEST_quarantine", "proj_TEST_quarantine_other"
OWNER, OTHER = "TEST Quarantine Owner", "TEST Quarantine Other"
O_ID, X_ID = reg.company_slug(OWNER), reg.company_slug(OTHER)
DOC = "d" * 64
DSN: dict = {}


def _conn(company="PLATFORM_ADMIN", admin=False):
    url = (os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + DSN["url"].rsplit("/", 1)[1]) if admin else DSN["url"]
    conn = connect_dsn(url)
    conn.cursor().execute("SET app.current_company_id = %s", (company,))
    return conn


def _q(sql, params=(), company="PLATFORM_ADMIN"):
    conn = _conn(company)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    DSN["url"] = pg_store
    for company, pid in ((OWNER, PID), (OTHER, OTHER_PID)):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,'PRODUCER','DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company))
        _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,%s,%s,'e-Methanol') "
           "ON CONFLICT DO NOTHING", (pid, f"TEST {pid}", reg.company_slug(company)))
    _q("INSERT INTO project_sales_detail (project_id, region, source, created_by, verification_state) "
       "VALUES (%s, 'TEST', 'TEST importer load', 'importer', 'UNVERIFIED') ON CONFLICT DO NOTHING", (PID,))
    yield


def _confirm(by, evidence, state="CONFIRMED"):
    return _q("UPDATE project_sales_detail SET verification_state = %s, verified_by = %s, verified_at = now(), "
              "evidence_sha256 = %s WHERE project_id = %s", (state, by, evidence, PID))


@pytest.mark.parametrize("by, evidence", [("reviewer", None), ("importer", DOC)])
def test_a_confirmation_needs_a_document_and_someone_other_than_the_importer(by, evidence):
    with pytest.raises(psycopg2.Error, match="CONFIRMATION_NEEDS_EVIDENCE"):
        _confirm(by, evidence)
    with pytest.raises(psycopg2.Error, match="CONFIRMATION_NEEDS_EVIDENCE"):
        _confirm(by, evidence, state="AUDITED")


def test_an_insert_cannot_arrive_confirmed_without_evidence():
    with pytest.raises(psycopg2.Error, match="CONFIRMATION_NEEDS_EVIDENCE"):
        _q("INSERT INTO input_classification (feedstock, item_type, source, created_by, verification_state, verified_by, "
           "verified_at) VALUES ('TEST feedstock', 'TEST', 'TEST', 'importer', 'CONFIRMED', 'someone', now())")


def test_a_confirmation_with_evidence_is_kept_in_the_history_and_so_is_its_withdrawal():
    _confirm("reviewer", DOC)
    _q("UPDATE project_sales_detail SET verification_state = 'UNVERIFIED', verified_by = NULL, verified_at = NULL, "
       "evidence_sha256 = NULL, quarantine_reason = 'TEST withdrawn' WHERE project_id = %s", (PID,))
    rows = _q("SELECT from_state, to_state, prior_verified_by, verified_by, evidence_sha256, reason FROM "
              "marketplace_record_history WHERE record_key->>'project_id' = %s ORDER BY id", (PID,))
    assert [(r["from_state"], r["to_state"]) for r in rows] == [("UNVERIFIED", "CONFIRMED"), ("CONFIRMED", "UNVERIFIED")]
    assert (rows[0]["verified_by"], rows[0]["evidence_sha256"]) == ("reviewer", DOC)
    assert (rows[1]["prior_verified_by"], rows[1]["reason"]) == ("reviewer", "TEST withdrawn")


def test_the_history_is_the_owners_and_gex_and_nobody_writes_or_changes_it():
    assert _q("SELECT count(*) AS n FROM marketplace_record_history WHERE record_key->>'project_id' = %s", (PID,),
              company=O_ID)[0]["n"] == 2
    assert _q("SELECT count(*) AS n FROM marketplace_record_history WHERE record_key->>'project_id' = %s", (PID,),
              company=X_ID)[0]["n"] == 0
    for sql in ("INSERT INTO marketplace_record_history (table_name, record_key, from_state, to_state) "
                "VALUES ('project_sales_detail', '{}', 'UNVERIFIED', 'CONFIRMED')",
                "UPDATE marketplace_record_history SET reason = 'x'"):
        conn = _conn()
        try:
            with pytest.raises(psycopg2.Error, match="permission denied"):
                conn.cursor().execute(sql)
        finally:
            conn.rollback()
            conn.close()
    for sql in ("UPDATE marketplace_record_history SET reason = 'x'", "DELETE FROM marketplace_record_history"):
        conn = _conn(admin=True)
        try:
            with pytest.raises(psycopg2.Error, match="APPEND_ONLY"):
                conn.cursor().execute(sql)
        finally:
            conn.rollback()
            conn.close()
