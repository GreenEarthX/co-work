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
month_avg. Idempotent: a contract already converted (origin_ref 'jti:<id>')
is skipped. On 2026-11-06 there is nothing to convert (0 JTI rows).

JTI status -> trade_status (no JTI row exists to test this against; see the
Phase 1 report): draft, proposed -> pending_confirmation; committed ->
confirmed (noted on the chain: committed in the JTI book, NOT confirmed
through TRADE_CONFIRM); terminated -> terminated; expired -> completed.

    python -m app.trading_book.migrate.jti_to_terms --dry-run
    python -m app.trading_book.migrate.jti_to_terms --execute
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from app.trading_book import record, validation
from app.trading_book.cashflows import _count_months_in_tenor, _month_iter
from app.trading_book.terms import TermsIn

STATUS = {"draft": "pending_confirmation", "proposed": "pending_confirmation", "committed": "confirmed",
          "terminated": "terminated", "expired": "completed"}
UNITS = {"t", "MWh", "kg", "m3"}
ACTOR = "MIGRATION_M2_JTI_TO_TERMS"


def _jti_rows(conn) -> list[dict]:
    return record._rows(conn, """
        SELECT c.*, fp.fixed_price, fp.price_basis, il.index_definition_id, il.spread AS index_spread,
               il.floor AS index_floor, il.cap AS index_cap, il.fixing_rule,
               bs.company_id AS buyer_company, ss.company_id AS seller_company
        FROM tb_contract c
        LEFT JOIN tb_contract_fixed_price fp ON fp.id = c.id
        LEFT JOIN tb_contract_index_linked il ON il.id = c.id
        LEFT JOIN tb_counterparty bs ON bs.id = c.buy_side_id
        LEFT JOIN tb_counterparty ss ON ss.id = c.sell_side_id
        WHERE c.contract_type <> 'terms' ORDER BY c.contract_number""")


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


def run(conn, execute: bool) -> dict:
    report = {"considered": 0, "converted": [], "skipped_already_converted": [], "stopped": {}}
    from app.core.order_book import _ctx

    ctx = _ctx(conn)
    for c in _jti_rows(conn):
        report["considered"] += 1
        origin = f"jti:{c['id']}"
        if record.by_origin(conn, origin):
            report["skipped_already_converted"].append(c["contract_number"])
            continue
        terms, problems = plan(conn, c)
        if terms is not None:
            problems = [f"rule {code}" for code in validation.validate(terms, "contract", ctx)]
        if problems:
            report["stopped"][c["contract_number"]] = problems
            continue
        if execute:
            status = STATUS[c["status"].lower()]
            made = record.create_contract(
                conn, terms=terms, owner_company_id=c["owner_company_id"], kind="trade", project_id=None,
                origin_ref=origin, correlation_id=None, actor=ACTOR, company_id=None,
                note=f"migrated from JTI {c['contract_number']} ({c['contract_type']}, status {c['status']})"
                     + ("; committed in the JTI book, NOT confirmed through TRADE_CONFIRM"
                        if c["status"].lower() == "committed" else ""),
                event_type="MIGRATED", reason="migrated", trade_status=status)
            report["converted"].append({"from": c["contract_number"], "to": made["contract_ref"]})
        else:
            report["converted"].append({"from": c["contract_number"], "to": "(dry run)"})
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = ap.parse_args(argv)
    from app.core import market_engine as me

    conn = me._conn()
    try:
        report = run(conn, execute=args.execute)
        if args.execute and not report["stopped"]:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    print(f"considered {report['considered']}, converted {len(report['converted'])}, "
          f"already converted {len(report['skipped_already_converted'])}, stopped {len(report['stopped'])}"
          + (" (dry run: nothing written)" if args.dry_run else ""))
    for number, problems in report["stopped"].items():
        print(f"  STOPPED {number}: {'; '.join(problems)}")
    if args.execute and report["stopped"]:
        print("  nothing written: resolve the stopped contracts first")
    return 1 if report["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
