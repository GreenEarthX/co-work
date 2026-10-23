"""
Migration 063's policies on PostgreSQL — who sees which piece of a trade.

A trade has a seller (the project owner, resolved through
app_company_can_see_capacity) and a buyer (named on the row). Each of them sees
the RFQ / match / contract / settlement / token it is party to; nobody else
does. Before 063 a buyer could not see its own match, contract or the token it
had bought, because every policy resolved through the seller's project only.

Every test runs in ONE transaction that is rolled back — nothing reaches the
dev database. Rows are written as PLATFORM_ADMIN, read back as each tenant.
"""
from __future__ import annotations

import pytest

from pg_support import pg_connect

PID = "proj_bremen_h2"                     # owner heliosnord_gmbh (test_marketplace_slice)
SELLER, BUYER, STRANGER = "heliosnord_gmbh", "gt_test_buyer_co", "gt_test_stranger_co"
NOW = "2026-10-23T00:00:00+00:00"


@pytest.fixture
def cur():
    conn = pg_connect()
    c = conn.cursor()
    c.execute("BEGIN")
    c.execute("SET LOCAL ROLE gex_app")
    c.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
    c.execute("INSERT INTO tokens (id, capacity_id, lifecycle_state, holder_company_id) "
              "VALUES ('gt_tok_sold', %s, 'SETTLED', %s)", (PID, BUYER))
    c.execute("INSERT INTO rfqs (id, buyer_company_id, molecule, volume_mtpd, delivery_start, "
              "delivery_end, created_at) VALUES ('gt_rfq', %s, 'E_METHANOL', 1, '2027-01-01', "
              "'2027-12-31', %s)", (BUYER, NOW))
    c.execute("INSERT INTO matches (id, project_id, token_id, seller_company_id, buyer_company_id) "
              "VALUES ('gt_match', %s, 'gt_tok_sold', %s, %s)", (PID, SELLER, BUYER))
    c.execute("INSERT INTO contracts (id, project_id, match_id, seller_company_id, buyer_company_id, "
              "created_at) VALUES ('gt_contract', %s, 'gt_match', %s, %s, %s)", (PID, SELLER, BUYER, NOW))
    c.execute("INSERT INTO settlement_events (settlement_id, contract_id, project_id, token_id, "
              "counterparty_buyer_id, counterparty_seller_id, settlement_type, settlement_status, "
              "volume_kg, price_per_kg, total_amount, currency, audit_hash, version, created_at, "
              "updated_at) VALUES ('gt_settle', 'gt_contract', %s, 'gt_tok_sold', %s, %s, 'SPOT', "
              "'PENDING', 1, 1, 1, 'EUR', 'x', 1, %s, %s)", (PID, BUYER, SELLER, NOW, NOW))
    try:
        yield c
    finally:
        conn.rollback()
        conn.close()


def _sees(cur, company: str) -> dict:
    cur.execute("SET LOCAL app.current_company_id = %s", (company,))
    out = {}
    for table, key, ident in (("rfqs", "id", "gt_rfq"), ("matches", "id", "gt_match"),
                              ("contracts", "id", "gt_contract"), ("tokens", "id", "gt_tok_sold"),
                              ("settlement_events", "settlement_id", "gt_settle")):
        cur.execute(f"SELECT count(*) FROM {table} WHERE {key} = %s", (ident,))
        out[table] = cur.fetchone()[0]
    return out


def test_the_buyer_sees_every_piece_of_its_own_trade(cur):
    assert _sees(cur, BUYER) == {"rfqs": 1, "matches": 1, "contracts": 1, "tokens": 1,
                                 "settlement_events": 1}


def test_the_seller_sees_its_trade_but_not_the_buyers_rfq(cur):
    # The RFQ is the buyer's own request; the seller sees it only as an anonymised
    # listing, which the market engine serves.
    assert _sees(cur, SELLER) == {"rfqs": 0, "matches": 1, "contracts": 1, "tokens": 1,
                                  "settlement_events": 1}


def test_a_stranger_sees_nothing(cur):
    assert set(_sees(cur, STRANGER).values()) == {0}


def test_no_tenant_context_sees_nothing(cur):
    assert set(_sees(cur, "NO_TENANT_CONTEXT").values()) == {0}


def test_a_tenant_cannot_write_an_rfq_in_another_companys_name(cur):
    cur.execute("SET LOCAL app.current_company_id = %s", (STRANGER,))
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="row-level security"):
        cur.execute("INSERT INTO rfqs (id, buyer_company_id, molecule, volume_mtpd, delivery_start, "
                    "delivery_end, created_at) VALUES ('gt_rfq_forged', %s, 'E_METHANOL', 1, "
                    "'2027-01-01', '2027-12-31', %s)", (BUYER, NOW))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_a_tenant_cannot_make_itself_the_buyer_of_someone_elses_contract(cur):
    cur.execute("SET LOCAL app.current_company_id = %s", (STRANGER,))
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="row-level security"):
        cur.execute("INSERT INTO contracts (id, project_id, seller_company_id, buyer_company_id, "
                    "created_at) VALUES ('gt_contract_forged', %s, %s, %s, %s)",
                    (PID, SELLER, BUYER, NOW))
    cur.execute("ROLLBACK TO SAVEPOINT s")
