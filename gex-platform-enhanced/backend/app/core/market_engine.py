"""
Market engine — every cross-company step of a tokenised trade.
==============================================================
docs/COMMERCIAL_PLATFORM_GAP_REGISTER.md, P0 (2026-10-23). The chain

    capacity -> token -> offer (listing) / RFQ -> match -> contract -> settlement

was modelled but could not run end to end, trades did not move tokens (G-02),
and the trail broke at matching and settlement (G-03).

JML's decisions of 2026-10-23
-----------------------------
* Listings are ANONYMISED: every vetted company sees open offers and open RFQs
  with their commercial terms, never the counterparty, the project or the
  location. Names and full terms reach the two parties once a match exists.
* A match needs BOTH parties to accept. Each acceptance records who and when.

Why one engine, and why it holds the operator connection
--------------------------------------------------------
Base tables stay strictly tenant-scoped (alembic 036/063): a company reads its
own offers, RFQs, tokens. Several steps necessarily span both companies — reading
the counterparty's open listing, creating a match that joins a seller's offer to
a buyer's RFQ, the buyer's acceptance moving the seller's token, settlement
handing the token's title to the buyer. On PostgreSQL those run on ONE
PLATFORM_ADMIN connection (`_conn`), logged by the shim like the other admin
sites. That is safe only because every public function here authorises the
calling Party explicitly before it touches anything; tests pin each refusal.
GEX operates the market and trades nothing: a GEX account may run matching for
everyone but cannot list, request, accept, contract or settle.

Token states driven by the trade (tokens_sqlite.TOKEN_TRANSITIONS)
------------------------------------------------------------------
    listing opened      MINTED   -> RESERVED   (one open listing per token)
    listing withdrawn   RESERVED -> MINTED
    both parties accept RESERVED -> MATCHED
    settlement confirmed MATCHED -> SETTLED, title (holder_company_id) -> buyer
Retirement stays where it was: an evidenced act by the holder
(POST /tokens/{id}/transition), never a side effect.

The trail
---------
Every step writes events carrying the token's correlation_id, so one id runs
from capacity to retirement. The ledger has its own connection, so events are
written after the step commits; a failed write is raised, never swallowed.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("gex.market_engine")

# Part of the matching METHOD, not data (JML, 2026-10-23: kept in code, documented).
# The threshold an automated run would apply; unused while MARKET_AUTO_MATCHING is
# off. The score's weights live with the scoring function,
# matching_sqlite.calculate_match_score (molecule 40, price 30, ...).
MIN_MATCH_SCORE = 60
LIVE_LISTING_STATES = ("OPEN", "RESERVED", "MATCHED")


# ── identity and refusals ───────────────────────────────────────────────────

@dataclass
class Party:
    user_id: str
    company_id: Optional[str]
    company_name: Optional[str] = None
    is_admin: bool = False

    @classmethod
    def from_payload(cls, payload: dict) -> "Party":
        uid = payload.get("user_id") or payload.get("sub")
        if not uid:
            raise MarketRefused(401, "AUTHENTICATION_REQUIRED", "Sign in to use the market.")
        return cls(user_id=str(uid), company_id=payload.get("company_id"),
                   company_name=payload.get("company_name"),
                   is_admin=bool(payload.get("is_platform_admin")))


@dataclass
class MarketRefused(Exception):
    status: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _refuse(status: int, code: str, message: str):
    raise MarketRefused(status, code, message)


def _trader(party: Party) -> None:
    """GEX operates the market; it does not trade on it."""
    if party.is_admin:
        _refuse(403, "GEX_DOES_NOT_TRADE",
                "GEX operates the market and trades nothing: a GEX account cannot list, "
                "request, accept, contract or settle.")
    if not party.company_id:
        _refuse(403, "NO_COMPANY", "Your account belongs to no company, so it cannot trade.")


# ── storage ─────────────────────────────────────────────────────────────────

def _conn():
    """The market operator connection. PostgreSQL only (JML, 2026-10-23): RFQs and
    the rest of the chain live in PostgreSQL and nowhere else — there is no SQLite
    fallback, so an unconfigured switch refuses instead of writing a file."""
    from app.core.db_backend import PLATFORM_ADMIN, market_connection, market_is_postgres

    if not market_is_postgres():
        _refuse(503, "MARKET_REQUIRES_POSTGRES",
                "The market runs on PostgreSQL only; set MARKET_DB_BACKEND=postgres.")
    # Every caller in this module has authorised its Party before reaching here.
    return market_connection(company_id=PLATFORM_ADMIN)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(conn, sql: str, params: Iterable = ()) -> Optional[dict]:
    r = conn.execute(sql, tuple(params)).fetchone()
    return dict(r) if r else None


def _rows(conn, sql: str, params: Iterable = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def seller_company(project_id: Optional[str]) -> Optional[str]:
    """The company that owns a project. Callers pass the CAPACITY'S project
    (capacities.project_id, alembic 084) — before 084 they passed the capacity id
    itself, read as a project id, and every producer-created capacity failed."""
    from app.core.project_registry import get_project_profile

    profile = get_project_profile(project_id) if project_id else None
    return profile.owner_company_id if profile else None


def seller_name(project_id: Optional[str]) -> Optional[str]:
    from app.core.project_registry import get_project_profile

    profile = get_project_profile(project_id) if project_id else None
    return profile.owner_company_name if profile else None


# ── events ──────────────────────────────────────────────────────────────────

class _Trail:
    def __init__(self, party: Party):
        self.party, self.events = party, []

    def add(self, event_type: str, aggregate_type: str, aggregate_id: str, data: dict,
            correlation_id: Optional[str], project_id: Optional[str] = None):
        self.events.append(dict(event_type=event_type, aggregate_type=aggregate_type,
                                aggregate_id=aggregate_id, data=data, correlation_id=correlation_id,
                                project_id=project_id))

    def write(self) -> None:
        from app.core.event_store import append_event

        for e in self.events:
            try:
                append_event(event_type=e["event_type"], aggregate_type=e["aggregate_type"],
                             aggregate_id=e["aggregate_id"], data=e["data"],
                             user_id=self.party.user_id, correlation_id=e["correlation_id"],
                             project_id=e["project_id"], company_id=self.party.company_id)
            except Exception as exc:  # noqa: BLE001 — a gap in the trail is never silent
                logger.exception("market step committed but its trail was NOT written: %s", e)
                raise MarketRefused(500, "TRAIL_WRITE_FAILED",
                                    f"The step was recorded but its audit event "
                                    f"{e['event_type']} could not be written.") from exc


def _commit(conn, trail: _Trail) -> None:
    conn.commit()
    trail.write()


# ── tokens ──────────────────────────────────────────────────────────────────

def _move_token(conn, trail: _Trail, token_id: str, expected: set[str], target: str,
                why: str, extra: Optional[dict] = None) -> None:
    from app.api.v1.tokens_sqlite import TOKEN_TRANSITIONS, TokenLifecycleState

    tok = _row(conn, "SELECT t.lifecycle_state, t.correlation_id, c.project_id FROM tokens t "
                     "JOIN capacities c ON c.id = t.capacity_id WHERE t.id = ?", (token_id,))
    if tok is None:
        _refuse(404, "TOKEN_NOT_FOUND", f"Token {token_id} does not exist.")
    current = tok["lifecycle_state"] or "MINTED"
    allowed = TOKEN_TRANSITIONS.get(TokenLifecycleState(current), [])
    if current not in expected or TokenLifecycleState(target) not in allowed:
        _refuse(409, "TOKEN_STATE", f"The token is {current}; this step needs it "
                                    f"{' or '.join(sorted(expected))} to move it to {target}.")
    sets, params = ["lifecycle_state = ?"], [target]
    for col, val in (extra or {}).items():
        sets.append(f"{col} = ?")
        params.append(val)
    conn.execute(f"UPDATE tokens SET {', '.join(sets)} WHERE id = ?", (*params, token_id))
    trail.add("token.state_changed", "token", token_id,
              {"from": current, "to": target, "reason": why, **(extra or {})},
              tok["correlation_id"], tok["project_id"])


# ── listings (anonymised) ───────────────────────────────────────────────────

OFFER_LISTING_FIELDS = ("id", "molecule", "volume_mtpd", "price_eur_kg", "delivery_start",
                        "delivery_end", "delivery_type", "delivery_basis", "price_basis",
                        "certification_pathway_required", "min_order_kg", "esg_tier", "created_at")
RFQ_LISTING_FIELDS = ("id", "molecule", "volume_mtpd", "max_price_eur_kg", "delivery_start",
                      "delivery_end", "compliance_requirements", "created_at")
# Never in a listing: company, project, capacity, token, location, names, contacts.


def commodities() -> list[dict]:
    """The commodities the market trades — tb_commodity (reference data, alembic 065).
    Screens take their molecule lists from here, never from a constant."""
    conn = _conn()
    try:
        return _rows(conn, "SELECT code, name, default_unit::text AS default_unit, market_molecule "
                           "FROM tb_commodity ORDER BY name")
    finally:
        conn.close()


def _normalise_spot_to_per_tonne(prices: dict) -> None:
    """Add `eur_per_t` to every spot row, in place, with how it was derived.

    An energy-priced molecule needs the fuel's specific energy to reach a per-tonne
    basis. Where that is unknown the field is None and `eur_per_t_basis` says why —
    a screen must be able to tell "no price" from "price in another unit".
    """
    try:
        from app.core.fuel_catalog import get_fuel
    except Exception:                                    # noqa: BLE001
        get_fuel = None                                  # type: ignore

    for molecule, row in prices.items():
        unit = (row.get("unit") or "").strip()
        base = row.get("value_base")
        row["eur_per_t"] = None
        if base is None:
            row["eur_per_t_basis"] = "no value"
            continue
        if unit in ("EUR/t",):
            row["eur_per_t"] = float(base)
            row["eur_per_t_basis"] = "already per tonne"
            continue
        if unit in ("EUR/kg",):
            row["eur_per_t"] = float(base) * 1000.0
            row["eur_per_t_basis"] = "x1000 from EUR/kg"
            continue
        if unit in ("EUR/MWh", "EUR/kWh"):
            mwh_per_t = None
            if get_fuel is not None:
                try:
                    # kWh/kg is numerically identical to MWh/t, no factor needed
                    f = get_fuel(molecule) or {}
                    sev = (f.get("measures") or {}).get("specific_energy_value")
                    if sev:
                        mwh_per_t = float(sev)
                except Exception:                              # noqa: BLE001
                    mwh_per_t = None
            if mwh_per_t:
                per_mwh = float(base) * (1000.0 if unit == "EUR/kWh" else 1.0)
                row["eur_per_t"] = per_mwh * mwh_per_t
                row["eur_per_t_basis"] = (
                    f"{per_mwh:g} EUR/MWh x {mwh_per_t:g} MWh/t specific energy")
            else:
                row["eur_per_t_basis"] = (
                    f"cannot convert {unit}: no specific_energy_value for {molecule}")
            continue
        row["eur_per_t_basis"] = f"unrecognised unit {unit!r}"


def project_economics(party: Party) -> dict:
    """The Marketplace records (alembic 066), read AS THE CALLER — RLS returns only
    the projects its company may see. Every record carries its verification
    state; the spot prices are the registry's rows for the market keys, proposed
    or approved, each with its state, so the screen can say which are unverified.
    """
    from app.core.db_backend import market_connection

    if not party.user_id:
        _refuse(401, "AUTHENTICATION_REQUIRED", "Sign in to read market records.")
    conn = market_connection()                       # the bound caller, not PLATFORM_ADMIN
    try:
        spot = _rows(conn, "SELECT c.market_molecule AS molecule, r.value_base, r.unit, r.currency, r.state, "
                           "r.source_name FROM reference_parameter r JOIN tb_commodity c "
                           "ON c.registry_pathway = r.pathway WHERE r.parameter_key IN "
                           "('market_spot_price', 'market_spot_price_energy') AND r.region = 'ANY' "
                           "AND r.state IN ('approved', 'proposed') ORDER BY r.state = 'approved' DESC")
        prices: dict = {}
        for r in spot:                               # an approved price wins over a proposal
            prices.setdefault(r["molecule"], r)
        # Normalise to EUR per tonne HERE, where the fuel's energy content is reachable.
        #
        # `market_spot_price` is EUR/t but `market_spot_price_energy` is EUR/MWh (e-NG),
        # and both land in this one field. The Marketplace screen read `spot.value_base`
        # and discarded `unit`, so a 120 EUR/MWh e-NG price was used as 120 EUR/t:
        # measured 2026-10-23 on proj_lehavre_eng, a displayed margin of -1694 EUR/MT
        # where 120 x 13.9 kWh/kg gives about +1668. Converting in the SCREEN would have
        # repeated the mistake one layer up; the fix belongs where the energy content is.
        #
        # value_base and unit are left untouched — a consumer that wants the raw row
        # still has it. `eur_per_t` is the normalised figure with its own provenance, and
        # is None (never a guess) when the conversion cannot be made.
        _normalise_spot_to_per_tonne(prices)
        sales = _rows(conn, "SELECT * FROM project_sales_detail")
        lines = _rows(conn, "SELECT * FROM project_input_line ORDER BY project_id, seq")
        classes = _rows(conn, "SELECT * FROM input_classification")
    finally:
        conn.close()
    by_project: dict = {}
    for line in lines:
        by_project.setdefault(line["project_id"], []).append(line)
    return {"spot_prices": prices, "sales_detail": {r["project_id"]: r for r in sales},
            "input_lines": by_project, "input_classification": {r["feedstock"]: r for r in classes}}


# ── the market on the order model (Phase 3, alembic 087) ────────────────────
#
# Phase 0 Q6/Q8, JML 2026-11-06. A listing is a firm SELL tb_order; an RFQ a BUY
# tb_rfq; a proposal an invited firm tb_order answering the RFQ against the listing
# (listing_order_id + rfq_id) — the proposer's acceptance. The other party's
# acceptance runs order_book._accept: fill + draft contract in one locked
# transaction. The functions below keep the names and the response shapes the
# screens read (offer / RFQ / match dicts); the rows behind them are the order
# model's, and offers / rfqs / matches are no longer written (dropped in M6).

def _monthly(start, end):
    """[(period_start, period_end)] month by month over the delivery window."""
    from datetime import date as _date, timedelta

    out, cur = [], start
    while cur <= end:
        nxt = _date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((cur, min(end, nxt - timedelta(days=1))))
        cur = nxt
    return out


def _day(v):
    from datetime import date as _date

    return _date.fromisoformat(str(v)[:10])


def market_terms(conn, *, molecule: str, volume_mtpd, price_eur_kg, delivery_start, delivery_end,
                 quality: Optional[dict] = None, clauses: Optional[list] = None,
                 seller_cp: Optional[str] = None, buyer_cp: Optional[str] = None):
    """The market's terms in the terms model: a physical product leg (seller ->
    buyer) and, when there is a price, a fixed-price payment leg (buyer -> seller),
    one flow per delivery month. Volume is t/day × days; €/kg × 1000 per tonne;
    payment on the delivered quantity (decided 2026-10-23). Parties only on a
    contract; an order or RFQ names none (D3)."""
    from decimal import Decimal

    from app.trading_book import record
    from app.trading_book.terms import TermsIn

    code = record.commodity_for_molecule(conn, molecule)
    if code is None:
        _refuse(409, "UNKNOWN_COMMODITY", f"{molecule!r} is not a traded commodity (tb_commodity).")
    start, end = _day(delivery_start), _day(delivery_end)
    if end < start:
        _refuse(422, "DELIVERY_WINDOW", "The delivery window ends before it starts.")
    rate = Decimal(str(volume_mtpd))
    product, payment = [], []
    for i, (a, b) in enumerate(_monthly(start, end), start=1):
        qty = (rate * ((b - a).days + 1)).quantize(Decimal("0.000001"))
        product.append({"seq": i, "flow_type": "physical", "period_start": a, "period_end": b, "settle_date": b,
                        "quantity": qty, "unit": "t"})
        if price_eur_kg is not None:
            payment.append({"seq": i, "flow_type": "fixed_cash", "period_start": a, "period_end": b,
                            "settle_date": b, "quantity": qty, "unit": "t",
                            "unit_price": (Decimal(str(price_eur_kg)) * 1000).quantize(Decimal("0.00000001")),
                            "quantity_basis": "delivered", "quantity_source_flow": f"1.{i}"})
    legs = [{"seq": 1, "leg_role": "product", "payer": seller_cp, "receiver": buyer_cp, "flows": product}]
    if payment:
        legs.append({"seq": 2, "leg_role": "payment", "payer": buyer_cp, "receiver": seller_cp, "flows": payment})
    return TermsIn.model_validate({"settlement": "physical", "commodity": code, "quality_spec": quality or {},
                                   "currency": "EUR", "legs": legs,
                                   "clauses": [{"seq": n, **c} for n, c in enumerate(clauses or [], start=1)]})


def _terms_summary(conn, terms_id: str) -> dict:
    """molecule, volume_mtpd, price_eur_kg, delivery window and clause attributes of stored terms."""
    from decimal import Decimal

    from app.trading_book import record

    t = record._row(conn, "SELECT co.market_molecule FROM tb_terms t JOIN tb_commodity co ON co.id = t.commodity_id "
                          "WHERE t.id = ?", (terms_id,))
    terms = record.load_terms(conn, terms_id)
    product = [f for leg in terms.legs if leg.leg_role.value == "product" for f in leg.flows]
    priced = [f for leg in terms.legs if leg.leg_role.value == "payment" for f in leg.flows if f.unit_price is not None]
    start = min((f.period_start for f in product), default=None)
    end = max((f.period_end for f in product), default=None)
    days = (end - start).days + 1 if start and end else None
    total = sum((f.quantity for f in product), Decimal(0))
    attrs = {}
    for c in terms.clauses:
        attrs.update({k: v for k, v in (c.attrs or {}).items()})
        if c.clause_type in ("delivery", "payment") and "text" in (c.attrs or {}):
            attrs[f"{c.clause_type}_terms"] = c.attrs["text"]
    return {"molecule": (t or {}).get("market_molecule"), "volume_mtpd": float(total / days) if days else None,
            "price_eur_kg": float(priced[0].unit_price / 1000) if priced else None,
            "delivery_start": start.isoformat() if start else None, "delivery_end": end.isoformat() if end else None,
            "quality": terms.quality_spec, "attrs": attrs}


def _company_of(conn, cp) -> Optional[str]:
    r = _row(conn, "SELECT company_id FROM tb_counterparty WHERE id = ?", (str(cp),)) if cp else None
    return r["company_id"] if r else None


def _iso(v) -> Optional[str]:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None else None)


# Order status -> the listing's states the screens know (063's vocabulary).
LISTING_STATE = {"draft": "DRAFT", "open": "OPEN", "partially_filled": "OPEN", "filled": "MATCHED",
                 "cancelled": "WITHDRAWN", "expired": "EXPIRED", "rejected": "WITHDRAWN"}
LISTING_STATUS = {"draft": "draft", "open": "active", "partially_filled": "active", "filled": "matched",
                  "cancelled": "expired", "expired": "expired", "rejected": "expired"}
# tb_rfq status -> the RFQ states the screens know (Q8 read backwards).
RFQ_STATE = {"draft": "draft", "published": "open", "closed": "matched", "withdrawn": "withdrawn",
             "expired": "expired"}


def _listing(conn, o: dict) -> dict:
    """A listing (a sell tb_order) in the offer shape, with its token's state and project."""
    s = _terms_summary(conn, str(o["terms_id"]))
    tok = _row(conn, "SELECT t.lifecycle_state, t.correlation_id, t.capacity_id, t.carbon_intensity_gco2e_mj, "
                     "t.certification_pathway, c.project_id FROM tokens t JOIN capacities c ON c.id = t.capacity_id "
                     "WHERE t.id = ?", (o["token_id"],)) if o.get("token_id") else None
    state = LISTING_STATE.get(o["status"], "WITHDRAWN")
    if state == "MATCHED" and tok and tok["lifecycle_state"] == "SETTLED":
        state = "SETTLED"
    a = s["attrs"]
    return {"id": str(o["id"]), "token_id": o.get("token_id"), "molecule": s["molecule"],
            "volume_mtpd": s["volume_mtpd"], "price_eur_kg": s["price_eur_kg"],
            "delivery_start": s["delivery_start"], "delivery_end": s["delivery_end"], "location": o.get("location"),
            "status": LISTING_STATUS.get(o["status"], "expired"), "listing_state": state,
            "offer_type": o["order_type"], "correlation_id": o.get("correlation_id"),
            "delivery_type": a.get("delivery_type"), "delivery_basis": a.get("delivery_basis"),
            "price_basis": a.get("price_basis"),
            "certification_pathway_required": s["quality"].get("certification_pathway_required"),
            "min_order_kg": float(o["min_fill_quantity"]) * 1000 if o.get("min_fill_quantity") else None,
            "esg_tier": s["quality"].get("esg_tier"), "created_at": _iso(o["created_at"]),
            "capacity_id": (tok or {}).get("capacity_id"), "capacity_project_id": (tok or {}).get("project_id"),
            "token_state": (tok or {}).get("lifecycle_state"), "token_correlation_id": (tok or {}).get("correlation_id"),
            "carbon_intensity_gco2e_mj": (tok or {}).get("carbon_intensity_gco2e_mj"),
            "certification_pathway": (tok or {}).get("certification_pathway"),
            "seller_company_id": _company_of(conn, o["owner_id"])}


def _listing_by_id(conn, offer_id: str, lock: bool = False) -> dict:
    o = _row(conn, "SELECT * FROM tb_order WHERE id = ? AND listing_order_id IS NULL AND rfq_id IS NULL"
                   + (" FOR UPDATE" if lock else ""), (offer_id,)) if _is_uuid(offer_id) else None
    if o is None:
        _refuse(404, "OFFER_NOT_FOUND", "No offer with that id.")
    return o


def _is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except ValueError:
        return False


def _rfq(conn, r: dict) -> dict:
    """An RFQ (a tb_rfq) in the shape the screens know."""
    s = _terms_summary(conn, str(r["terms_id"]))
    return {"id": str(r["id"]), "buyer_company_id": _company_of(conn, r["requester_id"]),
            "created_by": r.get("created_by_user"), "molecule": s["molecule"], "volume_mtpd": s["volume_mtpd"],
            "max_price_eur_kg": s["price_eur_kg"], "delivery_start": s["delivery_start"],
            "delivery_end": s["delivery_end"], "location": r.get("location"), "buyer_name": r.get("buyer_name"),
            "buyer_contact": r.get("buyer_contact"),
            "compliance_requirements": r.get("compliance_requirements") or [],
            "status": RFQ_STATE.get(r["status"], r["status"]), "correlation_id": r.get("correlation_id"),
            "created_at": _iso(r["created_at"]), "updated_at": _iso(r["updated_at"])}


def _rfq_by_id(conn, rfq_id: str, lock: bool = False) -> Optional[dict]:
    if not _is_uuid(rfq_id):
        return None
    return _row(conn, "SELECT * FROM tb_rfq WHERE id = ?" + (" FOR UPDATE" if lock else ""), (rfq_id,))


def _order_event(conn, order_id: str, from_status: Optional[str], to_status: str, actor: str, reason: str) -> None:
    conn.execute("INSERT INTO tb_order_event (order_id, from_status, to_status, actor_id, reason) "
                 "VALUES (?, ?, ?, ?, ?)", (order_id, from_status, to_status, actor, reason))


# ── listings ────────────────────────────────────────────────────────────────

def create_listing(party: Party, token: dict, *, volume_mtpd: float, price_eur_kg: float, delivery_start: str,
                   delivery_end: str, location: Optional[str] = None, offer_type: str = "firm",
                   delivery_type: Optional[str] = None, delivery_basis: Optional[str] = None,
                   price_basis: Optional[str] = None, certification_pathway_required: Optional[str] = None,
                   min_order_kg: Optional[float] = None, esg_tier: Optional[str] = None,
                   open_now: bool = False) -> dict:
    """A draft listing (a firm SELL order) of the caller's own token. The caller has
    already been checked as the token's project owner (marketplace route)."""
    from decimal import Decimal

    from app.trading_book import record

    _trader(party)
    if volume_mtpd <= 0 or price_eur_kg <= 0:
        _refuse(422, "LISTING_TERMS", "Volume and price must be positive.")
    conn, trail = _conn(), _Trail(party)
    try:
        quality = {k: v for k, v in (("certification_pathway", token.get("certification_pathway")),
                                     ("carbon_intensity_gco2e_mj", token.get("carbon_intensity_gco2e_mj")),
                                     ("certification_pathway_required", certification_pathway_required),
                                     ("esg_tier", esg_tier)) if v is not None}
        quality = {k: (v if isinstance(v, (list, str)) else str(v)) for k, v in quality.items()}
        clauses = []
        if delivery_type or delivery_basis:
            clauses.append({"clause_type": "delivery", "attrs": {k: v for k, v in (
                ("delivery_type", delivery_type), ("delivery_basis", delivery_basis)) if v}})
        if price_basis:
            clauses.append({"clause_type": "price", "attrs": {"price_basis": price_basis}})
        terms = market_terms(conn, molecule=token["molecule"], volume_mtpd=volume_mtpd, price_eur_kg=price_eur_kg,
                             delivery_start=delivery_start, delivery_end=delivery_end, quality=quality, clauses=clauses)
        from app.trading_book import validation

        failed = validation.validate(terms, "order")
        if failed:
            _refuse(422, "TERMS_INVALID", "The listing's terms break rules " + ", ".join(failed) + ".")
        w = record.write_terms(conn, terms, party.company_id, freeze=False)
        order_id = str(uuid.uuid4())
        conn.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, order_type, all_or_nothing, min_fill_quantity, "
                     "valid_until, status, visibility, token_id, correlation_id, location, created_by_user) "
                     "VALUES (?, ?, 'sell', ?, ?, false, ?, ?, 'draft', 'platform', ?, ?, ?, ?)",
                     (order_id, record.counterparty_for(conn, party.company_id), w["terms_id"],
                      "firm" if offer_type != "indicative" else "indicative",
                      Decimal(str(min_order_kg)) / 1000 if min_order_kg else None,
                      _day(delivery_end).isoformat() + "T23:59:59+00:00", token["id"], token.get("correlation_id"),
                      location, party.user_id))
        _order_event(conn, order_id, None, "draft", party.user_id, "listing created")
        trail.add("offer.created", "offer", order_id, {"token_id": token["id"], "volume_mtpd": volume_mtpd},
                  token.get("correlation_id"), token.get("capacity_project_id"))
        _commit(conn, trail)
    finally:
        conn.close()
    return open_offer(party, order_id) if open_now else my_listing(party, order_id)


def my_listing(party: Party, offer_id: str) -> dict:
    conn = _conn()
    try:
        o = _listing(conn, _listing_by_id(conn, offer_id))
        if not party.is_admin and o["seller_company_id"] != party.company_id:
            _refuse(404, "OFFER_NOT_FOUND", "No offer of yours with that id.")
        return o
    finally:
        conn.close()


def my_listings(party: Party) -> list[dict]:
    conn = _conn()
    try:
        cp = _row(conn, "SELECT id FROM tb_counterparty WHERE company_id = ?", (party.company_id,))
        if cp is None and not party.is_admin:
            return []
        sql = "SELECT * FROM tb_order WHERE listing_order_id IS NULL AND rfq_id IS NULL AND token_id IS NOT NULL"
        params: list = []
        if not party.is_admin:
            sql += " AND owner_id = ?"
            params.append(str(cp["id"]))
        return [_listing(conn, o) for o in _rows(conn, sql + " ORDER BY created_at DESC", params)]
    finally:
        conn.close()


def offer_listings(party: Party, molecule: Optional[str] = None) -> list[dict]:
    conn = _conn()
    try:
        out = []
        for o in _rows(conn, "SELECT * FROM tb_order WHERE listing_order_id IS NULL AND rfq_id IS NULL "
                             "AND token_id IS NOT NULL AND status = 'open' AND visibility = 'platform' "
                             "ORDER BY created_at DESC"):
            r = _listing(conn, o)
            if molecule and r["molecule"] != molecule:
                continue
            item = {k: r.get(k) for k in OFFER_LISTING_FIELDS}
            item["carbon_intensity_gco2e_mj"] = r["carbon_intensity_gco2e_mj"]
            item["certification_pathway"] = r["certification_pathway"]
            item["mine"] = bool(party.company_id) and r["seller_company_id"] == party.company_id
            if item["mine"]:
                item["project_id"] = r["capacity_project_id"]      # the seller's own; never anyone else's
            out.append(item)
        return out
    finally:
        conn.close()


def open_offer(party: Party, offer_id: str) -> dict:
    """draft -> open: the listing goes live, its terms freeze, its token is reserved (MINTED -> RESERVED)."""
    from app.trading_book import record

    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _listing_by_id(conn, offer_id, lock=True)
        lv = _listing(conn, o)
        if lv["seller_company_id"] != party.company_id:
            _refuse(403, "NOT_YOUR_OFFER", "Only the company that owns the project can list its offer.")
        if o["status"] != "draft":
            _refuse(409, "LISTING_STATE", f"The listing is {lv['listing_state']}, not DRAFT.")
        if _row(conn, "SELECT 1 AS x FROM tb_order WHERE token_id = ? AND id <> ? AND listing_order_id IS NULL "
                      "AND rfq_id IS NULL AND status IN ('open', 'partially_filled', 'filled')", (o["token_id"], offer_id)):
            _refuse(409, "TOKEN_ALREADY_LISTED", "This token already backs a live listing. One token is one "
                                                 "tradeable lot: mint another token to list more volume.")
        record.freeze(conn, str(o["terms_id"]))
        conn.execute("UPDATE tb_order SET status = 'open', valid_from = now(), updated_at = now() WHERE id = ?", (offer_id,))
        _order_event(conn, offer_id, "draft", "open", party.user_id, "listed")
        _move_token(conn, trail, o["token_id"], {"MINTED"}, "RESERVED", f"listed as offer {offer_id}")
        trail.add("offer.opened", "offer", offer_id, {"token_id": o["token_id"]}, lv["token_correlation_id"],
                  lv["capacity_project_id"])
        _commit(conn, trail)
        return _listing(conn, _listing_by_id(conn, offer_id))
    finally:
        conn.close()


def _close_proposals(conn, trail: _Trail, party: Party, column: str, value: str, reason: str,
                     keep: Optional[str] = None) -> None:
    for p in _rows(conn, f"SELECT id, status, correlation_id FROM tb_order WHERE {column} = ? AND "
                         "listing_order_id IS NOT NULL AND status = 'open'", (value,)):
        if keep and str(p["id"]) == keep:
            continue
        conn.execute("UPDATE tb_order SET status = 'cancelled', updated_at = now() WHERE id = ?", (str(p["id"]),))
        _order_event(conn, str(p["id"]), "open", "cancelled", party.user_id, reason)
        trail.add("match.superseded" if reason.startswith("superseded") else "match.cancelled", "match",
                  str(p["id"]), {"reason": reason}, p["correlation_id"])


def withdraw_offer(party: Party, offer_id: str, expire: bool = False) -> dict:
    """Withdraw (or expire) a draft or open listing: its token is released and pending proposals close."""
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _listing_by_id(conn, offer_id, lock=True)
        lv = _listing(conn, o)
        if lv["seller_company_id"] != party.company_id:
            _refuse(403, "NOT_YOUR_OFFER", "Only the company that owns the project can withdraw its offer.")
        if o["status"] not in ("draft", "open"):
            _refuse(409, "LISTING_STATE", f"A {lv['listing_state']} listing cannot be withdrawn: a match has "
                                          f"been agreed on it.")
        _close_proposals(conn, trail, party, "listing_order_id", offer_id, "cancelled: listing withdrawn")
        target = "expired" if expire else "cancelled"
        conn.execute("UPDATE tb_order SET status = ?, updated_at = now() WHERE id = ?", (target, offer_id))
        _order_event(conn, offer_id, o["status"], target, party.user_id,
                     "listing expired" if expire else "listing withdrawn")
        if o["status"] == "open":
            _move_token(conn, trail, o["token_id"], {"RESERVED"}, "MINTED", f"listing {offer_id} withdrawn")
        trail.add("offer.withdrawn", "offer", offer_id, {"from": lv["listing_state"]}, lv["token_correlation_id"],
                  lv["capacity_project_id"])
        _commit(conn, trail)
        return _listing(conn, _listing_by_id(conn, offer_id))
    finally:
        conn.close()


# ── RFQs ────────────────────────────────────────────────────────────────────

RFQ_TRANSITIONS = {"draft": ("open", "cancelled"), "open": ("withdrawn", "expired")}
# The screens' RFQ moves -> tb_rfq (Q8: a cancelled draft is withdrawn).
RFQ_MOVE = {"open": "published", "cancelled": "withdrawn", "withdrawn": "withdrawn", "expired": "expired"}


def create_rfq(party: Party, *, molecule: str, volume_mtpd: float, delivery_start: str,
               delivery_end: str, max_price_eur_kg: Optional[float] = None,
               location: Optional[str] = None, buyer_contact: Optional[str] = None,
               compliance_requirements: Optional[list] = None, status: str = "open") -> dict:
    from app.trading_book import record, validation

    _trader(party)
    if status not in ("draft", "open"):
        _refuse(422, "RFQ_STATUS", "A new RFQ is either 'draft' or 'open'.")
    if volume_mtpd <= 0:
        _refuse(422, "RFQ_VOLUME", "Volume must be positive.")
    if delivery_end < delivery_start:
        _refuse(422, "RFQ_WINDOW", "The delivery window ends before it starts.")
    rfq_id = str(uuid.uuid4())
    correlation_id = f"RFQ-{rfq_id[:8]}"
    conn, trail = _conn(), _Trail(party)
    try:
        terms = market_terms(conn, molecule=molecule, volume_mtpd=volume_mtpd, price_eur_kg=max_price_eur_kg,
                             delivery_start=delivery_start, delivery_end=delivery_end)
        failed = validation.validate(terms, "rfq")
        if failed:
            _refuse(422, "TERMS_INVALID", "The RFQ's terms break rules " + ", ".join(failed) + ".")
        w = record.write_terms(conn, terms, party.company_id, freeze=status == "open")
        conn.execute("INSERT INTO tb_rfq (id, requester_id, side, terms_id, valid_until, status, buyer_name, "
                     "buyer_contact, location, compliance_requirements, correlation_id, created_by_user) "
                     "VALUES (?, ?, 'buy', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (rfq_id, record.counterparty_for(conn, party.company_id), w["terms_id"],
                      _day(delivery_end).isoformat() + "T23:59:59+00:00", "published" if status == "open" else "draft",
                      party.company_name, buyer_contact, location, json.dumps(compliance_requirements or []),
                      correlation_id, party.user_id))
        trail.add("rfq.created", "rfq", rfq_id, {"molecule": molecule, "volume_mtpd": volume_mtpd,
                                                 "status": status}, correlation_id)
        _commit(conn, trail)
        return _rfq(conn, _rfq_by_id(conn, rfq_id))
    finally:
        conn.close()


def transition_rfq(party: Party, rfq_id: str, new_status: str) -> dict:
    from app.trading_book import record

    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        r = _rfq_by_id(conn, rfq_id, lock=True)
        if r is None or _company_of(conn, r["requester_id"]) != party.company_id:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ of yours with that id.")
        current = RFQ_STATE.get(r["status"], r["status"])
        if new_status not in RFQ_TRANSITIONS.get(current, ()):
            _refuse(409, "RFQ_TRANSITION", f"An RFQ that is {current} cannot become "
                                           f"{new_status}. 'matched' is set by the market.")
        if new_status in ("withdrawn", "expired"):
            _close_proposals(conn, trail, party, "rfq_id", rfq_id, "cancelled: RFQ closed")
        if new_status == "open":
            record.freeze(conn, str(r["terms_id"]))
        conn.execute("UPDATE tb_rfq SET status = ?, updated_at = now() WHERE id = ?", (RFQ_MOVE[new_status], rfq_id))
        trail.add(f"rfq.{new_status}", "rfq", rfq_id, {"from": current, "to": new_status}, r["correlation_id"])
        _commit(conn, trail)
        return _rfq(conn, _rfq_by_id(conn, rfq_id))
    finally:
        conn.close()


def my_rfqs(party: Party) -> list[dict]:
    conn = _conn()
    try:
        cp = _row(conn, "SELECT id FROM tb_counterparty WHERE company_id = ?", (party.company_id,))
        if cp is None:
            return []
        return [_rfq(conn, r) for r in _rows(conn, "SELECT * FROM tb_rfq WHERE requester_id = ? "
                                                   "ORDER BY created_at DESC", (str(cp["id"]),))]
    finally:
        conn.close()


def rfq_listings(party: Party, molecule: Optional[str] = None) -> list[dict]:
    conn = _conn()
    try:
        out = []
        for r in _rows(conn, "SELECT * FROM tb_rfq WHERE status = 'published' ORDER BY created_at DESC"):
            v = _rfq(conn, r)
            if molecule and v["molecule"] != molecule:
                continue
            item = {k: v.get(k) for k in RFQ_LISTING_FIELDS}
            item["mine"] = bool(party.company_id) and v["buyer_company_id"] == party.company_id
            out.append(item)
        return out
    finally:
        conn.close()


# ── proposals (matches) ─────────────────────────────────────────────────────

def _score(offer: dict, rfq: dict) -> int:
    from app.api.v1.matching_sqlite import calculate_match_score

    return calculate_match_score(offer, rfq)


def _match(conn, p: dict) -> dict:
    """A proposal (an invited firm order answering an RFQ against a listing) in the match shape."""
    listing = _listing(conn, _row(conn, "SELECT * FROM tb_order WHERE id = ?", (str(p["listing_order_id"]),)))
    rfq = _rfq(conn, _rfq_by_id(conn, str(p["rfq_id"])))
    s = _terms_summary(conn, str(p["terms_id"]))
    proposer = _company_of(conn, p["owner_id"])
    events = _rows(conn, "SELECT * FROM tb_order_event WHERE order_id = ? ORDER BY id", (str(p["id"]),))
    created, closed = (events[0] if events else {}), (events[-1] if len(events) > 1 else {})
    seller, buyer = listing["seller_company_id"], rfq["buyer_company_id"]
    status = {"open": "pending", "filled": "accepted"}.get(p["status"])
    if status is None:
        reason = (closed.get("reason") or "")
        status = "declined" if reason.startswith("declined") else "superseded" if reason.startswith(
            "superseded") else "cancelled"
    accepted = {}
    if created:
        accepted["seller" if proposer == seller else "buyer"] = (created["actor_id"], _iso(created["at"]))
    if p["status"] == "filled" and closed:
        accepted["buyer" if proposer == seller else "seller"] = (closed["actor_id"], _iso(closed["at"]))
    return {"id": str(p["id"]), "offer_id": str(p["listing_order_id"]), "rfq_id": str(p["rfq_id"]),
            "match_score": p.get("match_score"), "volume_mtpd": s["volume_mtpd"], "price_eur_kg": s["price_eur_kg"],
            "status": status, "created_at": _iso(p["created_at"]), "project_id": listing["capacity_project_id"],
            "token_id": listing["token_id"], "seller_company_id": seller, "buyer_company_id": buyer,
            "molecule": s["molecule"], "delivery_start": s["delivery_start"], "delivery_end": s["delivery_end"],
            "correlation_id": p.get("correlation_id"), "created_by": p.get("created_by_user"),
            "seller_accepted_by": accepted.get("seller", (None, None))[0],
            "seller_accepted_at": accepted.get("seller", (None, None))[1],
            "buyer_accepted_by": accepted.get("buyer", (None, None))[0],
            "buyer_accepted_at": accepted.get("buyer", (None, None))[1],
            "delivery_terms": s["attrs"].get("delivery_terms"), "payment_terms": s["attrs"].get("payment_terms"),
            "buyer_name": rfq["buyer_name"], "proposer_company_id": proposer}


def _proposal(conn, match_id: str, lock: bool = False) -> dict:
    p = _row(conn, "SELECT * FROM tb_order WHERE id = ? AND listing_order_id IS NOT NULL"
                   + (" FOR UPDATE" if lock else ""), (match_id,)) if _is_uuid(match_id) else None
    if p is None:
        _refuse(404, "MATCH_NOT_FOUND", "No match with that id.")
    return p


def _matchable(conn, o: dict, rfq: dict, minimum: int = MIN_MATCH_SCORE) -> Optional[int]:
    """Score if this listing and RFQ may be matched now, else None."""
    if (o["listing_state"] != "OPEN" or o["token_state"] != "RESERVED" or rfq["status"] != "open"
            or o["molecule"] != rfq["molecule"]):
        return None
    if o["seller_company_id"] == rfq["buyer_company_id"]:
        return None                                    # no self-trade
    if _row(conn, "SELECT 1 AS x FROM tb_order WHERE listing_order_id = ? AND rfq_id = ? AND status IN "
                  "('open', 'filled')", (o["id"], rfq["id"])):
        return None
    score = _score(o, rfq)
    return score if score >= minimum else None


def create_match(party: Party, offer_id: str, rfq_id: str, *, delivery_terms: Optional[str] = None,
                 payment_terms: Optional[str] = None) -> dict:
    """Propose one listing against one RFQ (Q6): an invited firm order on the proposer's
    side — the proposer's acceptance — on the listing's price, over the overlap of the
    two windows, for the smaller volume, with the delivery and payment terms agreed
    with the proposal. The other party's acceptance makes the contract."""
    from app.trading_book import record, validation

    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _listing(conn, _listing_by_id(conn, offer_id))
        r = _rfq_by_id(conn, rfq_id, lock=True)
        if r is None:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ with that id.")
        rfq = _rfq(conn, r)
        seller, buyer = o["seller_company_id"], rfq["buyer_company_id"]
        if party.company_id not in (seller, buyer):
            _refuse(403, "NOT_A_PARTY", "You can only match your own offer or your own RFQ.")
        if seller == buyer:
            _refuse(409, "SELF_TRADE", "A company cannot match its own offer with its own RFQ.")
        score = _matchable(conn, o, rfq, minimum=0)    # bilateral (2B): the score informs, never gates
        if score is None:
            _refuse(409, "NOT_MATCHABLE", "This pair cannot be matched: the listing or RFQ is not "
                                          "open, the molecules differ, or a match already exists.")
        clauses = [{"clause_type": k, "attrs": {"text": t.strip()}} for k, t in
                   (("delivery", delivery_terms), ("payment", payment_terms)) if t and t.strip()]
        terms = market_terms(conn, molecule=o["molecule"], volume_mtpd=min(o["volume_mtpd"], rfq["volume_mtpd"]),
                             price_eur_kg=o["price_eur_kg"], delivery_start=max(o["delivery_start"], rfq["delivery_start"]),
                             delivery_end=min(o["delivery_end"], rfq["delivery_end"]),
                             quality=_terms_summary(conn, str(_listing_by_id(conn, offer_id)["terms_id"]))["quality"],
                             clauses=clauses)
        failed = validation.validate(terms, "order")
        if failed:
            _refuse(409, "TERMS_INVALID", "The proposed terms break rules " + ", ".join(failed) + ".")
        w = record.write_terms(conn, terms, party.company_id)
        proposal_id = str(uuid.uuid4())
        other = buyer if party.company_id == seller else seller
        conn.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, order_type, all_or_nothing, valid_until, "
                     "status, rfq_id, visibility, token_id, correlation_id, listing_order_id, match_score, "
                     "created_by_user) VALUES (?, ?, ?, ?, 'firm', true, ?, 'open', ?, 'invited', ?, ?, ?, ?, ?)",
                     (proposal_id, record.counterparty_for(conn, party.company_id),
                      "sell" if party.company_id == seller else "buy", w["terms_id"],
                      r["valid_until"], rfq_id, o["token_id"], o["token_correlation_id"], offer_id, score,
                      party.user_id))
        conn.execute("INSERT INTO tb_order_invitee (order_id, counterparty_id) VALUES (?, ?)",
                     (proposal_id, record.counterparty_for(conn, other)))
        _order_event(conn, proposal_id, None, "open", party.user_id, "proposal: the proposer's acceptance")
        trail.add("match.created", "match", proposal_id,
                  {"offer_id": offer_id, "rfq_id": rfq_id, "score": score,
                   "rfq_correlation_id": rfq["correlation_id"]}, o["token_correlation_id"], o["capacity_project_id"])
        trail.add("match.accepted", "match", proposal_id,
                  {"side": "seller" if party.company_id == seller else "buyer"}, o["token_correlation_id"],
                  o["capacity_project_id"])
        _commit(conn, trail)
        return _match(conn, _proposal(conn, proposal_id))
    finally:
        conn.close()


def run_matching(party: Party) -> dict:
    """SUSPENDED unless MARKET_AUTO_MATCHING (JML, 2026-10-23, spec decision 2B): GEX
    pairing third parties' interests may make it a trading venue, which counsel must
    rule on first. On the order model a GEX-made proposal would also be GEX trading,
    so with the switch on this still refuses until counsel and JML say how it works."""
    from app.core.config import settings

    if not settings.MARKET_AUTO_MATCHING:
        _refuse(409, "AUTO_MATCHING_SUSPENDED",
                "Automated matching is switched off. Choose a listing and propose a match to it; "
                "it binds only when both parties accept.")
    _refuse(501, "AUTO_MATCHING_NOT_BUILT", "Automated matching is not built on the order model.")


def _side(party: Party, m: dict) -> str:
    if party.company_id == m["seller_company_id"]:
        return "seller"
    if party.company_id == m["buyer_company_id"]:
        return "buyer"
    _refuse(404, "MATCH_NOT_FOUND", "No match of yours with that id.")


def _reveal(m: dict) -> dict:
    """What a party sees of its own match: both counterparties and the agreed terms."""
    out = dict(m)
    out["seller_company_name"] = seller_name(m.get("project_id"))
    return out


def my_matches(party: Party) -> list[dict]:
    conn = _conn()
    try:
        out = []
        for p in _rows(conn, "SELECT * FROM tb_order WHERE listing_order_id IS NOT NULL ORDER BY created_at DESC"):
            m = _match(conn, p)
            if party.company_id in (m["seller_company_id"], m["buyer_company_id"]):
                out.append({**_reveal(m), "side": "seller" if m["seller_company_id"] == party.company_id else "buyer"})
        return out
    finally:
        conn.close()


def accept_match(party: Party, match_id: str) -> dict:
    """The other party's acceptance (Q6): fill and draft contract in one locked
    transaction (order_book._accept); the listing is consumed, the RFQ closes, the
    other proposals on either are superseded, and the token moves RESERVED -> MATCHED."""
    from app.core import order_book
    from app.trading_book.record import RecordRefused

    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        p = _proposal(conn, match_id, lock=True)
        m = _match(conn, p)
        side = _side(party, m)
        if m["status"] != "pending":
            _refuse(409, "MATCH_STATE", f"The match is {m['status']}, not pending.")
        if party.company_id == m["proposer_company_id"]:
            _refuse(409, "ALREADY_ACCEPTED", f"The {side} side has already accepted: it proposed the match.")
        listing = _listing_by_id(conn, m["offer_id"], lock=True)
        r = _rfq_by_id(conn, m["rfq_id"], lock=True)
        if listing["status"] != "open" or r["status"] != "published":
            _refuse(409, "NO_LONGER_AVAILABLE", "The listing or the RFQ is no longer open.")
        try:
            made = order_book._accept(conn, party, match_id, None, origin_ref=f"match:{match_id}",
                                      project_id=m["project_id"], correlation_id=m["correlation_id"],
                                      token_ids=[m["token_id"]] if m["token_id"] else (),
                                      note=f"match {match_id} accepted by both parties")
        except RecordRefused as exc:
            _refuse(exc.status, exc.code, exc.message)
        conn.execute("UPDATE tb_order SET status = 'filled', updated_at = now() WHERE id = ?", (m["offer_id"],))
        _order_event(conn, m["offer_id"], "open", "filled", party.user_id, f"listing taken by match {match_id}")
        conn.execute("UPDATE tb_rfq SET status = 'closed', updated_at = now() WHERE id = ?", (m["rfq_id"],))
        _close_proposals(conn, trail, party, "listing_order_id", m["offer_id"], f"superseded by {match_id}",
                         keep=match_id)
        _close_proposals(conn, trail, party, "rfq_id", m["rfq_id"], f"superseded by {match_id}", keep=match_id)
        _move_token(conn, trail, m["token_id"], {"RESERVED"}, "MATCHED", f"match {match_id} agreed")
        trail.add("match.accepted", "match", match_id, {"side": side}, m["correlation_id"], m["project_id"])
        trail.add("match.agreed", "match", match_id, {"offer_id": m["offer_id"], "rfq_id": m["rfq_id"]},
                  m["correlation_id"], m["project_id"])
        trail.add("contract.created", "contract", made["contract_id"],
                  {"match_id": match_id, "token_id": m["token_id"], "contract_ref": made["contract_ref"],
                   "terms_hash": made["terms_hash"]}, m["correlation_id"], m["project_id"])
        _commit(conn, trail)
        return _reveal(_match(conn, _proposal(conn, match_id)))
    finally:
        conn.close()


def decline_match(party: Party, match_id: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        p = _proposal(conn, match_id, lock=True)
        m = _match(conn, p)
        side = _side(party, m)
        if m["status"] != "pending":
            _refuse(409, "MATCH_STATE", f"The match is {m['status']}, not pending.")
        conn.execute("UPDATE tb_order SET status = 'cancelled', updated_at = now() WHERE id = ?", (match_id,))
        _order_event(conn, match_id, "open", "cancelled", party.user_id, f"declined by the {side}")
        trail.add("match.declined", "match", match_id, {"side": side}, m["correlation_id"], m["project_id"])
        _commit(conn, trail)
        return _reveal(_match(conn, _proposal(conn, match_id)))
    finally:
        conn.close()


# ── contracts — the one contract record (alembic 065/083, Phase 1) ──────────
#
# Since Phase 1 of "One contract record" (JML 2026-11-05/06) an agreed match
# creates its contract in the record (trading_book/record.py) in the SAME
# transaction as the agreement, and `contracts` (063) is never written again.
# The contract is a draft — version 1, pending_confirmation, UNVERIFIED — until
# both parties confirm it with four eyes each (TRADE_CONFIRM, core/order_book).
# A contract is a commercial record: it never reaches the gate engine.

def _contract_view(conn, party: Party, contract_id: str) -> dict:
    from app.trading_book import record

    view = record.market_view(conn, contract_id)
    if view is None or not (party.is_admin or party.company_id in (view["seller_company_id"],
                                                                   view["buyer_company_id"])):
        _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
    return view


def create_contract(party: Party, match_id: str, *, delivery_terms: Optional[str] = None,
                    payment_terms: Optional[str] = None) -> dict:
    """COMPATIBILITY (Q6). The contract already exists from the moment both sides
    accepted; this returns it. Terms typed now that differ from what both sides
    accepted are refused — they would be a change, i.e. a new version."""
    from app.trading_book import record

    _trader(party)
    conn = _conn()
    try:
        m = _match(conn, _proposal(conn, match_id))
        _side(party, m)
        if m["status"] != "accepted":
            _refuse(409, "MATCH_NOT_AGREED", "A contract needs a match both parties have accepted.")
        c = record.by_origin(conn, f"match:{match_id}")
        if c is None:
            _refuse(409, "CONTRACT_MISSING", "This agreed match has no contract record.")
        view = _contract_view(conn, party, str(c["id"]))
        for name, typed in (("delivery_terms", delivery_terms), ("payment_terms", payment_terms)):
            if (typed or "").strip() and typed.strip() != (view.get(name) or ""):
                _refuse(409, "TERMS_AGREED_AT_ACCEPTANCE",
                        f"The {name.replace('_', ' ')} were agreed with the match; a change is a new version.")
        return view
    finally:
        conn.close()


def my_contracts(party: Party) -> list[dict]:
    from app.trading_book import record

    conn = _conn()
    try:
        return record.market_views_for(conn, party.company_id)
    finally:
        conn.close()


# ── settlement: the cash leg, and the token's title ─────────────────────────

def create_settlement(party: Party, contract_id: str, *, settlement_type: str, volume_kg: float,
                      settlement_date: Optional[str] = None, currency: str = "EUR") -> dict:
    """Everything except the quantity comes from the contract — nothing is typed twice."""
    from app.api.v1.settlement_events import SettlementType, _hash_settlement, _log_event

    _trader(party)
    if volume_kg <= 0:
        _refuse(422, "SETTLEMENT_VOLUME", "The settled quantity must be positive.")
    try:
        SettlementType(settlement_type)
    except ValueError:
        _refuse(422, "SETTLEMENT_TYPE", f"Unknown settlement type {settlement_type!r}.")
    conn, trail = _conn(), _Trail(party)
    try:
        c = _contract_view(conn, party, contract_id)
        if c["status"] not in ("confirmed", "active"):
            _refuse(409, "CONTRACT_NOT_CONFIRMED",
                    f"The contract is {c['status']}: both parties confirm it before anything is settled.")
        settlement_id, now = str(uuid.uuid4()), _now()
        total = round(volume_kg * (c["price_eur_kg"] or 0), 2)
        audit_hash = _hash_settlement({"settlement_id": settlement_id, "contract_id": contract_id,
                                       "token_id": c["token_id"], "volume_kg": volume_kg,
                                       "total_amount": total, "created_at": now})
        conn.execute(
            "INSERT INTO settlement_events (settlement_id, contract_id, project_id, token_id, "
            "counterparty_buyer_id, counterparty_seller_id, settlement_type, settlement_status, "
            "volume_kg, price_per_kg, total_amount, currency, settlement_date, audit_hash, version, "
            "created_at, updated_at, correlation_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (settlement_id, contract_id, c["project_id"], c["token_id"], c["buyer_company_id"],
             c["seller_company_id"], settlement_type, "PENDING", volume_kg, c["price_eur_kg"], total,
             currency, settlement_date, audit_hash, 1, now, now, c["correlation_id"]))
        _log_event(conn, settlement_id, c["project_id"], "settlement.created", party.user_id,
                   new_val=contract_id)
        trail.add("settlement.created", "settlement", settlement_id,
                  {"contract_id": contract_id, "volume_kg": volume_kg, "total_amount": total},
                  c["correlation_id"], c["project_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM settlement_events WHERE settlement_id = ?", (settlement_id,))
    finally:
        conn.close()


def confirm_settlement(party: Party, settlement_id: str, *, payment_reference: str) -> dict:
    """The seller confirms the payment arrived: the token is SETTLED and its title passes to the buyer."""
    from app.api.v1.settlement_events import _hash_settlement, _log_event

    _trader(party)
    if not (payment_reference or "").strip():
        _refuse(422, "PAYMENT_REFERENCE_REQUIRED", "Confirmation names the bank payment reference.")
    conn, trail = _conn(), _Trail(party)
    try:
        s = _row(conn, "SELECT * FROM settlement_events WHERE settlement_id = ?", (settlement_id,))
        if s is None or party.company_id not in (s["counterparty_seller_id"], s["counterparty_buyer_id"]):
            _refuse(404, "SETTLEMENT_NOT_FOUND", "No settlement of yours with that id.")
        if party.company_id != s["counterparty_seller_id"]:
            _refuse(403, "PAYEE_CONFIRMS", "The seller, who receives the payment, confirms it.")
        if s["settlement_status"] != "PENDING":
            _refuse(409, "SETTLEMENT_STATE", f"The settlement is {s['settlement_status']}, not PENDING.")
        now = _now()
        conn.execute("UPDATE settlement_events SET settlement_status = 'CONFIRMED', payment_reference = ?, "
                     "audit_hash = ?, version = version + 1, updated_at = ? WHERE settlement_id = ?",
                     (payment_reference, _hash_settlement({"settlement_id": settlement_id,
                                                           "status": "CONFIRMED",
                                                           "payment_reference": payment_reference,
                                                           "confirmed_at": now}), now, settlement_id))
        _log_event(conn, settlement_id, s["project_id"], "settlement.confirmed", party.user_id,
                   field="settlement_status", old_val="PENDING", new_val="CONFIRMED")
        _move_token(conn, trail, s["token_id"], {"MATCHED"}, "SETTLED", f"settlement {settlement_id}",
                    extra={"holder_company_id": s["counterparty_buyer_id"]})
        trail.add("settlement.confirmed", "settlement", settlement_id,
                  {"payment_reference": payment_reference, "title_to": s["counterparty_buyer_id"]},
                  s["correlation_id"], s["project_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM settlement_events WHERE settlement_id = ?", (settlement_id,))
    finally:
        conn.close()


# ── the trail, for lineage ──────────────────────────────────────────────────

def trail_for(party: Party, correlation_id: str) -> list[dict]:
    """Every event of one chain, for a party to it (seller, buyer or holder) or GEX."""
    conn = _conn()
    try:
        if not party.is_admin:
            seen = any(party.company_id in (m["seller_company_id"], m["buyer_company_id"])
                       for m in (_match(conn, p) for p in _rows(
                           conn, "SELECT * FROM tb_order WHERE listing_order_id IS NOT NULL AND correlation_id = ?",
                           (correlation_id,))))
            if not seen:
                for t in _rows(conn, "SELECT c.project_id, t.holder_company_id FROM tokens t "
                                     "JOIN capacities c ON c.id = t.capacity_id "
                                     "WHERE t.correlation_id = ?", (correlation_id,)):
                    if party.company_id in (seller_company(t["project_id"]), t["holder_company_id"]):
                        seen = True
                        break
            if not seen:
                _refuse(404, "TRAIL_NOT_FOUND", "No chain of yours with that id.")
    finally:
        conn.close()
    from app.core.event_store import get_compliance_thread

    return get_compliance_thread(correlation_id)
