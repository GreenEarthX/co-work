"""
Alembic 066 — the Marketplace records live in PostgreSQL and every one says it is
UNVERIFIED (JML, 2026-10-23). Alembic 112 — they are the OWNING company's alone (and
GEX's): a stakeholder with project access reads none of them, because they hold the
producer's supplier prices, break-even and other buyers' deals (2026-11-13).

PostgreSQL parts run in the throwaway database (conftest.pg_store). The last
test is a source guard: MarketplacePage.tsx must not grow its constants back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pg_support import connect_dsn

OWNER, OTHER, PID = "test_mr_owner", "test_mr_other", "proj_TEST_marketplace_records"
STAKEHOLDER = "test_mr_stakeholder"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, OTHER, STAKEHOLDER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                "VALUES (%s, 'TEST records plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (PID, OWNER))
    cur.execute("INSERT INTO project_sales_detail (project_id, region, available, tokenised, source) VALUES "
                "(%s, 'TEST', '{\"volume_mtpd\": 10}', '{\"volume_mtpd\": 5}', 'TEST') ON CONFLICT DO NOTHING",
                (PID,))
    cur.execute("INSERT INTO project_input_line (project_id, seq, feedstock, ratio, ratio_unit, unit_price, "
                "price_unit, status, source) VALUES (%s, 1, 'TEST CO2', 1.46, 'MT/MT', 100, 'EUR/MT', "
                "'planned', 'TEST') ON CONFLICT DO NOTHING", (PID,))
    # F15: availability comes from these tokens, not from the record's stored figures above.
    cur.execute("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd) VALUES "
                "('cap_TEST_mr', %s, 'TEST', 'e-Methanol', 1000) ON CONFLICT DO NOTHING", (PID,))
    for tid, rate, state in (("tok_TEST_mr_a", 7, "MINTED"), ("tok_TEST_mr_b", 3, "RESERVED"),
                             ("tok_TEST_mr_c", 2, "MATCHED"), ("tok_TEST_mr_v", 50, "VOIDED")):
        cur.execute("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
                    "lifecycle_state, correlation_id, created_at) VALUES (%s, 'cap_TEST_mr', %s, '2028-01-01', "
                    "'2028-12-31', 'e-Methanol', %s, %s, now()::text) ON CONFLICT DO NOTHING", (tid, rate, state, tid))
    cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) "
                "VALUES (%s, %s, 'OFFTAKER', 'STAKEHOLDER', 'TEST') ON CONFLICT DO NOTHING", (PID, STAKEHOLDER))
    conn.commit()
    conn.close()
    return pg_store


def _economics_as(company):
    from app.core import market_engine as me
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company(company)
    try:
        return me.project_economics(me.Party(business_function="COMMERCIAL", user_id="u_test", company_id=company))
    finally:
        reset_current_company(token)


def test_the_projects_company_reads_its_records_marked_unverified(seeded):
    econ = _economics_as(OWNER)
    assert econ["sales_detail"][PID]["verification_state"] == "UNVERIFIED"
    assert [l["feedstock"] for l in econ["input_lines"][PID]] == ["TEST CO2"]
    assert econ["input_lines"][PID][0]["verification_state"] == "UNVERIFIED"


def test_another_company_reads_none_of_them(seeded):
    econ = _economics_as(OTHER)
    assert PID not in econ["sales_detail"] and PID not in econ["input_lines"]


def test_a_stakeholder_with_project_access_reads_none_of_them(seeded):
    """The leak 112 closes: project access (a prospective buyer) is not ownership."""
    from app.core.db_backend import market_connection

    conn = market_connection(company_id=STAKEHOLDER)
    try:
        seen = conn.execute("SELECT app_company_can_see_capacity(?, ?) AS v", (PID, STAKEHOLDER)).fetchone()
    finally:
        conn.close()
    assert seen["v"], "fixture: the stakeholder must be able to see the project, or this proves nothing"
    econ = _economics_as(STAKEHOLDER)
    assert PID not in econ["sales_detail"] and PID not in econ["input_lines"]


def test_gex_reads_them_to_curate(seeded):
    econ = _economics_as("PLATFORM_ADMIN")
    assert PID in econ["sales_detail"] and PID in econ["input_lines"]


def test_no_tenant_reads_nothing_and_only_gex_writes(seeded):
    assert _economics_as("__no_tenant_context__")["sales_detail"] == {}
    conn = connect_dsn(seeded)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = %s", (OWNER,))
    with pytest.raises(Exception, match="row-level security"):
        cur.execute("INSERT INTO project_input_line (project_id, seq, feedstock, ratio, ratio_unit, unit_price, "
                    "price_unit, status, source) VALUES (%s, 2, 'x', 1, 'MT/MT', 1, 'EUR/MT', 'spot', 'x')", (PID,))
    conn.rollback()
    conn.close()


def test_marketplace_page_holds_no_data_of_its_own():
    """The four constants, the 1,000 fallback price, the 330-day year and the
    synthetic chart (sine waves, the formula labelled 'Gabillon Forward') must not
    come back: figures on this screen come from PostgreSQL."""
    src = (FRONTEND / "features" / "marketplace" / "MarketplacePage.tsx").read_text()
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", src, flags=re.S)       # comments may name what was removed
    for forbidden in (r"\bconst\s+(MOLECULE_SPOT|PROJECT_SALES_DETAIL|PROJECT_FEEDSTOCK|INPUT_ENRICHMENT)\b",
                      r"Math\.sin", r"\?\?\s*1000\b", r"\*\s*330\b", r"Gabillon Forward", r"forwardCurve"):
        assert not re.search(forbidden, code), f"MarketplacePage.tsx: {forbidden}"



def test_availability_is_derived_from_the_owners_tokens_never_from_stored_figures(seeded):
    """F15: the record says 5 MTPD tokenised; the tokens say 7 + 3 + 2 (the voided 50 holds nothing)."""
    windows = _economics_as(OWNER)["token_windows"][PID]
    assert sorted((w["rate_mtpd"], w["state"]) for w in windows) == [(2.0, "MATCHED"), (3.0, "RESERVED"), (7.0, "MINTED")]
    assert windows[0]["start"] == "2028-01-01" and windows[0]["end"] == "2028-12-31"
    for company in (OTHER, STAKEHOLDER):          # commercial: not for project access, as 112
        assert PID not in _economics_as(company)["token_windows"]


def test_an_owned_project_without_tokens_has_an_empty_list_not_no_answer(seeded):
    conn = connect_dsn(seeded)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "('proj_TEST_mr_empty', 'TEST', %s, 'H2') ON CONFLICT DO NOTHING", (OWNER,))
    conn.commit()
    conn.close()
    assert _economics_as(OWNER)["token_windows"]["proj_TEST_mr_empty"] == []
    assert "proj_TEST_mr_empty" not in _economics_as(OTHER)["token_windows"]
