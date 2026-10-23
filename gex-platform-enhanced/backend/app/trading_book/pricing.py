"""
Flow amounts — spec §7, the arithmetic only. Decimal throughout (D8).

  fixed_cash   q × (unit_price + spread)
  float_cash   q × clamp(multiplier × fixing + spread, floor, cap)

q is the contracted quantity, or for quantity_basis = delivered the delivered
quantity of the product flow it pays for — the contracted quantity, flagged
projected, until that delivery exists. The cashflow engine (M4) dispatches on
flow_type and calls these.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

CENT = Decimal("0.01")


def money(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def fixed_amount(quantity: Decimal, unit_price: Decimal, spread: Decimal = Decimal(0)) -> Decimal:
    return money(quantity * (unit_price + spread))


def clamp(price: Decimal, floor: Optional[Decimal], cap: Optional[Decimal]) -> Decimal:
    if floor is not None and price < floor:
        return floor
    if cap is not None and price > cap:
        return cap
    return price


def float_amount(quantity: Decimal, fixing: Decimal, multiplier: Decimal = Decimal(1),
                 spread: Decimal = Decimal(0), floor: Optional[Decimal] = None,
                 cap: Optional[Decimal] = None) -> Decimal:
    return money(quantity * clamp(multiplier * fixing + spread, floor, cap))


def fixing(values: Iterable[Decimal], method: str) -> Decimal:
    """average / first / last of the index values inside the fixing window (in date order)."""
    vals = list(values)
    if not vals:
        raise ValueError("no index value inside the fixing window")
    if method == "first":
        return vals[0]
    if method == "last":
        return vals[-1]
    if method == "average":
        return sum(vals, Decimal(0)) / len(vals)
    raise ValueError(f"unknown fixing method {method!r}")


def payment_quantity(contracted: Decimal, basis: Optional[str],
                     delivered: Optional[Decimal]) -> tuple[Decimal, bool]:
    """(quantity to price, projected?)."""
    if basis == "delivered":
        return (delivered, False) if delivered is not None else (contracted, True)
    return contracted, False
