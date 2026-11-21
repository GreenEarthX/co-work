"""
TEST fixture: the dedicated project for the CFO workbook journey (JML, 19 Nov 2026).
=====================================================================================
JML decided on 19 Nov that the import / save / retrieve / amend / export journey runs on a
dedicated proj_TEST_ project, never on North Sea. This script creates it and removes it.

  project   proj_TEST_workbook_journey  "TEST — Workbook journey (synthetic)", owner hamburgone_com
            (the demo producer whose CFO account runs the journey), E_METHANOL, DE
  parties   two TEST buyer companies, granted project access as offtakers, so the offtake card
            can become a frame of two buyers

Every row carries the marker TEST_FIXTURE_WORKBOOK_JOURNEY (metadata_json / granted_by). --remove
deletes, scoped to this one project, everything the journey writes: workbook imports, financing
and cost basis versions, TEA runs, the contract record, project access, the project and the two
TEST tenants. Platform ledger events are NOT deleted: they are hash-chained; they name the
proj_TEST_ id, which is how they are recognised.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/load_workbook_journey_project.py [--remove] [--execute]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT = "proj_TEST_workbook_journey"
OWNER = "hamburgone_com"
MARKER = "TEST_FIXTURE_WORKBOOK_JOURNEY"
BUYERS = ("TEST Journey Buyer A", "TEST Journey Buyer B")


def _buyer_ids() -> list[str]:
    from app.core.project_registry import company_slug
    return [company_slug(n) for n in BUYERS]


def _connect():
    import psycopg2
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if not url:
        sys.exit("Export ALEMBIC_DATABASE_URL (the gex_user DSN) first.")
    return psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://"))


def load(cur) -> None:
    for name, cid in zip(BUYERS, _buyer_ids()):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'OFFTAKER', 'DE') ON CONFLICT (company_id) DO NOTHING", (cid, name))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, jurisdiction, country, "
                "metadata_json, created_by) VALUES (%s, %s, %s, 'E_METHANOL', 'EU', 'DE', %s, %s) "
                "ON CONFLICT (project_id) DO NOTHING",
                (PROJECT, "TEST — Workbook journey (synthetic)", OWNER, json.dumps({"test_fixture": MARKER}), MARKER))
    for cid in _buyer_ids():
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) "
                    "VALUES (%s, %s, 'OFFTAKER', 'STAKEHOLDER', %s) ON CONFLICT DO NOTHING", (PROJECT, cid, MARKER))


def remove(cur, execute: bool) -> None:
    import _fixture_record
    for table in ("workbook_import", "financing_case_version", "cost_basis_version", "model_base_case"):
        cur.execute(f"SELECT count(*) FROM {table} WHERE project_id = %s", (PROJECT,))
        n = cur.fetchone()[0]
        print(f"  {'delete' if execute else 'would delete'} {n} row(s) from {table}")
        if execute and n:
            cur.execute("SET LOCAL session_replication_role = replica")     # append-only triggers, this tx only
            cur.execute(f"DELETE FROM {table} WHERE project_id = %s", (PROJECT,))
            cur.execute("SET LOCAL session_replication_role = origin")
    _fixture_record.remove(cur, PROJECT, execute)
    if execute:
        cur.execute("DELETE FROM project_access WHERE project_id = %s", (PROJECT,))
        cur.execute("DELETE FROM projects WHERE project_id = %s AND created_by = %s", (PROJECT, MARKER))
        # The record made each TEST buyer a counterparty (per company, not per project); its contracts
        # are gone above. If anything else still references them, this refuses and nothing is removed.
        cur.execute("DELETE FROM tb_counterparty WHERE company_id = ANY(%s)", (_buyer_ids(),))
        cur.execute("DELETE FROM tenants WHERE company_id = ANY(%s) AND company_name LIKE 'TEST %%'", (_buyer_ids(),))


def main() -> int:
    execute, removing = "--execute" in sys.argv, "--remove" in sys.argv
    conn = _connect()
    try:
        cur = conn.cursor()
        if removing:
            remove(cur, execute)
        elif execute:
            load(cur)
        cur.execute("SELECT count(*) FROM projects WHERE project_id = %s", (PROJECT,))
        print(f"{PROJECT}: {'present' if cur.fetchone()[0] else 'absent'}"
              + ("" if execute else " (DRY RUN — nothing written; add --execute)"))
        if execute:
            conn.commit()
        else:
            conn.rollback()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
