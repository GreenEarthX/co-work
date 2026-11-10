"""
M4 — the cashflow engine on the one contract model (spec §7, §10 T10; Phase 3, 2026-11-10).

T10, the golden migration: the Rotterdam contract in its OLD (JTI) form -> the
M2 converter's mapping -> the NEW engine (trading_book/flows.py, dispatch on
flow_type) gives the same cashflows as the OLD engine (trading_book/cashflows.py,
kept as the frozen reference), line by line: the same 180 months, quantity (to
the 6 decimals tb_flow stores), price, amount and allocated amount (to the cent),
estimate flag and note. The old form is built in memory, so the test outlives
M6's drop of the JTI tables; on 2026-11-10 it also passed against the JTI seed
written to the database and converted by jti_to_terms.run (same lines). And from
either party's side the amounts mirror (T06).

In the throwaway database (conftest.pg_store); the old seed is written as the
owner of that database, the conversion and the new engine run as the runtime.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from pg_support import connect_dsn

OWNER = "test_rotterdam_opco"
PID_JTI, PID_RECORD = "proj_TEST_rotterdam_h2", "proj_TEST_rotterdam_record"
FROM, TO = date(2027, 6, 1), date(2042, 5, 31)
CENT, QTY = Decimal("0.01"), Decimal("0.000001")


def _owner_dsn(pg_store):
    return os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1]


def _old_form(index_id: str):
    """The Rotterdam contract in its OLD (JTI) form, in memory: the old engine is pure
    code over these objects, so T10 outlives M6, which drops the JTI tables (alembic 088)."""
    import uuid
    from datetime import timedelta

    from app.trading_book import seed
    from app.trading_book.models import (Asset, ContractStatus, IndexHistory, IndexLinkedContract, PFLineItemType,
                                         ProjectFinanceLink)

    r = seed.ROTTERDAM
    asset = Asset(id=uuid.uuid4(), project_id=PID_JTI, name="Rotterdam H2 Hub Phase 1", location="Port of Rotterdam, NL",
                  country_code="NL", technology="PEM_ELECTROLYSIS", capacity_mw=Decimal("100.000"), is_active=True)
    contract = IndexLinkedContract(id=uuid.uuid4(), contract_number=r["contract_number"], fuel_type=r["fuel_type"],
                                   trade_date=date(2026, 5, 4), effective_date=r["effective_date"],
                                   termination_date=r["termination_date"], notional_quantity=r["notional_quantity"],
                                   quantity_unit=r["quantity_unit"], currency=r["currency"],
                                   status=ContractStatus.COMMITTED, index_definition_id=uuid.UUID(index_id),
                                   spread=r["index_spread"], floor=r["index_floor"], cap=r["index_cap"],
                                   fixing_rule=r["fixing_rule"], owner_company_id=OWNER)
    link = ProjectFinanceLink(id=uuid.uuid4(), project_asset_id=asset.id, contract_id=contract.id,
                              line_item_type=PFLineItemType.REVENUE, allocation_share=Decimal("1.000000"))
    start = seed.SEED_AS_OF - timedelta(days=seed.HISTORY_DAYS - 1)
    history = [IndexHistory(index_definition_id=contract.index_definition_id, observation_date=start + timedelta(days=i),
                            value=v) for i, v in enumerate(seed._make_history_values())]
    return asset, link, contract, history


@pytest.fixture(scope="module")
def golden(pg_store):
    from app.core import market_engine as me
    from app.db import session
    from app.trading_book import flows, seed
    from app.trading_book.cashflows import generate_cashflows_for_project

    saved = session._sync_engine            # never leak the throwaway URL into later modules
    session._sync_engine = None
    conn = connect_dsn(_owner_dsn(pg_store))
    cur = conn.cursor()
    cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                "(%s, 'TEST Rotterdam OpCo', 'PRODUCER', 'NL') ON CONFLICT DO NOTHING", (OWNER,))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST Rotterdam H2 Hub Phase 1', %s, 'H2') ON CONFLICT DO NOTHING", (PID_RECORD, OWNER))
    conn.commit()
    conn.close()

    mconn = me._conn()
    try:
        fixture = seed.seed_record(mconn, project_id=PID_RECORD, owner_company_id=OWNER)
        mconn.commit()
        asset, link, contract, history = _old_form(fixture["index_id"])
        old = generate_cashflows_for_project(asset, [(link, contract, history)], FROM, TO)
        new = flows.project_cashflows(mconn, fixture["asset_id"], "TEST Rotterdam", FROM, TO)
        names = {cp: me._row(mconn, "SELECT legal_name FROM tb_counterparty WHERE id = ?", (cp,))["legal_name"]
                 for cp in (fixture["buyer_cp"], fixture["seller_cp"])}
        buyer_side = flows.contract_lines(mconn, fixture["contract_id"], as_party=names[fixture["buyer_cp"]])
        seller_side = flows.contract_lines(mconn, fixture["contract_id"], as_party=names[fixture["seller_cp"]])
    finally:
        mconn.close()
    yield {"old": old, "new": new, "fixture": fixture, "buyer_side": buyer_side, "seller_side": seller_side}
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _line(r):
    return (r.period_start, r.period_end, r.quantity.quantize(QTY), r.price,
            r.gross_amount.quantize(CENT) if r.gross_amount is not None else None,
            r.allocated_amount.quantize(CENT) if r.allocated_amount is not None else None,
            r.sign, r.is_estimate)


def test_t10_the_converted_contract_gives_the_old_engines_cashflows_line_by_line(golden):
    """The old (JTI) form -> the M2 converter's mapping (seed_record builds the record
    contract through jti_to_terms.plan) -> the new engine == the old engine."""
    old, new = golden["old"].rows, golden["new"].rows
    assert len(old) == len(new) == 180                                # 15 years of months
    diffs = [(i, _line(a), _line(b)) for i, (a, b) in enumerate(zip(old, new)) if _line(a) != _line(b)]
    assert not diffs, diffs[:3]
    # The old engine's note says why a price is an estimate; the new one says the same.
    assert {r.notes.split(";")[0] for r in old} == {r.notes.split(";")[0] for r in new} \
        == {"extrapolated_from_2026-04-30"}


def test_t06_from_each_partys_side_the_amounts_mirror(golden):
    buyer, seller = golden["buyer_side"], golden["seller_side"]
    paid = [b.signed_amount for b in buyer if b.amount is not None]
    received = [s.signed_amount for s in seller if s.amount is not None]
    assert paid and all(p < 0 for p in paid) and all(r > 0 for r in received)
    assert all(p == -r for p, r in zip(paid, received)) and sum(paid) + sum(received) == 0


def test_t05_the_collar_holds_and_every_line_says_who_pays(golden):
    lines = golden["buyer_side"]
    priced = [line for line in lines if line.price is not None]
    assert all(Decimal("80") <= line.price <= Decimal("250") for line in priced)
    assert {line.payer for line in priced} == {"TEST BP plc (synthetic offtaker)"}
    assert {line.receiver for line in priced} == {"TEST Rotterdam H2 Hub OpCo BV"}
    assert {line.status for line in priced} == {"projected"}           # extrapolated, not fixed
