"""
Alembic 064 on PostgreSQL — the trading book's tenant policies.

Replaces 036's admin-only lock, which test_marketplace_slice pinned "until assets
name a project". proj_bremen_h2 is owned by heliosnord_gmbh and shared with
allianz (project_access); etfuels_sa has nothing to do with it.

Every test runs in ONE transaction that is rolled back.
"""
from __future__ import annotations

import pytest

from pg_support import pg_connect

PID, OWNER, SHARED, STRANGER = "proj_bremen_h2", "heliosnord_gmbh", "allianz", "etfuels_sa"
ASSET, CONTRACT, LINK = ("00000000-0000-4000-8000-0000000064a1", "00000000-0000-4000-8000-0000000064c1",
                         "00000000-0000-4000-8000-0000000064f1")
BUY, SELL = "00000000-0000-4000-8000-0000000064b1", "00000000-0000-4000-8000-0000000064b2"
INSERT_CONTRACT = ("INSERT INTO tb_contract (id, contract_number, owner_company_id, buy_side_id, sell_side_id, "
                   "fuel_type, trade_date, effective_date, termination_date, notional_quantity, quantity_unit, "
                   "currency, status, contract_type, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, "
                   "'GREEN_H2', '2026-10-23', '2027-01-01', '2030-12-31', 1, 'MWh', 'EUR', 'DRAFT', "
                   "'fixed_price', now(), now())")
INSERT_ASSET = ("INSERT INTO tb_asset (id, project_id, name, location, country_code, technology, capacity_mw, "
                "is_active, created_at, updated_at) VALUES (%s, %s, 'gt asset', 'gt', 'DE', 'PEM', 1, true, "
                "now(), now())")


@pytest.fixture
def cur():
    conn = pg_connect()
    c = conn.cursor()
    c.execute("BEGIN")
    c.execute("SET LOCAL ROLE gex_app")
    c.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
    c.execute(INSERT_ASSET, (ASSET, PID))
    for cid, name in ((BUY, "gt buyer 064"), (SELL, "gt seller 064")):
        c.execute("INSERT INTO tb_counterparty (id, legal_name, country_code, is_active, created_at, updated_at) "
                  "VALUES (%s, %s, 'DE', true, now(), now())", (cid, name))
    c.execute(INSERT_CONTRACT, (CONTRACT, "gt-064-1", OWNER, BUY, SELL))
    c.execute("INSERT INTO tb_contract_fixed_price (id, fixed_price, price_basis) VALUES (%s, 1, 'flat')",
              (CONTRACT,))
    try:
        yield c
    finally:
        conn.rollback()
        conn.close()


def _as(cur, company):
    cur.execute("SET LOCAL app.current_company_id = %s", (company,))


def _count(cur, table, ident):
    cur.execute(f"SELECT count(*) FROM {table} WHERE id = %s", (ident,))
    return cur.fetchone()[0]


def _refused(cur, sql, params):
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="row-level security"):
        cur.execute(sql, params)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_the_projects_companies_see_the_asset_a_stranger_does_not(cur):
    for company, expected in ((OWNER, 1), (SHARED, 1), (STRANGER, 0), ("__no_tenant_context__", 0)):
        _as(cur, company)
        assert _count(cur, "tb_asset", ASSET) == expected, company


def test_a_contract_is_seen_by_its_book_and_through_a_linked_asset(cur):
    _as(cur, SHARED)
    assert _count(cur, "tb_contract", CONTRACT) == 0          # not linked yet
    _as(cur, OWNER)
    assert _count(cur, "tb_contract_fixed_price", CONTRACT) == 1
    cur.execute("INSERT INTO tb_project_finance_link (id, project_asset_id, contract_id, line_item_type, "
                "allocation_share, created_at, updated_at) VALUES (%s, %s, %s, 'REVENUE', 1, now(), now())",
                (LINK, ASSET, CONTRACT))
    _as(cur, SHARED)
    assert _count(cur, "tb_contract", CONTRACT) == 1
    assert _count(cur, "tb_contract_fixed_price", CONTRACT) == 1
    _as(cur, STRANGER)
    assert _count(cur, "tb_contract", CONTRACT) + _count(cur, "tb_project_finance_link", LINK) == 0


def test_only_the_owner_writes_the_asset(cur):
    for company in (SHARED, STRANGER):
        _as(cur, company)
        _refused(cur, INSERT_ASSET, ("00000000-0000-4000-8000-0000000064a2", PID))
    _as(cur, SHARED)
    cur.execute("UPDATE tb_asset SET name = 'gt renamed' WHERE id = %s", (ASSET,))
    assert cur.rowcount == 0, "a company with read access changed the asset"


def test_a_company_cannot_book_into_another_companys_book(cur):
    _as(cur, STRANGER)
    _refused(cur, INSERT_CONTRACT, ("00000000-0000-4000-8000-0000000064c2", "gt-064-2", OWNER, BUY, SELL))
    cur.execute(INSERT_CONTRACT, ("00000000-0000-4000-8000-0000000064c3", "gt-064-3", STRANGER, BUY, SELL))
    # ...and cannot allocate its own contract to someone else's asset.
    _refused(cur, "INSERT INTO tb_project_finance_link (id, project_asset_id, contract_id, line_item_type, "
                  "allocation_share, created_at, updated_at) VALUES (%s, %s, %s, 'REVENUE', 1, now(), now())",
             ("00000000-0000-4000-8000-0000000064f2", ASSET, "00000000-0000-4000-8000-0000000064c3"))


def test_indices_are_read_by_all_and_written_by_gex_only(cur):
    _as(cur, STRANGER)
    cur.execute("SELECT count(*) FROM tb_index_definition")
    _refused(cur, "INSERT INTO tb_index_definition (id, provider, index_code, currency, unit_basis, frequency, "
                  "is_active, created_at, updated_at) VALUES (%s, 'Argus', 'gt_064', 'EUR', 'MWh', 'daily', "
                  "true, now(), now())", ("00000000-0000-4000-8000-0000000064d1",))


def test_the_counterparty_register_is_closed_to_no_tenant_context(cur):
    _as(cur, "__no_tenant_context__")
    assert _count(cur, "tb_counterparty", BUY) == 0
    _as(cur, STRANGER)
    assert _count(cur, "tb_counterparty", BUY) == 1
    cur.execute("UPDATE tb_counterparty SET country_code = 'FR' WHERE id = %s", (BUY,))
    assert cur.rowcount == 0, "a tenant changed the shared counterparty register"
