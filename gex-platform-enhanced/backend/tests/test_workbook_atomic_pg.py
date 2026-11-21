"""A workbook save is all or nothing (19 Nov; JML: "prove transactional rollback").

On a throwaway database (pg_store), never the development store:
  - a financing case and the workbook import declared beside it are written in ONE
    transaction: when the import row is refused, the case is not left behind;
  - an offtake card and its import row likewise: when the import fails, the card and its
    contract versions are not saved;
  - a DRAFT financing case may lack a TEA run and terms; an ELIGIBLE one may not (127).
"""
from __future__ import annotations

import os
import uuid

import pytest

OWNER = "test_wb_owner"
PROJECT = "proj_TEST_workbook_atomic"


def _superuser(pg_url: str):
    from pg_support import connect_dsn
    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


def _su(url, sql, params=()):
    conn = _superuser(url)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [list(dict(r).values()) for r in cur.fetchall()] if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module")
def seeded(pg_store):
    _su(pg_store, "INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, 'TEST workbook owner', "
                  "'PRODUCER') ON CONFLICT DO NOTHING", (OWNER,))
    _su(pg_store, "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                  "(%s, 'TEST workbook atomic (synthetic)', %s, 'E_METHANOL') ON CONFLICT DO NOTHING", (PROJECT, OWNER))
    return pg_store


def _access():
    from types import SimpleNamespace
    return SimpleNamespace(project_id=PROJECT, project_name="TEST", owner_tenant=OWNER, user_id="cfo", basis="owner")


def _draft(previous=None):
    from app.core import calculation_chain as cc
    return cc.financing_draft_record(project_id=PROJECT, owner_tenant=OWNER, case_id=None, base_case=None,
                                     terms={"debt_eur": {"value": 1e8, "source": "indicative, bank call"}},
                                     previous=previous, case_latest=None, saved_by="cfo")


def _parsed(sha="a" * 64):
    return {"template_version": "gex-cost-tea-1", "file_sha256": sha}


def test_a_refused_import_row_leaves_no_financing_case(seeded):
    from app.api.v1 import routes_calculation_chain as r
    rec = _draft()
    bad = r._import_row(_access(), "financing", _parsed(sha="not-a-sha"), "financing_case_version",
                        rec["version_id"], rec["content_sha256"], {"capital_sources": []})
    with pytest.raises(Exception):
        r._insert_many(OWNER, [("financing_case_version", rec), ("workbook_import", bad)])
    assert _su(seeded, "SELECT count(*) FROM financing_case_version WHERE version_id = %s", (rec["version_id"],))[0][0] == 0
    good = r._import_row(_access(), "financing", _parsed(), "financing_case_version", rec["version_id"],
                         rec["content_sha256"], {"capital_sources": []})
    stored = r._insert_many(OWNER, [("financing_case_version", rec), ("workbook_import", good)])
    assert stored["status"] == "DRAFT" and stored["tea_claim_id"] is None and stored["fci_eur"] is None
    assert {l["code"] for l in stored["limitations"]} == {"NO_TEA_RUN", "TERMS_MISSING"}
    assert _su(seeded, "SELECT count(*) FROM workbook_import WHERE target_ref = %s", (rec["version_id"],))[0][0] == 1


def test_the_database_refuses_an_eligible_case_without_its_tea_run(seeded):
    from app.api.v1 import routes_calculation_chain as r
    rec = _draft()
    rec["status"] = "ELIGIBLE"
    rec["limitations"] = []
    with pytest.raises(Exception):
        r._insert_many(OWNER, [("financing_case_version", rec)])
    assert _su(seeded, "SELECT count(*) FROM financing_case_version WHERE version_id = %s", (rec["version_id"],))[0][0] == 0


def test_a_failed_import_row_leaves_the_offtake_card_unsaved(seeded):
    from app.api.v1.routes_bankability_proxy import save_card
    from app.core.contract_tokens import card_terms

    card = {"counterparty_name": "TEST buyer (synthetic)", "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80.0,
            "contracted_tonnes_per_year": 1000.0}

    def boom(conn):
        raise RuntimeError("import row refused")

    before = _su(seeded, "SELECT count(*) FROM tb_contract_version")[0][0]
    with pytest.raises(RuntimeError):
        save_card(PROJECT, "offtake", card, "cfo", OWNER, also=boom)
    assert not (card_terms(PROJECT).get("offtake") or {})
    assert _su(seeded, "SELECT count(*) FROM tb_contract_version")[0][0] == before

    from app.api.v1 import routes_calculation_chain as r
    imp = r._import_row(_access(), "offtake", _parsed(), "offtake_card", PROJECT, "b" * 64, {"buyers": {}})
    assert save_card(PROJECT, "offtake", card, "cfo", OWNER, also=lambda conn: r._insert_import(conn, imp))
    assert card_terms(PROJECT)["offtake"]["counterparty_name"] == "TEST buyer (synthetic)"
    assert _su(seeded, "SELECT count(*) FROM workbook_import WHERE import_id = %s", (imp["import_id"],))[0][0] == 1
