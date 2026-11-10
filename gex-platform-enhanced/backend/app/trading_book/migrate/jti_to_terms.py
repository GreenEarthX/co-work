"""
M2 — the JTI → terms converter (spec §8 M2; Phase 1 of "One contract record").

Each legacy contract (tb_contract with tb_contract_fixed_price or
tb_contract_index_linked) becomes ONE record contract: physical terms with a
product leg (seller → buyer) and a payment leg (buyer → seller), one flow per
calendar month of the tenor, exactly as the old cashflow engine
(trading_book/cashflows.py) splits it — flat quantity per month
(notional / months), fixed price per unit, or the index's monthly average
plus spread, clamped by floor and cap (fixing method `average` over the
month). Version 1, reason `migrated`, event MIGRATED.

Stops and reports — never guesses — when a contract has no buyer or seller, no
platform company behind a side, a fuel with no tb_commodity, a unit tb_unit
does not know, a status with no mapping, or a fixing rule other than
month_avg. M6 (alembic 088, 2026-11-10) dropped the JTI tables once nothing was left to
convert (0 rows, then and on 2026-11-06), and with them this module's run() and
command line. plan() stays: it is the mapping seed_record() builds the Rotterdam
fixture with, and the one T10 checks against the old engine line by line.

JTI status -> trade_status (no JTI row exists to test this against; see the
Phase 1 report): draft, proposed -> pending_confirmation; committed ->
confirmed (noted on the chain: committed in the JTI book, NOT confirmed
through TRADE_CONFIRM); terminated -> terminated; expired -> completed.

"""
from __future__ import annotations

from decimal import Decimal

from app.trading_book import record
from app.trading_book.cashflows import _count_months_in_tenor, _month_iter
from app.trading_book.terms import TermsIn

STATUS = {"draft": "pending_confirmation", "proposed": "pending_confirmation", "committed": "confirmed",
          "terminated": "terminated", "expired": "completed"}
UNITS = {"t", "MWh", "kg", "m3"}
ACTOR = "MIGRATION_M2_JTI_TO_TERMS"


def plan(conn, c: dict) -> tuple[TermsIn | None, list[str]]:
    """(terms, problems). Problems mean: stop and report this contract."""
    problems = []
    if not c.get("buy_side_id") or not c.get("sell_side_id"):
        problems.append("no explicit buyer and seller")
    status = (c.get("status") or "").lower()          # PostgreSQL stores the enum NAME: 'COMMITTED'
    if status not in STATUS:
        problems.append(f"status {c.get('status')!r} has no mapping")
    code = record.commodity_for_molecule(conn, c.get("fuel_type"))
    if code is None:
        problems.append(f"fuel {c.get('fuel_type')!r} has no tb_commodity")
    if c.get("quantity_unit") not in UNITS:
        problems.append(f"unit {c.get('quantity_unit')!r} is not a tb_unit")
    indexed = c.get("index_definition_id") is not None
    if indexed and c.get("fixing_rule") != "month_avg":
        problems.append(f"fixing rule {c.get('fixing_rule')!r} is not month_avg")
    if not indexed and c.get("fixed_price") is None:
        problems.append("neither a fixed price nor an index")
    months = _count_months_in_tenor(c["effective_date"], c["termination_date"]) if c.get("effective_date") else 0
    if months == 0:
        problems.append("empty tenor")
    if problems:
        return None, problems
    qty = (Decimal(c["notional_quantity"]) / Decimal(months)).quantize(Decimal("0.000001"))
    seller, buyer = str(c["sell_side_id"]), str(c["buy_side_id"])
    product, payment = [], []
    for i, (a, b) in enumerate(_month_iter(c["effective_date"], c["termination_date"]), start=1):
        product.append({"seq": i, "flow_type": "physical", "period_start": a, "period_end": b, "settle_date": b,
                        "quantity": qty, "unit": c["quantity_unit"]})
        pay = {"seq": i, "period_start": a, "period_end": b, "settle_date": b, "quantity": qty,
               "unit": c["quantity_unit"], "quantity_basis": "delivered", "quantity_source_flow": f"1.{i}"}
        if indexed:
            pay.update(flow_type="float_cash", index=str(c["index_definition_id"]), index_multiplier=1,
                       spread=c["index_spread"] or 0, floor=c["index_floor"], cap=c["index_cap"],
                       fixing_method="average", fixing_start=a, fixing_end=b)
        else:
            pay.update(flow_type="fixed_cash", unit_price=c["fixed_price"])
        payment.append(pay)
    clauses = []
    if not indexed and c.get("price_basis") and c["price_basis"] != "flat":
        clauses.append({"seq": 1, "clause_type": "price", "attrs": {"price_basis": c["price_basis"],
                        "note": "the JTI cashflow engine treated it as flat; so does this conversion"}})
    terms = TermsIn.model_validate({
        "settlement": "physical", "commodity": code, "currency": c["currency"],
        "legs": [{"seq": 1, "leg_role": "product", "payer": seller, "receiver": buyer, "flows": product},
                 {"seq": 2, "leg_role": "payment", "payer": buyer, "receiver": seller, "flows": payment}],
        "clauses": clauses})
    return terms, problems
