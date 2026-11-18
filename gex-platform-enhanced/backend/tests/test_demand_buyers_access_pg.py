"""
Alembic 113 — a project's buyer list (`project_dataset` kind `demand_buyers`) is read by
its owner, its mandated lender and GEX only. A buyer with project access must not read
the names of the buyers it competes with; an insurer or EPC contractor has no need to.
Every other dataset kind keeps the "may see the project" rule (069), so a stakeholder
still reads those — the second half of each check, so a fix that blanked the whole
table could not pass.

Read as `gex_app` in the throwaway database (conftest.pg_store), exactly as
GET /api/v1/projects/{id}/datasets/{kind} reads: the caller's tenant, RLS decides.
"""
from __future__ import annotations

import pytest

from pg_support import connect_dsn

PID = "proj_TEST_demand_buyers"
OWNER, BUYER, LENDER, INSURER, STRANGER = (
    "test_db_owner", "test_db_buyer", "test_db_lender", "test_db_insurer", "test_db_stranger")
ACCESS = {  # company -> (actor_type, access_role)
    BUYER: ("OFFTAKER", "STAKEHOLDER"),
    LENDER: ("COMMERCIAL_BANKER", "MANDATED_LENDER"),
    INSURER: ("INSURER", "MANDATED_INSURER"),
}


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company, ctype in ((OWNER, "PRODUCER"), (BUYER, "OFFTAKER"), (LENDER, "THIRD_PARTY"),
                           (INSURER, "THIRD_PARTY"), (STRANGER, "OFFTAKER")):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}", ctype))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                "VALUES (%s, 'TEST buyer-list plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (PID, OWNER))
    for company, (actor, role) in ACCESS.items():
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) "
                    "VALUES (%s, %s, %s, %s, 'TEST') ON CONFLICT DO NOTHING", (PID, company, actor, role))
    for kind, payload in (("demand_buyers", '["TEST rival buyer", "TEST buyer"]'),
                          ("offtake_quality", '{"TEST": true}')):
        cur.execute("INSERT INTO project_dataset (project_id, kind, payload, source) VALUES (%s, %s, %s, 'TEST') "
                    "ON CONFLICT DO NOTHING", (PID, kind, payload))
    conn.commit()
    conn.close()
    return pg_store


def _kinds_read_by(dsn, company):
    conn = connect_dsn(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute("SELECT kind FROM project_dataset WHERE project_id = %s ORDER BY kind", (PID,))
        return [r["kind"] for r in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()


def test_a_buyer_with_project_access_cannot_read_the_buyer_list(seeded):
    """The exposure 113 closes. offtake_quality proves the buyer CAN see the project."""
    assert _kinds_read_by(seeded, BUYER) == ["offtake_quality"]


def test_an_insurer_reads_the_projects_other_datasets_but_not_its_buyers(seeded):
    assert _kinds_read_by(seeded, INSURER) == ["offtake_quality"]


@pytest.mark.parametrize("company", [OWNER, LENDER, "PLATFORM_ADMIN"])
def test_owner_mandated_lender_and_gex_read_the_buyer_list(seeded, company):
    assert _kinds_read_by(seeded, company) == ["demand_buyers", "offtake_quality"]


def test_a_company_without_access_reads_nothing(seeded):
    assert _kinds_read_by(seeded, STRANGER) == []
