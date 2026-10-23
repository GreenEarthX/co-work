"""
Terms validation — spec §4, rules V01–V13. Applied on create and on freeze.

validate() returns the list of failed rule codes (empty = valid); the API answers
422 with that list. Pure: the caller supplies what lives in the database (the
index definitions, the restricted pairs) so every rule is unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.trading_book.conventions import LEG_ROLES, FlowType, LegRole, Settlement
from app.trading_book.terms import FlowIn, TermsIn

Kind = Literal["order", "contract"]
CASH_FLOWS = {FlowType.FIXED_CASH, FlowType.FLOAT_CASH}


@dataclass(frozen=True)
class IndexInfo:
    currency: str
    unit: str
    convertible: bool = False        # conversion is out of scope: a convertible index is still refused


@dataclass
class Context:
    indices: dict[str, IndexInfo] = field(default_factory=dict)
    restricted_pairs: set[frozenset] = field(default_factory=set)   # {frozenset({cp_a, cp_b})}
    allow_cash_settled: bool = False  # TRADING_ALLOW_CASH_SETTLED (default off, D5)


def _flows(terms: TermsIn):
    for leg in terms.legs:
        for flow in leg.flows:
            yield leg, flow


def validate(terms: TermsIn, kind: Kind, ctx: Context | None = None) -> list[str]:
    ctx = ctx or Context()
    failed: list[str] = []

    def fail(code: str) -> None:
        if code not in failed:
            failed.append(code)

    cash = terms.settlement != Settlement.PHYSICAL
    roles = [leg.leg_role for leg in terms.legs]
    by_role = {leg.leg_role: leg for leg in terms.legs}

    # V01 exactly two legs
    if len(terms.legs) != 2:
        fail("V01")
    # V02 the two roles the settlement calls for
    if sorted(roles) != sorted(LEG_ROLES[terms.settlement]):
        fail("V02")
    # V03 physical: product leg only physical flows; payment leg only cash flows
    if not cash:
        for leg, flow in _flows(terms):
            if leg.leg_role == LegRole.PRODUCT and flow.flow_type != FlowType.PHYSICAL:
                fail("V03")
            if leg.leg_role == LegRole.PAYMENT and flow.flow_type not in CASH_FLOWS:
                fail("V03")
    # V04 cash: no physical flows, all notional; fixed leg fixed, floating leg float
    if cash:
        for leg, flow in _flows(terms):
            if flow.flow_type == FlowType.PHYSICAL or not flow.is_notional:
                fail("V04")
            if leg.leg_role == LegRole.FIXED and flow.flow_type != FlowType.FIXED_CASH:
                fail("V04")
            if leg.leg_role == LegRole.FLOATING and flow.flow_type != FlowType.FLOAT_CASH:
                fail("V04")
    # V05 cash settlement is behind a flag
    if cash and not ctx.allow_cash_settled:
        fail("V05")
    # V06 parties: every leg in a contract, none in an order
    for leg in terms.legs:
        named = leg.payer is not None or leg.receiver is not None
        if kind == "contract" and (leg.payer is None or leg.receiver is None):
            fail("V06")
        if kind == "order" and named:
            fail("V06")
    # V07 / V08 the two legs run in opposite directions
    if kind == "contract":
        pair = (LegRole.PRODUCT, LegRole.PAYMENT) if not cash else (LegRole.FIXED, LegRole.FLOATING)
        a, b = by_role.get(pair[0]), by_role.get(pair[1])
        if a and b and not (a.payer == b.receiver and a.receiver == b.payer):
            fail("V08" if cash else "V07")
    # V09 one currency for all cash flows
    for _, flow in _flows(terms):
        if flow.flow_type in CASH_FLOWS and flow.currency and flow.currency.upper() != terms.currency.upper():
            fail("V09")
    # V10 a delivered-basis payment names the product flow it pays for, in these terms
    physical_refs = {f"{leg.seq}.{flow.seq}" for leg, flow in _flows(terms)
                     if flow.flow_type == FlowType.PHYSICAL}
    for _, flow in _flows(terms):
        if flow.flow_type in CASH_FLOWS and flow.quantity_basis == "delivered":
            if flow.quantity_source_flow not in physical_refs:
                fail("V10")
    # V11 float flows: a known index in the terms' currency and the flow's unit
    for _, flow in _flows(terms):
        if flow.flow_type == FlowType.FLOAT_CASH:
            info = ctx.indices.get(flow.index or "")
            if (info is None or info.convertible or info.currency.upper() != terms.currency.upper()
                    or info.unit != flow.unit):
                fail("V11")
    # V12 non-empty, ordered periods
    for _, flow in _flows(terms):
        if not _dates_ordered(flow):
            fail("V12")
    if any(not leg.flows for leg in terms.legs):
        fail("V12")
    # V13 restricted counterparties never share a contract
    if kind == "contract":
        parties = {p for leg in terms.legs for p in (leg.payer, leg.receiver) if p}
        for pair in ctx.restricted_pairs:
            if pair <= parties:
                fail("V13")
    return failed


def _dates_ordered(flow: FlowIn) -> bool:
    if flow.period_start > flow.period_end:
        return False
    if flow.flow_type == FlowType.FLOAT_CASH and flow.fixing_start and flow.fixing_end:
        return flow.fixing_start <= flow.fixing_end
    return True
