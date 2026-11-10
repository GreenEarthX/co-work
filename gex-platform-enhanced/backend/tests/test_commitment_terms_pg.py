"""
Commitment cards on PostgreSQL — since Phase 3 of "One contract record" (Q9,
alembic 093) the cards are a view over the contract record, not a table.

058 created commitment_terms (the cards) and commitment_terms_events (their
history) and this file checked their tenant scope and that the runtime could not
rewrite the history. Both guarantees now belong to the record: a card is read
through the record's RLS (tb_contract / tb_terms / tb_sub_leg, alembic 064-092),
and its history is the record's append-only, hash-chained event log (083's
trigger; tests/test_contract_record.py, tests/test_contract_tokens_pg.py). The
tests of the two retired tables went with them; what stays is that they stay
retired, and that a company with nothing to do with a project reads none of its
cards through the view.

Runs against the development database read-only (as gex_app); skips when
PostgreSQL is unconfigured or down.
"""

from __future__ import annotations

import pytest

from pg_support import pg_connect, requires_pg

FIXTURE = "proj_TEST_gates_reference"


@pytest.mark.parametrize("table", ["commitment_terms", "commitment_terms_events"])
def test_the_card_tables_stay_retired(table):
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",))
        assert cur.fetchone()[0] is None, f"`{table}` is back: the cards are the record's (alembic 093)"
    finally:
        conn.close()


def test_an_unknown_company_reads_no_card_and_the_owner_reads_them():
    requires_pg()
    from app.core.contract_tokens import card_view
    from app.core.db_backend import NO_TENANT_CONTEXT, evidence_connection

    for company, expect_any in (("acme_totally_unrelated", False), (NO_TENANT_CONTEXT, False),
                                ("hamburgone_com", True)):
        conn = evidence_connection(company_id=company)
        try:
            cards = card_view(FIXTURE, conn=conn)
        finally:
            conn.close()
        assert bool(cards) is expect_any, (company, cards)
