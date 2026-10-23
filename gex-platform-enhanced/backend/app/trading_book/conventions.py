"""
The side convention — the ONLY place trade direction is defined (spec §2).

An order is one-sided: an owner and a side, no counterparty (D3). At acceptance
the payer and receiver of every leg are resolved from this table and nowhere
else. Every other module imports it; none restates it.
"""
from __future__ import annotations

from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Settlement(StrEnum):
    PHYSICAL = "physical"
    CASH_NET = "cash_net"
    CASH_GROSS = "cash_gross"


class LegRole(StrEnum):
    PRODUCT = "product"
    PAYMENT = "payment"
    FIXED = "fixed"
    FLOATING = "floating"


class FlowType(StrEnum):
    PHYSICAL = "physical"
    FIXED_CASH = "fixed_cash"
    FLOAT_CASH = "float_cash"


# The leg roles each settlement has (V02).
LEG_ROLES: dict[Settlement, tuple[LegRole, LegRole]] = {
    Settlement.PHYSICAL: (LegRole.PRODUCT, LegRole.PAYMENT),
    Settlement.CASH_NET: (LegRole.FIXED, LegRole.FLOATING),
    Settlement.CASH_GROSS: (LegRole.FIXED, LegRole.FLOATING),
}

# Who PAYS on each leg. The other side receives.
#   physical / product   the seller delivers   (buyer receives the commodity)
#   physical / payment   the buyer pays        (seller receives the money)
#   cash / fixed         the buyer pays fixed
#   cash / floating      the seller pays floating
PAYER_SIDE: dict[LegRole, Side] = {
    LegRole.PRODUCT: Side.SELL,
    LegRole.PAYMENT: Side.BUY,
    LegRole.FIXED: Side.BUY,
    LegRole.FLOATING: Side.SELL,
}


def opposite(side: Side) -> Side:
    return Side.SELL if side == Side.BUY else Side.BUY


def resolve(leg_role: LegRole, buyer: str, seller: str) -> tuple[str, str]:
    """(payer, receiver) of a leg, given who is buying and who is selling."""
    payer_side = PAYER_SIDE[LegRole(leg_role)]
    return (buyer, seller) if payer_side == Side.BUY else (seller, buyer)


def parties_at_acceptance(order_side: Side, order_owner: str, acceptor: str) -> tuple[str, str]:
    """(buyer, seller) when `acceptor` takes an order owned by `order_owner`."""
    return (order_owner, acceptor) if Side(order_side) == Side.BUY else (acceptor, order_owner)


def direction(party: str, payer: str, receiver: str) -> int:
    """+1 for the receiver, -1 for the payer, 0 for anyone else (the derived book's sign)."""
    return 1 if party == receiver else -1 if party == payer else 0
