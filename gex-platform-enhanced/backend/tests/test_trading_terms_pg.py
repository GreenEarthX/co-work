"""
Alembic 065 on PostgreSQL — frozen terms, who sees orders and contracts, the views.

Runs in the throwaway database (conftest.pg_store), each test in ONE transaction
that is rolled back. Rows are written as PLATFORM_ADMIN and read back as each
TEST company: a seller with a one-sided order, a buyer who becomes its
counterparty on a contract, and a bystander.
"""
from __future__ import annotations

import pytest

from pg_support import connect_dsn

SELLER, BUYER, OTHER = "test_tt_seller", "test_tt_buyer", "test_tt_bystander"
CP_S, CP_B = "00000000-0000-4000-8000-0000000065a1", "00000000-0000-4000-8000-0000000065b1"
ORDER_TERMS, CONTRACT_TERMS = "00000000-0000-4000-8000-0000000065c1", "00000000-0000-4000-8000-0000000065c2"
ORDER, CONTRACT = "00000000-0000-4000-8000-0000000065d1", "00000000-0000-4000-8000-0000000065e1"


def _terms(cur, terms_id, owner, payer=None, receiver=None, frozen=False):
    cur.execute("INSERT INTO tb_terms (id, owner_company_id, settlement, commodity_id, currency) "
                "SELECT %s, %s, 'physical', id, 'EUR' FROM tb_commodity WHERE code = 'EMEOH'",
                (terms_id, owner))
    for seq, role, p, r, flow in ((1, "product", payer, receiver, "physical"),
                                  (2, "payment", receiver, payer, "fixed_cash")):
        cur.execute("INSERT INTO tb_leg (terms_id, leg_role, payer_id, receiver_id, seq) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id", (terms_id, role, p, r, seq))
        leg = cur.fetchone()["id"]
        cur.execute("INSERT INTO tb_flow (leg_id, seq, flow_type, period_start, period_end, settle_date, "
                    "quantity, unit, unit_price) VALUES (%s, 1, %s, '2027-01-01', '2027-01-31', "
                    "'2027-02-28', 1000, 't', %s)", (leg, flow, 900 if flow == "fixed_cash" else None))
    if frozen:
        cur.execute("UPDATE tb_terms SET frozen_at = now(), terms_hash = repeat('a', 64) WHERE id = %s",
                    (terms_id,))


@pytest.fixture
def cur(pg_store):
    conn = connect_dsn(pg_store)
    c = conn.cursor()
    c.execute("SET LOCAL ROLE gex_app")
    c.execute("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (SELLER, BUYER, OTHER):
        c.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER')",
                  (company, f"TEST {company}"))
    for cp, company in ((CP_S, SELLER), (CP_B, BUYER)):
        c.execute("INSERT INTO tb_counterparty (id, legal_name, country_code, is_active, created_at, "
                  "updated_at, company_id) VALUES (%s, %s, 'DE', true, now(), now(), %s)",
                  (cp, f"TEST {company}", company))
    _terms(c, ORDER_TERMS, SELLER, frozen=True)                    # one-sided: no parties
    c.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, valid_until, status) "
              "VALUES (%s, %s, 'sell', %s, now() + interval '30 days', 'open')", (ORDER, CP_S, ORDER_TERMS))
    _terms(c, CONTRACT_TERMS, SELLER, payer=CP_S, receiver=CP_B, frozen=True)
    c.execute("INSERT INTO tb_contract (id, contract_ref, trade_status, contract_type, created_at, updated_at) "
              "VALUES (%s, 'GEX-TB-TEST-000001', 'pending_confirmation', 'terms', now(), now())", (CONTRACT,))
    c.execute("INSERT INTO tb_contract_version (contract_id, version, terms_id, terms_hash, reason) "
              "VALUES (%s, 1, %s, repeat('a', 64), 'executed')", (CONTRACT, CONTRACT_TERMS))
    try:
        yield c
    finally:
        conn.rollback()
        conn.close()


def _as(cur, company):
    cur.execute("SET LOCAL app.current_company_id = %s", (company,))


def _count(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()["count"]


def _refused(cur, sql, params=(), match="TERMS_FROZEN|row-level security"):
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match=match):
        cur.execute(sql, params)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_t12_frozen_terms_cannot_change_for_any_role(cur):
    _refused(cur, "UPDATE tb_terms SET currency = 'USD' WHERE id = %s", (CONTRACT_TERMS,))
    _refused(cur, "UPDATE tb_flow SET quantity = 1 WHERE leg_id IN (SELECT id FROM tb_leg WHERE terms_id = %s)",
             (CONTRACT_TERMS,))
    _refused(cur, "DELETE FROM tb_leg WHERE terms_id = %s", (CONTRACT_TERMS,))
    _refused(cur, "INSERT INTO tb_leg (terms_id, leg_role, seq) VALUES (%s, 'payment', 3)", (CONTRACT_TERMS,))
    cur.execute("RESET ROLE")                                       # not even the owner of the tables
    _refused(cur, "UPDATE tb_terms SET currency = 'USD' WHERE id = %s", (CONTRACT_TERMS,), "TERMS_FROZEN")


def test_an_order_is_seen_by_its_owner_only(cur):
    for company, n in ((SELLER, 1), (BUYER, 0), (OTHER, 0), ("__no_tenant_context__", 0)):
        _as(cur, company)
        assert _count(cur, "SELECT count(*) FROM tb_order WHERE id = %s", (ORDER,)) == n, company
    _as(cur, BUYER)
    cur.execute("UPDATE tb_order SET status = 'cancelled' WHERE id = %s", (ORDER,))
    assert cur.rowcount == 0, "a non-owner changed someone's order"


def test_a_contract_is_seen_by_both_parties_and_no_one_else(cur):
    for company, n in ((SELLER, 1), (BUYER, 1), (OTHER, 0)):
        _as(cur, company)
        assert _count(cur, "SELECT count(*) FROM tb_contract WHERE id = %s", (CONTRACT,)) == n, company
        assert _count(cur, "SELECT count(*) FROM tb_contract_version WHERE contract_id = %s",
                      (CONTRACT,)) == n, company
        assert _count(cur, "SELECT count(*) FROM tb_flow f JOIN tb_leg l ON l.id = f.leg_id "
                           "WHERE l.terms_id = %s", (CONTRACT_TERMS,)) == 2 * n, company


def test_the_derived_book_is_signed_and_respects_rls(cur):
    _as(cur, BUYER)
    cur.execute("SELECT leg_role, direction, signed_quantity, signed_fixed_amount FROM v_party_flow "
                "WHERE contract_id = %s AND party_company_id = %s ORDER BY leg_role", (CONTRACT, BUYER))
    rows = {r["leg_role"]: r for r in cur.fetchall()}
    assert rows["product"]["direction"] == 1 and rows["product"]["signed_quantity"] == 1000
    assert rows["payment"]["direction"] == -1 and rows["payment"]["signed_fixed_amount"] == -900000
    _as(cur, OTHER)
    assert _count(cur, "SELECT count(*) FROM v_party_flow WHERE contract_id = %s", (CONTRACT,)) == 0
    _as(cur, SELLER)
    cur.execute("SELECT physical_qty, fixed_cash_amount FROM v_position WHERE party_company_id = %s", (SELLER,))
    assert dict(cur.fetchone()) == {"physical_qty": -1000, "fixed_cash_amount": 900000}


def test_the_order_trail_is_append_only(cur):
    _as(cur, SELLER)
    cur.execute("INSERT INTO tb_order_event (order_id, from_status, to_status, actor_id) "
                "VALUES (%s, 'draft', 'open', 'u_test')", (ORDER,))
    _refused(cur, "UPDATE tb_order_event SET reason = 'x' WHERE order_id = %s", (ORDER,), "permission denied")
    _refused(cur, "DELETE FROM tb_order_event WHERE order_id = %s", (ORDER,), "permission denied")


def test_a_contract_row_is_wholly_legacy_or_wholly_new(cur):
    _refused(cur, "INSERT INTO tb_contract (id, contract_type, created_at, updated_at) "
                  "VALUES (gen_random_uuid(), 'terms', now(), now())", match="ck_tb_contract_one_model")


# ── One token per contract; an amendment modifies it (JML, 2026-10-23) ─────

def _new_version(cur, n, event=None):
    terms = f"00000000-0000-4000-8000-00000000065{n}"
    _terms(cur, terms, SELLER, payer=CP_S, receiver=CP_B, frozen=True)
    cur.execute("UPDATE tb_contract_version SET superseded_at = now() WHERE contract_id = %s "
                "AND superseded_at IS NULL", (CONTRACT,))
    cur.execute("INSERT INTO tb_contract_version (contract_id, version, terms_id, terms_hash, reason, "
                "token_event_ref) VALUES (%s, %s, %s, repeat('b', 64), 'amendment', %s)",
                (CONTRACT, n, terms, event))


def test_an_amendment_is_a_modification_of_the_same_token(cur):
    # Version 2 cannot record a token modification before the contract has a token.
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="TOKEN_MISSING"):
        _new_version(cur, 2, event="tok-op:modify-1")
    cur.execute("ROLLBACK TO SAVEPOINT s")
    # Mint at confirmation: the contract gets its token, version 1 records the mint.
    cur.execute("UPDATE tb_contract SET token_ref = 'tok:TEST-1', trade_status = 'confirmed' WHERE id = %s",
                (CONTRACT,))
    cur.execute("UPDATE tb_contract_version SET token_event_ref = 'tok-op:mint' WHERE contract_id = %s "
                "AND version = 1", (CONTRACT,))
    _new_version(cur, 2, event="tok-op:modify-1")
    cur.execute("SELECT c.token_ref, v.version, v.token_event_ref FROM tb_contract c JOIN tb_contract_version v "
                "ON v.contract_id = c.id WHERE c.id = %s ORDER BY v.version", (CONTRACT,))
    rows = [tuple(r.values()) for r in cur.fetchall()]
    assert rows == [("tok:TEST-1", 1, "tok-op:mint"), ("tok:TEST-1", 2, "tok-op:modify-1")]


def test_the_token_is_never_replaced_or_shared(cur):
    cur.execute("UPDATE tb_contract SET token_ref = 'tok:TEST-1' WHERE id = %s", (CONTRACT,))
    _refused(cur, "UPDATE tb_contract SET token_ref = 'tok:TEST-2' WHERE id = %s", (CONTRACT,), "TOKEN_FIXED")
    _refused(cur, "UPDATE tb_contract SET token_ref = NULL WHERE id = %s", (CONTRACT,), "TOKEN_FIXED")
    _refused(cur, "INSERT INTO tb_contract (id, contract_ref, trade_status, contract_type, token_ref, created_at, "
                  "updated_at) VALUES (gen_random_uuid(), 'GEX-TB-TEST-000002', 'confirmed', 'terms', "
                  "'tok:TEST-1', now(), now())", match="unique|duplicate")
    cur.execute("UPDATE tb_contract_version SET token_event_ref = 'tok-op:mint' WHERE contract_id = %s", (CONTRACT,))
    _refused(cur, "UPDATE tb_contract_version SET token_event_ref = 'tok-op:other' WHERE contract_id = %s",
             (CONTRACT,), "TOKEN_FIXED")
