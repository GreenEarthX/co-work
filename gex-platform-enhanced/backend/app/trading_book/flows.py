"""
Cashflows of the one contract record — spec §7, M4. Dispatch on flow_type, not
on contract subtype.

  physical     a quantity in a period; no amount
  fixed_cash   q × (unit_price + spread)
  float_cash   q × clamp(multiplier × fixing + spread, floor, cap); the fixing
               is the average / first / last of tb_index_history inside the
               fixing window. With no fixing in the window, a forward curve
               (ForwardCurveProvider) is used if one is given, else the latest
               earlier fixing — both flagged as estimates, as the JTI engine did.

q is the contracted quantity, or for quantity_basis = delivered the delivered
quantity of the product flow it pays for (its delivery), the contracted quantity
flagged projected until that delivery exists.

Each line carries its payer and receiver; `as_party` signs the amount from that
company's perspective (+ received, − paid), so the buyer's line is minus the
seller's (T06). Status: settled (a confirmed settlement inside the period),
fixed (price and quantity known), projected (anything estimated).

Pure arithmetic is in pricing.py; this module reads the record and assembles.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Protocol

from pydantic import BaseModel

from app.trading_book import pricing, record
from app.trading_book.conventions import FlowType, direction


class ForwardCurveProvider(Protocol):
    def get(self, index_id: str, on: date) -> Optional[Decimal]: ...


class FlowLine(BaseModel):
    contract_id: str
    contract_ref: str
    version: int
    leg_seq: int
    leg_role: str
    sub_leg: int
    flow_seq: int
    flow_type: str
    period_start: date
    period_end: date
    settle_date: date
    quantity: Decimal
    unit: str
    currency: Optional[str]
    price: Optional[Decimal] = None          # per unit, after spread and collar
    amount: Optional[Decimal] = None         # money, 2 dp; None for physical or an unpriceable float
    payer: Optional[str] = None              # company id (or the off-platform counterparty's name)
    receiver: Optional[str] = None
    signed_amount: Optional[Decimal] = None  # from as_party's perspective
    status: str = "fixed"
    is_estimate: bool = False
    note: Optional[str] = None


def index_fixing(history: list[tuple[date, Decimal]], method: str, start: date, end: date,
                 forward: Optional[ForwardCurveProvider] = None,
                 index_id: Optional[str] = None) -> tuple[Optional[Decimal], bool, Optional[str]]:
    """(fixing, is_estimate, note) for one window."""
    inside = [v for d, v in sorted(history) if start <= d <= end]
    if inside:
        return pricing.fixing(inside, method), False, None
    if forward is not None and index_id is not None:
        value = forward.get(index_id, end)
        if value is not None:
            return value, True, "forward_curve"
    prior = [(d, v) for d, v in sorted(history) if d <= end]
    if not prior:
        return None, True, "no_history"
    d, v = prior[-1]
    return v, True, f"extrapolated_from_{d.isoformat()}"


def _party_names(conn, ids) -> dict:
    out = {}
    for cp in {i for i in ids if i}:
        r = record._row(conn, "SELECT company_id, legal_name FROM tb_counterparty WHERE id = ?", (cp,))
        out[cp] = (r["company_id"] or r["legal_name"]) if r else None
    return out


def contract_lines(conn, contract_id: str, *, as_party: Optional[str] = None,
                   forward: Optional[ForwardCurveProvider] = None) -> list[FlowLine]:
    """Every flow of the contract's current version, priced."""
    c = record._row(conn, "SELECT * FROM tb_contract WHERE id = ?", (contract_id,))
    v = record.current_version(conn, contract_id)
    if c is None or v is None:
        raise record.RecordRefused(404, "CONTRACT_NOT_FOUND", "No contract with that id.")
    terms = record.load_terms(conn, str(v["terms_id"]))
    names = _party_names(conn, [p for leg in terms.legs for p in (leg.payer, leg.receiver)])
    histories: dict[str, list] = {}
    for leg in terms.legs:
        for f in leg.flows:
            if f.index and f.index not in histories:
                histories[f.index] = [(r["observation_date"], Decimal(r["value"])) for r in record._rows(
                    conn, "SELECT observation_date, value FROM tb_index_history WHERE index_definition_id = ?",
                    (f.index,))]
    delivered: dict[str, Decimal] = {}
    for r in record._rows(conn, "SELECT l.seq AS leg_seq, f.seq, d.volume_mt FROM tb_flow f JOIN tb_leg l ON "
                                "l.id = f.leg_id JOIN deliveries d ON d.id = f.delivery_id WHERE l.terms_id = ?",
                          (str(v["terms_id"]),)):
        delivered[f"{r['leg_seq']}.{r['seq']}"] = Decimal(str(r["volume_mt"]))
    settled = [r["settlement_date"] for r in record._rows(
        conn, "SELECT settlement_date FROM settlement_events WHERE contract_id = ? AND settlement_status = 'CONFIRMED'",
        (contract_id,)) if r["settlement_date"]]
    lines = []
    for leg in sorted(terms.legs, key=lambda l: l.seq):
        payer, receiver = names.get(leg.payer), names.get(leg.receiver)
        for f in sorted(leg.flows, key=lambda f: f.seq):
            line = FlowLine(contract_id=str(c["id"]), contract_ref=c["contract_ref"], version=v["version"],
                            leg_seq=leg.seq, leg_role=leg.leg_role.value, sub_leg=leg.sub_leg, flow_seq=f.seq,
                            flow_type=f.flow_type.value, period_start=f.period_start, period_end=f.period_end,
                            settle_date=f.settle_date, quantity=f.quantity, unit=f.unit, currency=terms.currency,
                            payer=payer, receiver=receiver)
            if f.flow_type != FlowType.PHYSICAL:
                q, projected = pricing.payment_quantity(f.quantity, f.quantity_basis,
                                                        delivered.get(f.quantity_source_flow or ""))
                line.quantity = q
                if f.flow_type == FlowType.FIXED_CASH:
                    line.price = f.unit_price + f.spread
                    line.amount = pricing.fixed_amount(q, f.unit_price, f.spread)
                    line.is_estimate = projected
                else:
                    fx, estimate, note = index_fixing(histories.get(f.index, []), f.fixing_method,
                                                      f.fixing_start, f.fixing_end, forward, f.index)
                    line.note = note
                    line.is_estimate = estimate or projected
                    if fx is not None:
                        line.price = pricing.clamp(f.index_multiplier * fx + f.spread, f.floor, f.cap)
                        line.amount = pricing.money(q * line.price)
                if projected:
                    line.note = ((line.note + ";") if line.note else "") + "quantity_projected"
                line.status = "projected" if line.is_estimate or line.amount is None else "fixed"
            if any(_in(d, f.period_start, f.period_end) for d in settled):
                line.status = "settled"
            if as_party is not None and line.amount is not None:
                line.signed_amount = line.amount * direction(as_party, payer, receiver)
            lines.append(line)
    return lines


def _in(d, start: date, end: date) -> bool:
    try:
        d = date.fromisoformat(str(d)[:10])
    except ValueError:
        return False
    return start <= d <= end


def project_cashflows(conn, asset_id: str, asset_name: str, from_date: date, to_date: date,
                      forward: Optional[ForwardCurveProvider] = None):
    """The project projection (the JTI engine's CashflowProjection shape) built from
    RECORD contracts linked to the asset (tb_project_finance_link): one row per
    payment flow overlapping the window, signed by the link's line item and scaled
    by its allocation. The JTI engine is the reference T10 compares this with."""
    import uuid as _uuid
    from collections import defaultdict

    from app.trading_book.cashflows import CashflowProjection, CashflowRow, PeriodSummary, sign_for_line_item
    from app.trading_book.models import PFLineItemType

    rows, withheld = [], 0
    for link in record._rows(conn, "SELECT l.*, c.contract_type FROM tb_project_finance_link l JOIN tb_contract c "
                                   "ON c.id = l.contract_id WHERE l.project_asset_id = ? AND c.contract_type = 'terms'",
                             (asset_id,)):
        raw = str(link["line_item_type"])         # PostgreSQL stores the enum NAME ('REVENUE')
        item = PFLineItemType[raw] if raw in PFLineItemType.__members__ else PFLineItemType(raw)
        sign, share = sign_for_line_item(item), Decimal(link["allocation_share"])
        if record.current_version(conn, str(link["contract_id"])) is None:
            withheld += 1                 # its terms are not the caller's to read (RLS): counted, never guessed
            continue
        for line in contract_lines(conn, str(link["contract_id"]), forward=forward):
            if line.flow_type == "physical" or line.period_end < from_date or line.period_start > to_date:
                continue
            rows.append(CashflowRow(
                period_start=line.period_start, period_end=line.period_end, line_item_type=item,
                contract_id=_uuid.UUID(line.contract_id), contract_number=line.contract_ref,
                currency=line.currency or "", quantity=line.quantity, quantity_unit=line.unit, price=line.price,
                gross_amount=line.amount, sign=sign, allocation_share=share,
                allocated_amount=line.amount * sign * share if line.amount is not None else None,
                is_estimate=line.is_estimate, notes=line.note))
    rows.sort(key=lambda r: (r.period_start, r.contract_number))
    by_item: dict[str, Decimal] = defaultdict(Decimal)
    by_period: dict = defaultdict(lambda: defaultdict(Decimal))
    for r in rows:
        if r.allocated_amount is not None:
            by_item[r.line_item_type.value] += r.allocated_amount
            by_period[(r.period_start, r.period_end)][r.line_item_type.value] += r.allocated_amount
    estimates = sum(1 for r in rows if r.is_estimate)
    return CashflowProjection(
        project_asset_id=_uuid.UUID(str(asset_id)), project_name=asset_name, from_date=from_date, to_date=to_date,
        granularity="monthly", rows=rows, summary_by_line_item=dict(by_item),
        summary_by_period=[PeriodSummary(period_start=a, period_end=b, by_line_item=dict(v),
                                         net=sum(v.values(), Decimal(0))) for (a, b), v in sorted(by_period.items())],
        has_estimates=estimates > 0, estimate_period_count=estimates, withheld_contract_count=withheld)
