"""
gex_platform/trading_book/cashflows.py

Cashflow generator for B1.

Design:
    - Pure functions over ORM objects + a list of IndexHistory rows.
      No DB I/O in the generator itself; the API layer fetches and passes in.
    - Monthly granularity by default (calendar months).
    - Flat amortization of notional_quantity across periods (B1 simplification;
      B2 will support custom schedules via a CashflowSchedule table).
    - For IndexLinkedContract, period price = avg(IndexHistory in period) +
      spread, clamped by floor/cap.
    - For periods beyond available IndexHistory, forward-extrapolate the last
      observed value and flag is_estimate=True. This gives the heatmap
      something to stress without claiming we have data we don't.

Sign convention (project's perspective):
    REVENUE        -> +1 (cash in)
    OPEX           -> -1 (cash out)
    DEBT_SERVICE   -> -1
    CAPEX          -> -1
"""

from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.trading_book.models import (
    Asset,
    Contract,
    FixedPriceContract,
    IndexHistory,
    IndexLinkedContract,
    PFLineItemType,
    ProjectFinanceLink,
)


# ──────────────────────────────────────────────────────────────────────
# Sign convention
# ──────────────────────────────────────────────────────────────────────

_SIGN_BY_LINE_ITEM: dict[PFLineItemType, int] = {
    PFLineItemType.REVENUE: 1,
    PFLineItemType.OPEX: -1,
    PFLineItemType.DEBT_SERVICE: -1,
    PFLineItemType.CAPEX: -1,
}


def sign_for_line_item(line_item_type: PFLineItemType) -> int:
    """+1 for inflows (REVENUE), -1 for outflows."""
    return _SIGN_BY_LINE_ITEM[line_item_type]


# ──────────────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────────────


class CashflowRow(BaseModel):
    """One period's cashflow contribution from one (Contract, PFLink) pair."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    period_start: date
    period_end: date
    line_item_type: PFLineItemType
    contract_id: uuid.UUID
    contract_number: str
    currency: str
    quantity: Decimal
    quantity_unit: str
    price: Optional[Decimal]
    # ^^^ None when no IndexHistory at all (empty index). Otherwise always set,
    # but is_estimate flags forward-extrapolation.
    gross_amount: Optional[Decimal]
    sign: int
    allocation_share: Decimal
    allocated_amount: Optional[Decimal]
    is_estimate: bool
    notes: Optional[str] = None


class PeriodSummary(BaseModel):
    period_start: date
    period_end: date
    by_line_item: dict[str, Decimal]
    net: Decimal


class CashflowProjection(BaseModel):
    project_asset_id: uuid.UUID
    project_name: str
    from_date: date
    to_date: date
    granularity: str
    rows: List[CashflowRow]
    summary_by_line_item: dict[str, Decimal] = Field(default_factory=dict)
    summary_by_period: List[PeriodSummary] = Field(default_factory=list)
    has_estimates: bool = False
    estimate_period_count: int = 0


# ──────────────────────────────────────────────────────────────────────
# Period iteration
# ──────────────────────────────────────────────────────────────────────


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_iter(start: date, end: date) -> Iterator[Tuple[date, date]]:
    """Yield (period_start, period_end) for each calendar month overlapping
    [start, end] (inclusive). period_start = 1st of month or `start` if first;
    period_end = last day of month or `end` if last.

    Note: B1 treats partial-month boundaries as full months (no day-prorating).
    B2 will day-prorate via CashflowSchedule.
    """
    if start > end:
        return
    cur_year, cur_month = start.year, start.month
    while True:
        period_start = date(cur_year, cur_month, 1) if (cur_year, cur_month) != (start.year, start.month) else start
        last_day = _last_day_of_month(cur_year, cur_month)
        natural_end = date(cur_year, cur_month, last_day)
        period_end = min(natural_end, end)
        yield (period_start, period_end)
        if natural_end >= end:
            break
        # advance one month
        if cur_month == 12:
            cur_year += 1
            cur_month = 1
        else:
            cur_month += 1


def _count_months_in_tenor(effective: date, termination: date) -> int:
    """Number of calendar months touched by [effective, termination], inclusive."""
    if termination < effective:
        return 0
    return (termination.year - effective.year) * 12 + (termination.month - effective.month) + 1


# ──────────────────────────────────────────────────────────────────────
# Index price computation
# ──────────────────────────────────────────────────────────────────────


def _compute_index_price(
    contract: IndexLinkedContract,
    period_start: date,
    period_end: date,
    history: Sequence[IndexHistory],
) -> Tuple[Optional[Decimal], bool, Optional[str]]:
    """Return (price, is_estimate, note).

    Strategy for B1 (fixing_rule='month_avg' is the only honored rule):
        1. Average all observations strictly within the period.
        2. If none, fall back to the LATEST observation prior to or within
           the period (forward-extrapolation), is_estimate=True.
        3. If history is empty entirely, return (None, True, "no history").
    Apply spread + floor/cap collar.
    """
    in_period = [h for h in history if period_start <= h.observation_date <= period_end]
    note: Optional[str] = None
    is_estimate = False

    if in_period:
        avg = sum((h.value for h in in_period), Decimal("0")) / Decimal(len(in_period))
    else:
        # Fall back: latest observation at or before period_end.
        prior = [h for h in history if h.observation_date <= period_end]
        if not prior:
            return (None, True, "no_history")
        latest = max(prior, key=lambda h: h.observation_date)
        avg = latest.value
        is_estimate = True
        note = f"extrapolated_from_{latest.observation_date.isoformat()}"

    raw = avg + contract.spread
    if contract.floor is not None and raw < contract.floor:
        raw = contract.floor
        note = (note + ";" if note else "") + "floored"
    if contract.cap is not None and raw > contract.cap:
        raw = contract.cap
        note = (note + ";" if note else "") + "capped"
    return (raw, is_estimate, note)


# ──────────────────────────────────────────────────────────────────────
# Per-contract row generation
# ──────────────────────────────────────────────────────────────────────


def _generate_rows_for_contract(
    contract: Contract,
    link: ProjectFinanceLink,
    history: Sequence[IndexHistory],
    from_date: date,
    to_date: date,
) -> Iterator[CashflowRow]:
    """Yield CashflowRow per period for one (Contract, Link) pair, clamped
    to [from_date, to_date] intersected with the contract tenor.
    """
    eff_start = max(contract.effective_date, from_date)
    eff_end = min(contract.termination_date, to_date)
    if eff_start > eff_end:
        return

    total_months = _count_months_in_tenor(contract.effective_date, contract.termination_date)
    if total_months == 0:
        return
    qty_per_month = contract.notional_quantity / Decimal(total_months)

    sign = sign_for_line_item(link.line_item_type)
    allocation = link.allocation_share

    for period_start, period_end in _month_iter(eff_start, eff_end):
        price: Optional[Decimal]
        is_estimate = False
        note: Optional[str] = None

        if isinstance(contract, IndexLinkedContract):
            price, is_estimate, note = _compute_index_price(
                contract, period_start, period_end, history
            )
        elif isinstance(contract, FixedPriceContract):
            price = contract.fixed_price
            # B1: price_basis other than 'flat' is accepted but treated as flat.
            if contract.price_basis != "flat":
                note = f"price_basis={contract.price_basis}_treated_as_flat"
        else:
            # Subtype unknown — skip.
            continue

        if price is None:
            gross = None
            allocated = None
        else:
            gross = qty_per_month * price
            allocated = gross * Decimal(sign) * allocation

        yield CashflowRow(
            period_start=period_start,
            period_end=period_end,
            line_item_type=link.line_item_type,
            contract_id=contract.id,
            contract_number=contract.contract_number,
            currency=contract.currency,
            quantity=qty_per_month,
            quantity_unit=contract.quantity_unit,
            price=price,
            gross_amount=gross,
            sign=sign,
            allocation_share=allocation,
            allocated_amount=allocated,
            is_estimate=is_estimate,
            notes=note,
        )


# ──────────────────────────────────────────────────────────────────────
# Project-level aggregation
# ──────────────────────────────────────────────────────────────────────


def generate_cashflows_for_project(
    asset: Asset,
    links_with_contracts: Iterable[Tuple[ProjectFinanceLink, Contract, Sequence[IndexHistory]]],
    from_date: date,
    to_date: date,
    granularity: str = "monthly",
) -> CashflowProjection:
    """Aggregate per-contract cashflows for one project asset.

    Args:
        asset: the project Asset.
        links_with_contracts: iterable of (link, contract, history) triples.
            History is the IndexHistory for this contract's index (empty list
            for FixedPriceContract). Caller is responsible for fetching.
        from_date / to_date: window to project over.
        granularity: 'monthly' is the only supported value in B1.

    Returns:
        CashflowProjection with rows + per-line-item and per-period summaries.
    """
    if granularity != "monthly":
        raise ValueError(f"B1 supports granularity='monthly' only; got {granularity!r}")

    rows: list[CashflowRow] = []
    for link, contract, history in links_with_contracts:
        for row in _generate_rows_for_contract(contract, link, history, from_date, to_date):
            rows.append(row)

    rows.sort(key=lambda r: (r.period_start, r.contract_number))

    # Summary by line item (allocated amounts, signed)
    summary_by_li: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        if r.allocated_amount is not None:
            summary_by_li[r.line_item_type.value] += r.allocated_amount

    # Summary by period
    period_buckets: dict[Tuple[date, date], dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for r in rows:
        if r.allocated_amount is not None:
            period_buckets[(r.period_start, r.period_end)][r.line_item_type.value] += r.allocated_amount

    summary_by_period = [
        PeriodSummary(
            period_start=p_start,
            period_end=p_end,
            by_line_item=dict(by_li),
            net=sum(by_li.values(), Decimal("0")),
        )
        for (p_start, p_end), by_li in sorted(period_buckets.items())
    ]

    estimate_count = sum(1 for r in rows if r.is_estimate)

    return CashflowProjection(
        project_asset_id=asset.id,
        project_name=asset.name,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
        rows=rows,
        summary_by_line_item={k: v for k, v in summary_by_li.items()},
        summary_by_period=summary_by_period,
        has_estimates=estimate_count > 0,
        estimate_period_count=estimate_count,
    )


__all__ = [
    "CashflowRow",
    "PeriodSummary",
    "CashflowProjection",
    "generate_cashflows_for_project",
    "sign_for_line_item",
]
