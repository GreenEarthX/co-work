"""
The terms payload — one schema for orders, RFQ quotes and contracts (D4).

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


class LegIn(BaseModel):
    seq: int = Field(ge=1)
    leg_role: LegRole
    payer: Optional[str] = None                     # counterparty id; None in order terms (V06)
    receiver: Optional[str] = None
    flows: list[FlowIn] = Field(default_factory=list)


class TermsIn(BaseModel):
    settlement: Settlement
    commodity: str                                  # tb_commodity.code, e.g. EMEOH
    quality_spec: dict[str, Any] = Field(default_factory=dict)
    currency: str = Field(min_length=3, max_length=3)
    legs: list[LegIn] = Field(default_factory=list)
