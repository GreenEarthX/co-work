"""
The terms payload — one schema for orders, RFQ quotes and contracts (D4).

A terms object is shared terms (settlement, commodity, quality, currency, shared
clauses) plus one or more SUB-LEGS, one per buyer (alembic 083; Phase 0 Q1/Q2).
Each leg names its sub-leg; a bilateral trade is one sub-leg, the default.
Clauses carry the terms that have no cashflow (delivery and payment terms,
take-or-pay, CPs, damages, …), shared or for one sub-leg.

Deliberately loose: the rule checks live in validation.py and answer with rule
codes (V01–V13), so the model accepts anything structurally parseable and the
rules say what is wrong with it. Money and quantities are Decimal (D8).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.trading_book.conventions import FlowType, LegRole, Settlement


class FlowIn(BaseModel):
    seq: int = Field(ge=1)
    flow_type: FlowType
    period_start: date
    period_end: date
    settle_date: date
    quantity: Decimal = Field(gt=0)
    unit: str
    is_notional: bool = False
    quantity_basis: Optional[str] = None            # "contracted" | "delivered"
    quantity_source_flow: Optional[str] = None      # "<leg seq>.<flow seq>" within the same terms
    tolerance_min_pct: Optional[Decimal] = None
    tolerance_max_pct: Optional[Decimal] = None
    asset_id: Optional[str] = None
    currency: Optional[str] = None                  # cash flows; must equal the terms currency (V09)
    unit_price: Optional[Decimal] = None
    index: Optional[str] = None                     # index id
    index_multiplier: Decimal = Decimal("1")
    spread: Decimal = Decimal("0")
    cap: Optional[Decimal] = None
    floor: Optional[Decimal] = None
    fixing_method: Optional[str] = None             # "average" | "first" | "last"
    fixing_start: Optional[date] = None
    fixing_end: Optional[date] = None


# Mirrors alembic 083's CHECK (tests/test_contract_record.py keeps them equal).
CLAUSE_TYPES = ("delivery", "payment", "parties", "commitment", "conditions_precedent", "damages",
                "force_majeure", "change_in_law", "credit", "performance", "price", "declaration")


class ClauseIn(BaseModel):
    seq: int = Field(ge=1)
    clause_type: str
    sub_leg: Optional[int] = None                   # None: a shared clause
    attrs: dict[str, Any] = Field(default_factory=dict)


class SubLegIn(BaseModel):
    seq: int = Field(ge=1)
    rank: Optional[int] = None                      # tranching (Q2)


class LegIn(BaseModel):
    seq: int = Field(ge=1)
    sub_leg: int = Field(default=1, ge=1)
    leg_role: LegRole
    payer: Optional[str] = None                     # counterparty id; None in order terms (V06)
    receiver: Optional[str] = None
    flows: list[FlowIn] = Field(default_factory=list)


class TermsIn(BaseModel):
    # `card` terms (alembic 085, Phase 0 Q3) are a project's commitment-card fields
    # for one contract kind: card_projection holds the exact {card.field: value}
    # the confirming party confirms and the gate engine reads. They have no
    # settlement, commodity or currency of their own and, in Phase 2, no legs.
    profile: str = "complete"                       # "complete" | "card"
    card_projection: Optional[dict[str, Any]] = None
    settlement: Optional[Settlement] = None         # required for "complete" (V02)
    commodity: Optional[str] = None                 # tb_commodity.code, e.g. EMEOH
    quality_spec: dict[str, Any] = Field(default_factory=dict)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    legs: list[LegIn] = Field(default_factory=list)
    sub_legs: list[SubLegIn] = Field(default_factory=list)   # optional: rank per sub-leg
    clauses: list[ClauseIn] = Field(default_factory=list)

    def sub_leg_numbers(self) -> list[int]:
        return sorted({leg.sub_leg for leg in self.legs})
