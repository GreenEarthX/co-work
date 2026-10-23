"""
Alembic 066 — the Marketplace records live in PostgreSQL, readable by the
project's companies only, and every one says it is UNVERIFIED (JML, 2026-10-23).

PostgreSQL parts run in the throwaway database (conftest.pg_store). The last
test is a source guard: MarketplacePage.tsx must not grow its constants back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pg_support import connect_dsn

OWNER, OTHER, PID = "test_mr_owner", "test_mr_other", "proj_TEST_marketplace_records"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, OTHER):
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
    conn.commit()
    conn.close()
    return pg_store


def _economics_as(company):
    from app.core import market_engine as me
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company(company)
    try:
        return me.project_economics(me.Party(user_id="u_test", company_id=company))
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
