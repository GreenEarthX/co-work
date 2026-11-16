"""
Carving a market token to the quantity actually listed or agreed (discovery review F13, alembic 114).

A token is a rate (MTPD) over a delivery window. A listing may offer less than the token, and a
match may agree less than the listing (min of the two volumes, over the overlap of the two
windows). Before 114 the whole token moved at both points: a buyer of 40 MTPD for two years
received title to 50 MTPD for three.

`carve` splits the token so that ONE child equals the kept piece exactly and the rest becomes
remainder children, available again (MINTED). The pieces partition the parent's tonnes
(rate x days) exactly; custody kg, where the parent has any, is apportioned by tonnes and the
last piece takes the rounding so the sum is exact. The parent becomes SPLIT (frozen by
tokens_split_guard) and every child is recorded in `token_split` with the order that decided it.

Pieces, for parent (R, P0..P1) and kept (r, K0..K1) with K inside P and r <= R:
    kept               r      K0..K1        parent's state (the caller then moves it)
    rate remainder     R - r  P0..P1        MINTED   (if R > r)
    before the window  r      P0..K0-1      MINTED   (if K0 > P0)
    after the window   r      K1+1..P1      MINTED   (if K1 < P1)

Runs on the caller's operator connection, inside the caller's transaction: nothing commits here.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Optional

EPS = Decimal("0.000001")
CARVABLE = ("MINTED", "RESERVED")
# Copied from the parent unchanged (delivery_title.COPIED minus what a market piece redefines).
COPIED = ("capacity_id", "compliance_certifications", "correlation_id", "sovereign_provenance", "molecule",
          "production_window_start", "production_window_end", "certification_pathway",
          "carbon_intensity_gco2e_mj", "mass_balance_lot_id", "provenance_hash", "verification_state", "production_pathway", "physical_form", "specification_standard")


class CarveRefused(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


def _day(v) -> date:
    return date.fromisoformat(str(v)[:10])


def _row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def carve(conn, token_id: str, rate, start, end, *, reason: str, order_id: str, holder_company_id: str,
          trail=None) -> str:
    """Return the id of the token holding exactly (rate, start..end): the token itself when it
    already is that, otherwise a new child. Refuses a piece outside the token."""
    if reason not in ("market_listing", "market_acceptance"):
        raise ValueError(reason)
    t = _row(conn, "SELECT * FROM tokens WHERE id = ? FOR UPDATE", (token_id,))
    if t is None:
        raise CarveRefused(404, "TOKEN_NOT_FOUND", f"Token {token_id} does not exist.")
    if (t["lifecycle_state"] or "MINTED") not in CARVABLE:
        raise CarveRefused(409, "TOKEN_STATE", f"The token is {t['lifecycle_state']}; only an available or "
                                               "reserved token can be divided.")
    p0, p1, k0, k1 = _day(t["delivery_start"]), _day(t["delivery_end"]), _day(start), _day(end)
    prate, krate = Decimal(str(t["tokenised_mtpd"] or 0)), Decimal(str(rate))
    if k1 < k0 or k0 < p0 or k1 > p1:
        raise CarveRefused(409, "OUTSIDE_TOKEN_WINDOW",
                           f"{k0}..{k1} is not inside the token's delivery window {p0}..{p1}.")
    if krate <= 0 or krate > prate + EPS:
        raise CarveRefused(409, "OVER_TOKEN_RATE", f"{krate} MTPD is more than the token's {prate} MTPD.")
    if abs(prate - krate) <= EPS and (k0, k1) == (p0, p1):
        return token_id                                         # already exactly the piece

    one = timedelta(days=1)
    pieces = [("K", krate, k0, k1, t["lifecycle_state"] or "MINTED")]
    if prate - krate > EPS:
        pieces.append(("R", prate - krate, p0, p1, "MINTED"))
    if k0 > p0:
        pieces.append(("B", krate, p0, k0 - one, "MINTED"))
    if k1 < p1:
        pieces.append(("A", krate, k1 + one, p1, "MINTED"))

    tonnes = [r * ((b - a).days + 1) for _, r, a, b, _ in pieces]
    total_t = prate * ((p1 - p0).days + 1)
    assert abs(sum(tonnes) - total_t) <= EPS * 10, "pieces must partition the token's tonnes"
    kg_total = Decimal(str(_row(conn, "SELECT app_token_kg(?) AS kg", (token_id,))["kg"] or 0))
    kgs = [(kg_total * tn / total_t).quantize(EPS, rounding=ROUND_DOWN) if total_t else Decimal(0) for tn in tonnes]
    kgs[-1] = kg_total - sum(kgs[:-1])                           # exact sum

    stem = token_id.split("-M")[0][:60]
    now = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(COPIED)
    keep_id = None
    for (tag, r, a, b, state), tn, kg in zip(pieces, tonnes, kgs):
        child = f"{stem}-M{tag}{uuid.uuid4().hex[:8]}"
        energy = None if t["energy_mj"] is None else float(Decimal(str(t["energy_mj"])) * tn / total_t)
        conn.execute(f"INSERT INTO tokens (id, parent_token_id, holder_company_id, energy_mj, tokenised_mtpd, "
                     f"delivery_start, delivery_end, lifecycle_state, created_at, {cols}) "
                     f"SELECT ?, id, holder_company_id, ?, ?, ?, ?, ?, ?, {cols} FROM tokens WHERE id = ?",
                     (child, energy, float(r), a.isoformat(), b.isoformat(), state, now, token_id))
        facts = {"parent": token_id, "child": child, "reason": reason, "order_id": str(order_id),
                 "tokenised_mtpd": str(r), "delivery_start": a.isoformat(), "delivery_end": b.isoformat(),
                 "kg": str(kg)}
        conn.execute("INSERT INTO token_split (delivery_id, parent_token_id, child_token_id, kg, holder_company_id, "
                     "event_hash, reason, order_id, capacity_id, tokenised_mtpd, delivery_start, delivery_end) "
                     "VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (token_id, child, kg, t["holder_company_id"] or holder_company_id,
                      hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest(), reason, str(order_id),
                      t["capacity_id"], float(r), a.isoformat(), b.isoformat()))
        if tag == "K":
            keep_id = child
    conn.execute("UPDATE tokens SET lifecycle_state = 'SPLIT' WHERE id = ?", (token_id,))
    if trail is not None:
        trail.add("token.split", "token", token_id,
                  {"reason": reason, "order_id": str(order_id), "kept": keep_id,
                   "pieces": [{"tokenised_mtpd": str(r), "from": a.isoformat(), "to": b.isoformat(), "state": s}
                              for _, r, a, b, s in pieces]},
                  t["correlation_id"], None)
    return keep_id
