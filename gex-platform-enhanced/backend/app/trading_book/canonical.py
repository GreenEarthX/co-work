"""
Canonical terms JSON and its hash — spec §6.

terms → legs (by seq) → flows (by seq); sorted keys, no whitespace, decimals as
strings at a fixed scale, ISO dates, lowercase UUIDs; no database ids or
timestamps; counterparties as "cp:<id>". The same terms always give the same
bytes, so terms_hash = sha256 identifies the economic content of a contract
version — what its token will refer to (D7).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from app.trading_book.terms import FlowIn, TermsIn

SCALE = {"quantity": 6, "tolerance_min_pct": 4, "tolerance_max_pct": 4, "unit_price": 8,
         "index_multiplier": 8, "spread": 8, "cap": 8, "floor": 8}
FLOW_FIELDS = ("seq", "flow_type", "period_start", "period_end", "settle_date", "quantity", "unit",
               "is_notional", "quantity_basis", "quantity_source_flow", "tolerance_min_pct",
               "tolerance_max_pct", "asset_id", "currency", "unit_price", "index", "index_multiplier",
               "spread", "cap", "floor", "fixing_method", "fixing_start", "fixing_end")
# Present on every flow with a default; written only where the flow type uses them.
CASH_ONLY = {"index_multiplier": "float_cash", "spread": ("fixed_cash", "float_cash")}


def _value(key: str, v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v.quantize(Decimal(1).scaleb(-SCALE.get(key, 8))), "f")
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "value"):                       # StrEnum
        return v.value
    return v


def _flow(flow: FlowIn) -> dict:
    out = {}
    for key in FLOW_FIELDS:
        v = getattr(flow, key)
        if v is None:
            continue
        if key in CASH_ONLY and flow.flow_type.value not in CASH_ONLY[key]:
            continue
        if key == "is_notional" and v is False and flow.flow_type.value == "physical":
            continue
        if key in ("asset_id", "index"):
            v = str(v).lower()
        out[key] = _value(key, v)
    return out


def canonical_dict(terms: TermsIn) -> dict:
    legs = []
    for leg in sorted(terms.legs, key=lambda l: l.seq):
        item = {"seq": leg.seq, "leg_role": leg.leg_role.value,
                "flows": [_flow(f) for f in sorted(leg.flows, key=lambda f: f.seq)]}
        if leg.payer:
            item["payer"] = f"cp:{str(leg.payer).lower()}"
        if leg.receiver:
            item["receiver"] = f"cp:{str(leg.receiver).lower()}"
        legs.append(item)
    return {"settlement": terms.settlement.value, "commodity": terms.commodity,
            "quality_spec": terms.quality_spec, "currency": terms.currency.upper(), "legs": legs}


def canonical_bytes(terms: TermsIn) -> bytes:
    return json.dumps(canonical_dict(terms), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def terms_hash(terms: TermsIn) -> str:
    return hashlib.sha256(canonical_bytes(terms)).hexdigest()
