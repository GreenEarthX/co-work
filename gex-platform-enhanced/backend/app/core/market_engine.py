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
    """The company that owns the project behind a capacity (capacities.id IS a project id)."""
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

    tok = _row(conn, "SELECT lifecycle_state, correlation_id, capacity_id FROM tokens WHERE id = ?",
               (token_id,))
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
              tok["correlation_id"], tok["capacity_id"])


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


def offer_listings(party: Party, molecule: Optional[str] = None) -> list[dict]:
    conn = _conn()
    try:
        sql = ("SELECT o.*, t.capacity_id, t.carbon_intensity_gco2e_mj, t.certification_pathway "
               "FROM offers o JOIN tokens t ON t.id = o.token_id WHERE o.listing_state = 'OPEN'")
        params: list = []
        if molecule:
            sql += " AND o.molecule = ?"
            params.append(molecule)
        out = []
        for r in _rows(conn, sql + " ORDER BY o.created_at DESC", params):
            item = {k: r.get(k) for k in OFFER_LISTING_FIELDS}
            item["carbon_intensity_gco2e_mj"] = r.get("carbon_intensity_gco2e_mj")
            item["certification_pathway"] = r.get("certification_pathway")
            item["mine"] = bool(party.company_id) and seller_company(r["capacity_id"]) == party.company_id
            if item["mine"]:
                item["project_id"] = r["capacity_id"]      # the seller's own; never anyone else's
            out.append(item)
        return out
    finally:
        conn.close()


def rfq_listings(party: Party, molecule: Optional[str] = None) -> list[dict]:
    conn = _conn()
    try:
        sql, params = "SELECT * FROM rfqs WHERE status = 'open'", []
        if molecule:
            sql += " AND molecule = ?"
            params.append(molecule)
        out = []
        for r in _rows(conn, sql + " ORDER BY created_at DESC", params):
            item = {k: r.get(k) for k in RFQ_LISTING_FIELDS}
            item["mine"] = bool(party.company_id) and r["buyer_company_id"] == party.company_id
            out.append(item)
        return out
    finally:
        conn.close()


# ── RFQs ────────────────────────────────────────────────────────────────────

RFQ_TRANSITIONS = {"draft": ("open", "cancelled"), "open": ("withdrawn", "expired")}


def create_rfq(party: Party, *, molecule: str, volume_mtpd: float, delivery_start: str,
               delivery_end: str, max_price_eur_kg: Optional[float] = None,
               location: Optional[str] = None, buyer_contact: Optional[str] = None,
               compliance_requirements: Optional[list] = None, status: str = "open") -> dict:
    _trader(party)
    if status not in ("draft", "open"):
        _refuse(422, "RFQ_STATUS", "A new RFQ is either 'draft' or 'open'.")
    if volume_mtpd <= 0:
        _refuse(422, "RFQ_VOLUME", "Volume must be positive.")
    if delivery_end < delivery_start:
        _refuse(422, "RFQ_WINDOW", "The delivery window ends before it starts.")
    rfq_id = str(uuid.uuid4())
    correlation_id = f"RFQ-{rfq_id[:8]}"
    now = _now()
    conn, trail = _conn(), _Trail(party)
    try:
        conn.execute(
            "INSERT INTO rfqs (id, buyer_company_id, created_by, molecule, volume_mtpd, "
            "max_price_eur_kg, delivery_start, delivery_end, location, buyer_name, buyer_contact, "
            "compliance_requirements, status, correlation_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rfq_id, party.company_id, party.user_id, molecule, volume_mtpd, max_price_eur_kg,
             delivery_start, delivery_end, location, party.company_name, buyer_contact,
             json.dumps(compliance_requirements or []), status, correlation_id, now, now))
        trail.add("rfq.created", "rfq", rfq_id, {"molecule": molecule, "volume_mtpd": volume_mtpd,
                                                 "status": status}, correlation_id)
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
    finally:
        conn.close()


def transition_rfq(party: Party, rfq_id: str, new_status: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        rfq = _row(conn, "SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
        if rfq is None or rfq["buyer_company_id"] != party.company_id:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ of yours with that id.")
        if new_status not in RFQ_TRANSITIONS.get(rfq["status"], ()):
            _refuse(409, "RFQ_TRANSITION", f"An RFQ that is {rfq['status']} cannot become "
                                           f"{new_status}. 'matched' is set by the market.")
        if new_status in ("withdrawn", "expired"):
            _close_pending_matches(conn, trail, "rfq_id", rfq_id, "cancelled")
        conn.execute("UPDATE rfqs SET status = ?, updated_at = ? WHERE id = ?",
                     (new_status, _now(), rfq_id))
        trail.add(f"rfq.{new_status}", "rfq", rfq_id, {"from": rfq["status"], "to": new_status},
                  rfq["correlation_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
    finally:
        conn.close()


def my_rfqs(party: Party) -> list[dict]:
    conn = _conn()
    try:
        return _rows(conn, "SELECT * FROM rfqs WHERE buyer_company_id = ? ORDER BY created_at DESC",
                     (party.company_id,))
    finally:
        conn.close()


# ── offer listings and the token they reserve ───────────────────────────────

def _offer_with_token(conn, offer_id: str) -> dict:
    o = _row(conn, "SELECT o.*, t.capacity_id, t.lifecycle_state AS token_state, "
                   "t.correlation_id AS token_correlation_id "
                   "FROM offers o JOIN tokens t ON t.id = o.token_id WHERE o.id = ?", (offer_id,))
    if o is None:
        _refuse(404, "OFFER_NOT_FOUND", "No offer with that id.")
    return o


def open_offer(party: Party, offer_id: str) -> dict:
    """DRAFT -> OPEN: the listing goes live and reserves its token (MINTED -> RESERVED)."""
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _offer_with_token(conn, offer_id)
        if seller_company(o["capacity_id"]) != party.company_id:
            _refuse(403, "NOT_YOUR_OFFER", "Only the company that owns the project can list its offer.")
        if (o.get("listing_state") or "DRAFT") != "DRAFT":
            _refuse(409, "LISTING_STATE", f"The listing is {o.get('listing_state')}, not DRAFT.")
        other = _row(conn, "SELECT id FROM offers WHERE token_id = ? AND id <> ? AND listing_state IN "
                           "('OPEN','RESERVED','MATCHED')", (o["token_id"], offer_id))
        if other:
            _refuse(409, "TOKEN_ALREADY_LISTED",
                    "This token already backs a live listing. One token is one tradeable lot: "
                    "mint another token to list more volume.")
        conn.execute("UPDATE offers SET listing_state = 'OPEN', status = 'active' WHERE id = ?",
                     (offer_id,))
        _move_token(conn, trail, o["token_id"], {"MINTED"}, "RESERVED", f"listed as offer {offer_id}")
        trail.add("offer.opened", "offer", offer_id, {"token_id": o["token_id"]},
                  o["token_correlation_id"], o["capacity_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM offers WHERE id = ?", (offer_id,))
    finally:
        conn.close()


def withdraw_offer(party: Party, offer_id: str) -> dict:
    """OPEN -> WITHDRAWN: releases the token (RESERVED -> MINTED) and cancels pending matches."""
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _offer_with_token(conn, offer_id)
        if seller_company(o["capacity_id"]) != party.company_id:
            _refuse(403, "NOT_YOUR_OFFER", "Only the company that owns the project can withdraw its offer.")
        state = o.get("listing_state") or "DRAFT"
        if state not in ("DRAFT", "OPEN"):
            _refuse(409, "LISTING_STATE", f"A {state} listing cannot be withdrawn: a match has "
                                          f"been agreed on it.")
        _close_pending_matches(conn, trail, "offer_id", offer_id, "cancelled")
        conn.execute("UPDATE offers SET listing_state = 'WITHDRAWN', status = 'expired' WHERE id = ?",
                     (offer_id,))
        if state == "OPEN":
            _move_token(conn, trail, o["token_id"], {"RESERVED"}, "MINTED",
                        f"listing {offer_id} withdrawn")
        trail.add("offer.withdrawn", "offer", offer_id, {"from": state},
                  o["token_correlation_id"], o["capacity_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM offers WHERE id = ?", (offer_id,))
    finally:
        conn.close()


# ── matches ─────────────────────────────────────────────────────────────────

def _close_pending_matches(conn, trail: _Trail, column: str, value: str, status: str,
                           keep: Optional[str] = None) -> None:
    for m in _rows(conn, f"SELECT id, correlation_id FROM matches WHERE {column} = ? "
                         f"AND status = 'pending'", (value,)):
        if m["id"] == keep:
            continue
        conn.execute("UPDATE matches SET status = ? WHERE id = ?", (status, m["id"]))
        trail.add(f"match.{status}", "match", m["id"], {"because": f"{column} {value}"},
                  m["correlation_id"])


def _score(offer: dict, rfq: dict) -> int:
    from app.api.v1.matching_sqlite import calculate_match_score

    return calculate_match_score(offer, rfq)


def _insert_match(conn, trail: _Trail, party: Party, o: dict, rfq: dict, score: int) -> dict:
    match_id = str(uuid.uuid4())
    seller = seller_company(o["capacity_id"])
    conn.execute(
        "INSERT INTO matches (id, offer_id, rfq_id, match_score, volume_mtpd, price_eur_kg, status, "
        "created_at, project_id, token_id, seller_company_id, buyer_company_id, molecule, "
        "delivery_start, delivery_end, correlation_id, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (match_id, o["id"], rfq["id"], score, min(o["volume_mtpd"], rfq["volume_mtpd"]),
         o["price_eur_kg"], "pending", _now(), o["capacity_id"], o["token_id"], seller,
         rfq["buyer_company_id"], o["molecule"], max(o["delivery_start"], rfq["delivery_start"]),
         min(o["delivery_end"], rfq["delivery_end"]), o["token_correlation_id"], party.user_id))
    trail.add("match.created", "match", match_id,
              {"offer_id": o["id"], "rfq_id": rfq["id"], "score": score,
               "rfq_correlation_id": rfq["correlation_id"]},
              o["token_correlation_id"], o["capacity_id"])
    return {"id": match_id, "score": score}


def _matchable(conn, o: dict, rfq: dict, minimum: int = MIN_MATCH_SCORE) -> Optional[int]:
    """Score if this pair may be matched now, else None."""
    if (o.get("listing_state") != "OPEN" or o.get("token_state") != "RESERVED"
            or rfq["status"] != "open" or o.get("molecule") != rfq.get("molecule")):
        return None
    if seller_company(o["capacity_id"]) == rfq["buyer_company_id"]:
        return None                                    # no self-trade
    if _row(conn, "SELECT id FROM matches WHERE offer_id = ? AND rfq_id = ? AND status IN "
                  "('pending','accepted')", (o["id"], rfq["id"])):
        return None
    score = _score(o, rfq)
    return score if score >= minimum else None


def create_match(party: Party, offer_id: str, rfq_id: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        o = _offer_with_token(conn, offer_id)
        rfq = _row(conn, "SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
        if rfq is None:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ with that id.")
        seller = seller_company(o["capacity_id"])
        if party.company_id not in (seller, rfq["buyer_company_id"]):
            _refuse(403, "NOT_A_PARTY", "You can only match your own offer or your own RFQ.")
        if seller == rfq["buyer_company_id"]:
            _refuse(409, "SELF_TRADE", "A company cannot match its own offer with its own RFQ.")
        # Bilateral (spec decision 2B): the party chose this counterpart itself, so
        # GEX's score is recorded for information but does not gate the choice.
        score = _matchable(conn, o, rfq, minimum=0)
        if score is None:
            _refuse(409, "NOT_MATCHABLE", "This pair cannot be matched: the listing or RFQ is not "
                                          "open, the molecules differ, or a match already exists.")
        made = _insert_match(conn, trail, party, o, rfq, score)
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM matches WHERE id = ?", (made["id"],))
    finally:
        conn.close()


def run_matching(party: Party) -> dict:
    """GEX runs it for the whole market; a company runs it for its own open items.

    SUSPENDED unless MARKET_AUTO_MATCHING (JML, 2026-10-23, spec decision 2B):
    GEX pairing third parties' interests may make it a trading venue, which counsel
    must rule on first. Until then a match is made only by create_match — a party
    choosing a specific counterpart listing — and binds only when both accept.
    """
    from app.core.config import settings

    if not settings.MARKET_AUTO_MATCHING:
        _refuse(409, "AUTO_MATCHING_SUSPENDED",
                "Automated matching is switched off. Choose a listing and propose a match to it; "
                "it binds only when both parties accept.")
    if not party.is_admin:
        _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        offers = _rows(conn, "SELECT o.*, t.capacity_id, t.lifecycle_state AS token_state, "
                             "t.correlation_id AS token_correlation_id FROM offers o "
                             "JOIN tokens t ON t.id = o.token_id WHERE o.listing_state = 'OPEN'")
        rfqs = _rows(conn, "SELECT * FROM rfqs WHERE status = 'open'")
        created = []
        for o in offers:
            seller = seller_company(o["capacity_id"])
            for rfq in rfqs:
                mine = party.is_admin or party.company_id in (seller, rfq["buyer_company_id"])
                if not mine:
                    continue
                score = _matchable(conn, o, rfq)
                if score is not None:
                    created.append(_insert_match(conn, trail, party, o, rfq, score))
        _commit(conn, trail)
        return {"matches_created": len(created), "offers_considered": len(offers),
                "rfqs_considered": len(rfqs)}
    finally:
        conn.close()


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
        rows = _rows(conn, "SELECT m.*, r.buyer_name FROM matches m LEFT JOIN rfqs r ON r.id = m.rfq_id "
                           "WHERE m.seller_company_id = ? OR m.buyer_company_id = ? "
                           "ORDER BY m.created_at DESC", (party.company_id, party.company_id))
        return [{**_reveal(r), "side": "seller" if r["seller_company_id"] == party.company_id else "buyer"}
                for r in rows]
    finally:
        conn.close()


def accept_match(party: Party, match_id: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        m = _row(conn, "SELECT * FROM matches WHERE id = ?", (match_id,))
        if m is None:
            _refuse(404, "MATCH_NOT_FOUND", "No match with that id.")
        side = _side(party, m)
        if m["status"] != "pending":
            _refuse(409, "MATCH_STATE", f"The match is {m['status']}, not pending.")
        if m[f"{side}_accepted_by"]:
            _refuse(409, "ALREADY_ACCEPTED", f"The {side} side has already accepted.")
        now = _now()
        conn.execute(f"UPDATE matches SET {side}_accepted_by = ?, {side}_accepted_at = ? WHERE id = ?",
                     (party.user_id, now, match_id))
        trail.add("match.accepted", "match", match_id, {"side": side}, m["correlation_id"],
                  m["project_id"])
        other = "buyer" if side == "seller" else "seller"
        if m[f"{other}_accepted_by"]:
            o = _offer_with_token(conn, m["offer_id"])
            rfq = _row(conn, "SELECT status FROM rfqs WHERE id = ?", (m["rfq_id"],))
            if o.get("listing_state") != "OPEN" or (rfq or {}).get("status") != "open":
                _refuse(409, "NO_LONGER_AVAILABLE", "The listing or the RFQ is no longer open.")
            conn.execute("UPDATE matches SET status = 'accepted' WHERE id = ?", (match_id,))
            conn.execute("UPDATE offers SET listing_state = 'MATCHED', status = 'matched' WHERE id = ?",
                         (m["offer_id"],))
            conn.execute("UPDATE rfqs SET status = 'matched', updated_at = ? WHERE id = ?",
                         (now, m["rfq_id"]))
            _close_pending_matches(conn, trail, "offer_id", m["offer_id"], "superseded", keep=match_id)
            _close_pending_matches(conn, trail, "rfq_id", m["rfq_id"], "superseded", keep=match_id)
            _move_token(conn, trail, m["token_id"], {"RESERVED"}, "MATCHED", f"match {match_id} agreed")
            trail.add("match.agreed", "match", match_id, {"offer_id": m["offer_id"],
                                                          "rfq_id": m["rfq_id"]},
                      m["correlation_id"], m["project_id"])
        _commit(conn, trail)
        return _reveal(_row(conn, "SELECT * FROM matches WHERE id = ?", (match_id,)))
    finally:
        conn.close()


def decline_match(party: Party, match_id: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        m = _row(conn, "SELECT * FROM matches WHERE id = ?", (match_id,))
        if m is None:
            _refuse(404, "MATCH_NOT_FOUND", "No match with that id.")
        side = _side(party, m)
        if m["status"] != "pending":
            _refuse(409, "MATCH_STATE", f"The match is {m['status']}, not pending.")
        conn.execute("UPDATE matches SET status = 'declined' WHERE id = ?", (match_id,))
        trail.add("match.declined", "match", match_id, {"side": side}, m["correlation_id"],
                  m["project_id"])
        _commit(conn, trail)
        return _reveal(_row(conn, "SELECT * FROM matches WHERE id = ?", (match_id,)))
    finally:
        conn.close()


# ── contracts ───────────────────────────────────────────────────────────────

def create_contract(party: Party, match_id: str, *, delivery_terms: str, payment_terms: str) -> dict:
    _trader(party)
    conn, trail = _conn(), _Trail(party)
    try:
        m = _row(conn, "SELECT m.*, r.buyer_name FROM matches m LEFT JOIN rfqs r ON r.id = m.rfq_id "
                       "WHERE m.id = ?", (match_id,))
        if m is None:
            _refuse(404, "MATCH_NOT_FOUND", "No match with that id.")
        _side(party, m)
        if m["status"] != "accepted":
            _refuse(409, "MATCH_NOT_AGREED", "A contract needs a match both parties have accepted.")
        if _row(conn, "SELECT id FROM contracts WHERE match_id = ?", (match_id,)):
            _refuse(409, "CONTRACT_EXISTS", "This match already has its contract.")
        try:
            start = datetime.strptime(m["delivery_start"][:10], "%Y-%m-%d")
            end = datetime.strptime(m["delivery_end"][:10], "%Y-%m-%d")
            tenor = max(0, int((end - start).days / 365.25))
        except (TypeError, ValueError):
            tenor = None
        contract_id, now = str(uuid.uuid4()), _now()
        conn.execute(
            "INSERT INTO contracts (id, project_id, match_id, offer_id, rfq_id, token_id, "
            "seller_company_id, buyer_company_id, contract_id_external, counterparty, molecule, "
            "volume_mtpd, price_eur_kg, pricing_basis, delivery_terms, payment_terms, start_date, "
            "end_date, tenor_years, status, correlation_id, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (contract_id, m["project_id"], match_id, m["offer_id"], m["rfq_id"], m["token_id"],
             m["seller_company_id"], m["buyer_company_id"], f"CONT-{contract_id[:8].upper()}",
             m.get("buyer_name") or m["buyer_company_id"], m["molecule"], m["volume_mtpd"],
             m["price_eur_kg"], f"{delivery_terms} | {payment_terms}", delivery_terms, payment_terms,
             m["delivery_start"], m["delivery_end"], tenor, "active", m["correlation_id"],
             party.user_id, now, now))
        trail.add("contract.created", "contract", contract_id,
                  {"match_id": match_id, "token_id": m["token_id"]}, m["correlation_id"], m["project_id"])
        _commit(conn, trail)
        return _row(conn, "SELECT * FROM contracts WHERE id = ?", (contract_id,))
    finally:
        conn.close()


def my_contracts(party: Party) -> list[dict]:
    conn = _conn()
    try:
        return _rows(conn, "SELECT * FROM contracts WHERE seller_company_id = ? OR buyer_company_id = ? "
                           "ORDER BY created_at DESC", (party.company_id, party.company_id))
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
        c = _row(conn, "SELECT * FROM contracts WHERE id = ?", (contract_id,))
        if c is None or party.company_id not in (c["seller_company_id"], c["buyer_company_id"]):
            _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
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
        conn.execute("UPDATE offers SET listing_state = 'SETTLED' WHERE token_id = ? AND listing_state = 'MATCHED'",
                     (s["token_id"],))
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
            seen = _row(conn, "SELECT 1 AS ok FROM matches WHERE correlation_id = ? AND "
                              "(seller_company_id = ? OR buyer_company_id = ?)",
                        (correlation_id, party.company_id, party.company_id))
            if not seen:
                for t in _rows(conn, "SELECT capacity_id, holder_company_id FROM tokens "
                                     "WHERE correlation_id = ?", (correlation_id,)):
                    if party.company_id in (seller_company(t["capacity_id"]), t["holder_company_id"]):
                        seen = {"ok": 1}
                        break
            if not seen:
                _refuse(404, "TRAIL_NOT_FOUND", "No chain of yours with that id.")
    finally:
        conn.close()
    from app.core.event_store import get_compliance_thread

    return get_compliance_thread(correlation_id)
