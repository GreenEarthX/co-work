"""
Terms validation — spec §4, rules V01–V13, and V14 (alembic 083). Applied on
create and on freeze.

Since 083 terms have one or more sub-legs (one per buyer). V01, V02, V07 and V08
apply to EACH sub-leg — "exactly two legs" became "exactly two legs per
sub-leg" (Phase 0 Q1) — so a bilateral trade, one sub-leg, is checked exactly as
before. V14 is the structure: leg seqs unique across the terms, clause types
known, every clause and rank naming a sub-leg that exists.

validate() returns the list of failed rule codes (empty = valid); the API answers
422 with that list. Pure: the caller supplies what lives in the database (the
index definitions, the restricted pairs) so every rule is unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.trading_book.conventions import LEG_ROLES, FlowType, LegRole, Settlement
from app.trading_book.terms import CLAUSE_TYPES, FlowIn, TermsIn

Kind = Literal["order", "contract", "rfq"]
# "rfq": an RFQ's indicative terms (Phase 3, alembic 087) — a product leg, and a payment
# leg only when the buyer names a price; no parties, like an order (V06).
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


def _is_projection(proj) -> bool:
    return isinstance(proj, dict) and all(isinstance(k, str) and k.count(".") == 1 for k in proj)


def validate_card(terms: TermsIn) -> list[str]:
    """`card` terms (alembic 085): a projection of commitment-card fields and no
    legs. C01: a projection is present and every key is "card.field". C02: no
    legs or flows. C03 (a frame, Phase 3 Q2): every sub-leg names its buyer and
    carries a projection of its own, and no buyer appears twice."""
    failed = []
    if not _is_projection(terms.card_projection):
        failed.append("C01")
    if terms.legs:
        failed.append("C02")
    if terms.sub_legs:
        buyers = [s.buyer for s in terms.sub_legs]
        if (any(not b or not _is_projection(s.card_projection) for b, s in zip(buyers, terms.sub_legs))
                or len(set(buyers)) != len(buyers)):
            failed.append("C03")
    return failed


def validate(terms: TermsIn, kind: Kind, ctx: Context | None = None) -> list[str]:
    ctx = ctx or Context()
    failed: list[str] = []

    def fail(code: str) -> None:
        if code not in failed:
            failed.append(code)

    if terms.profile == "card":
        return validate_card(terms)
    if terms.settlement is None or terms.commodity is None or terms.currency is None:
        return ["V02"]          # complete terms name their settlement, commodity and currency

    cash = terms.settlement != Settlement.PHYSICAL
    sub_legs = {n: [leg for leg in terms.legs if leg.sub_leg == n] for n in terms.sub_leg_numbers()}

    # V01 exactly two legs per sub-leg (and at least one sub-leg); an RFQ may name no price
    allowed = (1, 2) if kind == "rfq" else (2,)
    if not sub_legs or any(len(legs) not in allowed for legs in sub_legs.values()):
        fail("V01")
    # V02 the two roles the settlement calls for, in each sub-leg (an RFQ: the first at least)
    for legs in sub_legs.values():
        roles = sorted(leg.leg_role for leg in legs)
        expected = sorted(LEG_ROLES[terms.settlement])
        if kind == "rfq" and len(roles) == 1:
            ok = roles == [LEG_ROLES[terms.settlement][0]]
        else:
            ok = roles == expected
        if not ok:
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
        if kind in ("order", "rfq") and named:
            fail("V06")
    # V07 / V08 the two legs of each sub-leg run in opposite directions
    if kind == "contract":
        pair = (LegRole.PRODUCT, LegRole.PAYMENT) if not cash else (LegRole.FIXED, LegRole.FLOATING)
        for legs in sub_legs.values():
            by_role = {leg.leg_role: leg for leg in legs}
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
    # V14 structure: unique leg seqs, known clauses, references to existing sub-legs
    if len({leg.seq for leg in terms.legs}) != len(terms.legs):
        fail("V14")
    if len({c.seq for c in terms.clauses}) != len(terms.clauses):
        fail("V14")
    for clause in terms.clauses:
        if clause.clause_type not in CLAUSE_TYPES or (clause.sub_leg is not None and clause.sub_leg not in sub_legs):
            fail("V14")
    if any(s.seq not in sub_legs for s in terms.sub_legs) or len({s.seq for s in terms.sub_legs}) != len(terms.sub_legs):
        fail("V14")
    return failed


def _dates_ordered(flow: FlowIn) -> bool:
    if flow.period_start > flow.period_end:
        return False
    if flow.flow_type == FlowType.FLOAT_CASH and flow.fixing_start and flow.fixing_end:
        return flow.fixing_start <= flow.fixing_end
    return True
