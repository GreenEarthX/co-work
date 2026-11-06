"""
Canonical terms JSON and its hash — spec §6.

terms → legs (by seq) → flows (by seq); sorted keys, no whitespace, decimals as
strings at a fixed scale, ISO dates, lowercase UUIDs; no database ids or
timestamps; counterparties as "cp:<id>". The same terms always give the same
bytes, so the hashes identify the economic content of a contract version.

Since alembic 083 there are three hashes (Phase 0 Q1/Q2/Q12):

  shared_hash   the shared terms: settlement, commodity, quality, currency and
                the clauses that belong to no sub-leg
  sub-leg hash  one per sub-leg (one per buyer): its legs, flows and clauses
  terms_hash    the Merkle root over [shared_hash, sub-leg hashes by seq]

A buyer confirms its own sub-leg's hash and the shared hash, so changing one
buyer's part leaves the others' confirmations standing; the root is what the
version records and what a ledger anchor carries. canonical_dict is the whole
terms in one document (the terms.json a party reads); it is not what is hashed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from app.trading_book.terms import ClauseIn, FlowIn, LegIn, TermsIn

SCALE = {"quantity": 6, "tolerance_min_pct": 4, "tolerance_max_pct": 4, "unit_price": 8,
         "index_multiplier": 8, "spread": 8, "cap": 8, "floor": 8}
FLOW_FIELDS = ("seq", "flow_type", "period_start", "period_end", "settle_date", "quantity", "unit",
               "is_notional", "quantity_basis", "quantity_source_flow", "tolerance_min_pct",
               "tolerance_max_pct", "asset_id", "unit_price", "index", "index_multiplier",
               "spread", "cap", "floor", "fixing_method", "fixing_start", "fixing_end")
# A flow's own `currency` is not hashed: V09 makes it equal the terms' currency,
# which is hashed, and tb_flow does not store it — so stored terms re-hash exactly.
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


def _leg(leg: LegIn) -> dict:
    item = {"seq": leg.seq, "leg_role": leg.leg_role.value,
            "flows": [_flow(f) for f in sorted(leg.flows, key=lambda f: f.seq)]}
    if leg.payer:
        item["payer"] = f"cp:{str(leg.payer).lower()}"
    if leg.receiver:
        item["receiver"] = f"cp:{str(leg.receiver).lower()}"
    return item


def _clause(clause: ClauseIn) -> dict:
    item = {"seq": clause.seq, "clause_type": clause.clause_type, "attrs": clause.attrs}
    if clause.sub_leg is not None:
        item["sub_leg"] = clause.sub_leg
    return item


def _clauses(terms: TermsIn, sub_leg) -> list[dict]:
    return [_clause(c) for c in sorted(terms.clauses, key=lambda c: c.seq) if c.sub_leg == sub_leg]


def _rank(terms: TermsIn, n: int):
    return next((s.rank for s in terms.sub_legs if s.seq == n), None)


def canonical_dict(terms: TermsIn) -> dict:
    """The whole terms in one canonical document. A bilateral trade with no
    clauses has exactly the spec §6 shape; sub-legs and clauses appear only when
    the terms have them."""
    multi = len(terms.sub_leg_numbers()) > 1
    legs = []
    for leg in sorted(terms.legs, key=lambda l: l.seq):
        item = _leg(leg)
        if multi:
            item["sub_leg"] = leg.sub_leg
        legs.append(item)
    out = {"settlement": _enum(terms.settlement), "commodity": terms.commodity,
           "quality_spec": terms.quality_spec, "currency": _upper(terms.currency), "legs": legs}
    out.update(_card(terms))
    if terms.clauses:
        out["clauses"] = [_clause(c) for c in sorted(terms.clauses, key=lambda c: c.seq)]
    if any(s.rank is not None for s in terms.sub_legs):
        out["sub_legs"] = [{"seq": s.seq, "rank": s.rank} for s in sorted(terms.sub_legs, key=lambda s: s.seq)]
    return out


def _enum(v):
    return v.value if v is not None else None


def _upper(v):
    return v.upper() if v is not None else None


def _card(terms: TermsIn) -> dict:
    """Card terms (alembic 085) hash their profile and projection; complete terms
    are hashed exactly as before — neither key appears."""
    if terms.profile == "complete" and terms.card_projection is None:
        return {}
    return {"profile": terms.profile, "card_projection": terms.card_projection}


def shared_dict(terms: TermsIn) -> dict:
    return {"settlement": _enum(terms.settlement), "commodity": terms.commodity,
            "quality_spec": terms.quality_spec, "currency": _upper(terms.currency),
            "clauses": _clauses(terms, None), **_card(terms)}


def sub_leg_dict(terms: TermsIn, n: int) -> dict:
    return {"seq": n, "rank": _rank(terms, n),
            "legs": [_leg(l) for l in sorted(terms.legs, key=lambda l: l.seq) if l.sub_leg == n],
            "clauses": _clauses(terms, n)}


def _bytes(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str).encode("utf-8")


def canonical_bytes(terms: TermsIn) -> bytes:
    return _bytes(canonical_dict(terms))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    """sha256 over hex leaves, pairwise; an odd node is paired with itself."""
    if not leaves:
        raise ValueError("a Merkle root needs at least one leaf")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [_sha(bytes.fromhex(a) + bytes.fromhex(b)) for a, b in zip(level[::2], level[1::2])]
    return level[0]


def merkle_proof(leaves: list[str], index: int) -> list[tuple[str, str]]:
    """[(sibling hash, 'L' | 'R')] from leaf `index` up to the root — what lets a
    buyer show its sub-leg is inside an anchored root without seeing the others."""
    proof, level, i = [], list(leaves), index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = i ^ 1
        proof.append((level[sibling], "L" if sibling < i else "R"))
        level = [_sha(bytes.fromhex(a) + bytes.fromhex(b)) for a, b in zip(level[::2], level[1::2])]
        i //= 2
    return proof


def verify_proof(leaf: str, proof: list[tuple[str, str]], root: str) -> bool:
    node = leaf
    for sibling, side in proof:
        node = _sha(bytes.fromhex(sibling) + bytes.fromhex(node)) if side == "L" \
            else _sha(bytes.fromhex(node) + bytes.fromhex(sibling))
    return node == root


def hashes(terms: TermsIn) -> dict:
    """{"shared_hash", "sub_legs": {seq: hash}, "terms_hash": the Merkle root}."""
    shared = _sha(_bytes(shared_dict(terms)))
    subs = {n: _sha(_bytes(sub_leg_dict(terms, n))) for n in terms.sub_leg_numbers()}
    return {"shared_hash": shared, "sub_legs": subs,
            "terms_hash": merkle_root([shared] + [subs[n] for n in sorted(subs)])}


def terms_hash(terms: TermsIn) -> str:
    return hashes(terms)["terms_hash"]
