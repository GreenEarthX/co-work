"""
gex_platform/trading_book/seed.py

B1 seed fixture, in the one contract model (M4/M6, 2026-11-10): one green-H2
project end to end — seed_record() writes it.

    - Asset:           TEST Rotterdam H2 Hub Phase 1 (NL, 100 MW PEM, COD 2027-06-01)
    - Counterparties:  a synthetic offtaker and the plant's OpCo (off-platform, TEST)
    - IndexDefinition: Argus Green H2 NWE daily (EUR/MWh), TEST code
    - IndexHistory:    30 days of synthetic observations around €95-110/MWh
    - Contract:        a record contract — 15 years, 7.5M MWh total (≈500k MWh/yr),
                       EUR, index + €15.50/MWh, collar [€80, €250]/MWh, monthly average
    - ProjectFinanceLink: REVENUE for the project, allocated in full

GET /api/v1/trading-book/projects/{asset_id}/cashflows then returns 180 monthly
rows, every one priced from the latest fixing and flagged an estimate. The JTI
form of the same contract survives only in memory, as T10's reference
(tests/test_cashflows_m4_pg.py).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal


# Reference assessment date — set to a recent fixed date so seed is reproducible.
SEED_AS_OF = date(2026, 4, 30)
HISTORY_DAYS = 30


def _make_history_values(seed_value: int = 42) -> list[Decimal]:
    """30 daily observations around €100/MWh with mild noise. Reproducible."""
    rng = random.Random(seed_value)
    base = Decimal("100.00")
    out: list[Decimal] = []
    for i in range(HISTORY_DAYS):
        # gentle sinusoid-ish drift +/- 8 EUR, plus +/- 1.5 EUR noise
        from math import sin, pi
        drift = Decimal(str(round(8 * sin(2 * pi * i / 30), 2)))
        noise = Decimal(str(round(rng.uniform(-1.5, 1.5), 2)))
        out.append(base + drift + noise)
    return out


# ── The fixture, built in the one contract model (M4, 2026-11-10) ───────────
#
# The JTI seed that stood here wrote tables M6 dropped (alembic 088). This writes the Rotterdam case as a record
# contract — physical terms, a product leg OpCo -> BP, a float_cash payment leg on the
# Argus index with the €80–250 collar, one flow per month, payment on delivered quantity —
# with the same index history and a REVENUE link. The terms come from the M2 converter's
# own mapping of the same economics, so this fixture and a converted JTI contract cannot
# drift apart. TEST data: the names below are the spec's illustration, not a real deal.

ROTTERDAM = {"contract_number": "GEX-2026-H2-ROT-001", "fuel_type": "H2", "status": "committed",
             "effective_date": date(2027, 6, 1), "termination_date": date(2042, 5, 31),
             "notional_quantity": Decimal("7500000"), "quantity_unit": "MWh", "currency": "EUR",
             "index_spread": Decimal("15.50"), "index_floor": Decimal("80"), "index_cap": Decimal("250"),
             "fixing_rule": "month_avg", "price_basis": None, "fixed_price": None}


def seed_record(conn, *, project_id: str = "proj_TEST_rotterdam_h2",
                owner_company_id: str = "test_rotterdam_opco") -> dict:
    """Write the Rotterdam fixture in the record (`?`-placeholder connection, operator
    context). The project and the owner's tenant must exist. Returns its ids."""
    import uuid

    from app.trading_book import record
    from app.trading_book.migrate import jti_to_terms

    asset_id, bp, spv, idx = (str(uuid.uuid4()) for _ in range(4))
    conn.execute("INSERT INTO tb_asset (id, project_id, name, location, country_code, technology, capacity_mw, "
                 "cod_date, is_active, created_at, updated_at) VALUES (?, ?, 'TEST Rotterdam H2 Hub Phase 1', "
                 "'Port of Rotterdam, NL', 'NL', 'PEM_ELECTROLYSIS', 100.000, '2027-06-01', true, now(), now())",
                 (asset_id, project_id))
    for cp, name, country in ((bp, "TEST BP plc (synthetic offtaker)", "GB"),
                              (spv, "TEST Rotterdam H2 Hub OpCo BV", "NL")):
        conn.execute("INSERT INTO tb_counterparty (id, legal_name, country_code, is_active, created_at, updated_at) "
                     "VALUES (?, ?, ?, true, now(), now())", (cp, name, country))
    conn.execute("INSERT INTO tb_index_definition (id, provider, index_code, description, currency, unit_basis, "
                 "frequency, is_active, created_at, updated_at) VALUES (?, 'Argus', 'TEST-AGH2-NWE-DLY', "
                 "'TEST Argus Green Hydrogen NWE daily (synthetic history)', 'EUR', 'EUR/MWh', 'daily', true, "
                 "now(), now())", (idx,))
    start = SEED_AS_OF - timedelta(days=HISTORY_DAYS - 1)
    for i, v in enumerate(_make_history_values()):
        conn.execute("INSERT INTO tb_index_history (id, index_definition_id, observation_date, value, source_ref, "
                     "ingested_at) VALUES (gen_random_uuid(), ?, ?, ?, ?, now())",
                     (idx, start + timedelta(days=i), v, f"test-seed-{i:03d}"))
    terms, problems = jti_to_terms.plan(conn, {**ROTTERDAM, "id": None, "buy_side_id": bp, "sell_side_id": spv,
                                               "index_definition_id": idx})
    assert not problems, problems
    made = record.create_contract(conn, terms=terms, owner_company_id=owner_company_id, kind="trade",
                                  project_id=project_id, origin_ref=f"fixture:rotterdam:{project_id}",
                                  correlation_id=None, actor="TEST_FIXTURE_ROTTERDAM", company_id=owner_company_id,
                                  note="TEST fixture: Rotterdam H2 Hub Phase 1, built in the record (M4)",
                                  event_type="MIGRATED", reason="fixture", trade_status="confirmed")
    conn.execute("INSERT INTO tb_project_finance_link (id, project_asset_id, contract_id, line_item_type, "
                 "allocation_share, notes, created_at, updated_at) VALUES (gen_random_uuid(), ?, ?, 'REVENUE', 1, "
                 "'TEST fixture: full offtake, allocated in full', now(), now())", (asset_id, made["id"]))
    return {"asset_id": asset_id, "contract_id": made["id"], "buyer_cp": bp, "seller_cp": spv, "index_id": idx}
