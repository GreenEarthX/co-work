"""
Order book — orders, RFQs and quotes on the one contract model (spec §5, §9; M3).

docs/CONTRACT_RECORD_PHASE0.md, JML's decisions of 2026-11-06:

* Q6 — a proposal is an INVITED FIRM QUOTE: a tb_order answering an RFQ, on the
  proposer's side, invited only to the requester. Making it is the proposer's
  acceptance (tb_order_event records who and when). The other party's
  acceptance completes the trade in ONE transaction: the order row is locked
  (SELECT … FOR UPDATE), status, validity, all-or-nothing, minimum fill and
  restricted pairs are checked, the terms are cloned with payer and receiver
  resolved by the side convention, frozen and hashed, and the fill and the
  draft contract (v1, pending_confirmation, UNVERIFIED) are created. Two
  simultaneous accepts make exactly one fill (T14).
* Q7 — TRADE_CONFIRM: each party confirms with four eyes inside its own
  company (core/wae.py); both confirmed moves the contract to `confirmed`. A
  confirmed `trade` contract is a commercial record: it never reaches the gate
  engine (Phases 1–2).
* Q5 — GEX staff read a contract's state, chain and hashes, never its terms.

The acceptor of an order has no order of its own yet, and tb_fill joins a buy
order to a sell order (D3: orders are one-sided). Acceptance therefore records
the acceptor's side as a mirror order — opposite side, private, the same
one-sided terms, status `filled` — so the fill names both commitments.

Every cross-company step runs on the market operator connection (PLATFORM_ADMIN)
after authorising the Party, as core/market_engine does; GEX trades nothing.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse, _trader
from app.trading_book import canonical, conventions as cv, record, validation
from app.trading_book.record import RecordRefused
from app.trading_book.terms import TermsIn

QTY = Decimal("0.000001")


def _conn():
    return me._conn()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(conn, sql, params=()):
    return record._row(conn, sql, params)


def _rows(conn, sql, params=()):
    return record._rows(conn, sql, params)


def _guard(fn):
    """RecordRefused (the record's own refusals) answer like the market's."""
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RecordRefused as exc:
            _refuse(exc.status, exc.code, exc.message)
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run


def _ctx(conn) -> validation.Context:
    pairs = {frozenset({str(r["counterparty_id"]), str(r["restricted_counterparty_id"])}) for r in _rows(
        conn, "SELECT counterparty_id, restricted_counterparty_id FROM tb_counterparty_restriction WHERE active")}
    # unit_basis is a price basis ("EUR/MWh"): the unit a flow is quoted in is its last part.
    indices = {str(r["id"]): validation.IndexInfo(currency=r["currency"], unit=(r["unit_basis"] or "").split("/")[-1])
               for r in _rows(conn, "SELECT id, currency, unit_basis FROM tb_index_definition")}
    return validation.Context(indices=indices, restricted_pairs=pairs)


def _validate(conn, terms: TermsIn, kind: str) -> None:
    failed = validation.validate(terms, kind, _ctx(conn))
    if failed:
        _refuse(422, "TERMS_INVALID", "The terms break rules " + ", ".join(failed) + ".")


def validate_terms(terms: TermsIn, kind: str = "order") -> list[str]:
    conn = _conn()
    try:
        return validation.validate(terms, kind, _ctx(conn))
    finally:
        conn.close()


def _event(conn, order_id: str, from_status: Optional[str], to_status: str, actor: str, reason: str) -> None:
    conn.execute("INSERT INTO tb_order_event (order_id, from_status, to_status, actor_id, reason) "
                 "VALUES (?, ?, ?, ?, ?)", (order_id, from_status, to_status, actor, reason))


def _restricted(conn, a: str, b: str) -> bool:
    return bool(_row(conn, "SELECT 1 AS x FROM tb_counterparty_restriction WHERE active AND ("
                           "(counterparty_id = ? AND restricted_counterparty_id = ?) OR "
                           "(counterparty_id = ? AND restricted_counterparty_id = ?))", (a, b, b, a)))


def _product_total(terms: TermsIn) -> Decimal:
    return sum((f.quantity for leg in terms.legs for f in leg.flows
                if f.flow_type == cv.FlowType.PHYSICAL), Decimal(0))


def _order_view(conn, o: dict, party: Party) -> dict:
    owner = record.company_of_counterparty(conn, o["owner_id"])
    mine = owner == party.company_id
    out = {k: (str(o[k]) if isinstance(o[k], uuid.UUID) else o[k]) for k in (
        "id", "side", "order_type", "all_or_nothing", "min_fill_quantity", "valid_from", "valid_until",
        "status", "rfq_id", "visibility")}
    out["mine"] = mine
    if mine:
        out["owner_company_id"] = owner
    out["terms"] = canonical.canonical_dict(record.load_terms(conn, str(o["terms_id"])))
    return out


# ── orders ──────────────────────────────────────────────────────────────────

def _insert_order(conn, party: Party, terms: TermsIn, *, side: str, order_type: str, all_or_nothing: bool,
                  min_fill_quantity: Optional[Decimal], valid_until: datetime, visibility: str,
                  invitees: list[str], rfq_id: Optional[str] = None, status: str = "draft",
                  reason: str = "created") -> str:
    owner_cp = record.counterparty_for(conn, party.company_id)
    w = record.write_terms(conn, terms, party.company_id, freeze=status != "draft")
    order_id = str(uuid.uuid4())
    conn.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, order_type, all_or_nothing, min_fill_quantity, "
                 "valid_until, status, rfq_id, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (order_id, owner_cp, side, w["terms_id"], order_type, all_or_nothing, min_fill_quantity,
                  valid_until, status, rfq_id, visibility))
    for company in invitees:
        if company == party.company_id:
            _refuse(422, "SELF_INVITE", "An order is not offered to its own owner.")
        conn.execute("INSERT INTO tb_order_invitee (order_id, counterparty_id) VALUES (?, ?)",
                     (order_id, record.counterparty_for(conn, company)))
    _event(conn, order_id, None, status, party.user_id, reason)
    return order_id


@_guard
def create_order(party: Party, terms: TermsIn, *, side: str, order_type: str = "firm",
                 all_or_nothing: bool = False, min_fill_quantity: Optional[Decimal] = None,
                 valid_until: datetime, visibility: str = "platform", invitees: list[str] = ()) -> dict:
    _trader(party)
    conn = _conn()
    try:
        _validate(conn, terms, "order")
        if visibility == "invited" and not invitees:
            _refuse(422, "INVITEES_REQUIRED", "An invited order names who may accept it.")
        order_id = _insert_order(conn, party, terms, side=side, order_type=order_type,
                                 all_or_nothing=all_or_nothing, min_fill_quantity=min_fill_quantity,
                                 valid_until=valid_until, visibility=visibility, invitees=list(invitees))
        conn.commit()
        return _order_view(conn, _row(conn, "SELECT * FROM tb_order WHERE id = ?", (order_id,)), party)
    finally:
        conn.close()


def _own_order(conn, party: Party, order_id: str, lock: bool = False) -> dict:
    o = _row(conn, "SELECT * FROM tb_order WHERE id = ?" + (" FOR UPDATE" if lock else ""), (order_id,))
    if o is None or record.company_of_counterparty(conn, o["owner_id"]) != party.company_id:
        _refuse(404, "ORDER_NOT_FOUND", "No order of yours with that id.")
    return o


@_guard
def open_order(party: Party, order_id: str) -> dict:
    """draft -> open: the terms freeze (spec §5) and the order can be accepted."""
    _trader(party)
    conn = _conn()
    try:
        o = _own_order(conn, party, order_id, lock=True)
        if o["status"] != "draft":
            _refuse(409, "ORDER_STATE", f"The order is {o['status']}, not draft.")
        _validate(conn, record.load_terms(conn, str(o["terms_id"])), "order")
        record.freeze(conn, str(o["terms_id"]))
        conn.execute("UPDATE tb_order SET status = 'open', updated_at = now() WHERE id = ?", (order_id,))
        _event(conn, order_id, "draft", "open", party.user_id, "opened")
        conn.commit()
        return _order_view(conn, _row(conn, "SELECT * FROM tb_order WHERE id = ?", (order_id,)), party)
    finally:
        conn.close()


@_guard
def cancel_order(party: Party, order_id: str) -> dict:
    _trader(party)
    conn = _conn()
    try:
        o = _own_order(conn, party, order_id, lock=True)
        if o["status"] not in ("draft", "open", "partially_filled"):
            _refuse(409, "ORDER_STATE", f"A {o['status']} order cannot be cancelled.")
        conn.execute("UPDATE tb_order SET status = 'cancelled', updated_at = now() WHERE id = ?", (order_id,))
        _event(conn, order_id, o["status"], "cancelled", party.user_id, "cancelled by its owner")
        conn.commit()
        return _order_view(conn, _row(conn, "SELECT * FROM tb_order WHERE id = ?", (order_id,)), party)
    finally:
        conn.close()


def list_orders(party: Party) -> list[dict]:
    """My orders, orders offered to me, and open platform orders (anonymised: no owner)."""
    conn = _conn()
    try:
        me_cp = _row(conn, "SELECT id FROM tb_counterparty WHERE company_id = ?", (party.company_id,))
        rows = _rows(conn, "SELECT * FROM tb_order ORDER BY created_at DESC")
        out = []
        for o in rows:
            owner = record.company_of_counterparty(conn, o["owner_id"])
            invited = bool(me_cp) and bool(_row(conn, "SELECT 1 AS x FROM tb_order_invitee WHERE order_id = ? "
                                                      "AND counterparty_id = ?", (str(o["id"]), str(me_cp["id"]))))
            public = o["visibility"] == "platform" and o["status"] in ("open", "partially_filled")
            if owner == party.company_id or invited or public:
                out.append(_order_view(conn, o, party))
        return out
    finally:
        conn.close()


def _scaled(terms: TermsIn, factor: Decimal) -> TermsIn:
    if factor == 1:
        return terms
    data = terms.model_dump()
    for leg in data["legs"]:
        for f in leg["flows"]:
            f["quantity"] = (f["quantity"] * factor).quantize(QTY)
    return TermsIn.model_validate(data)


def _with_parties(terms: TermsIn, buyer: str, seller: str) -> TermsIn:
    data = terms.model_dump()
    for leg in data["legs"]:
        leg["payer"], leg["receiver"] = cv.resolve(leg["leg_role"], buyer, seller)
    return TermsIn.model_validate(data)


def _project_of(conn, terms: TermsIn) -> Optional[str]:
    assets = {f.asset_id for leg in terms.legs for f in leg.flows if f.asset_id}
    projects = {r["project_id"] for a in assets for r in _rows(conn, "SELECT project_id FROM tb_asset WHERE id = ?", (a,))}
    return projects.pop() if len(projects) == 1 else None


def _accept(conn, party: Party, order_id: str, quantity: Optional[Decimal], *, quote_of: Optional[dict] = None,
            origin_ref: Optional[str] = None, project_id: Optional[str] = None,
            correlation_id: Optional[str] = None, token_ids=(), note: Optional[str] = None) -> dict:
    """The acceptance (Q6), in the caller's transaction. The market passes the extras
    of an agreed match: its origin ('match:<proposal>'), project, trail and token."""
    o = _row(conn, "SELECT * FROM tb_order WHERE id = ? FOR UPDATE", (order_id,))
    if o is None:
        _refuse(404, "ORDER_NOT_FOUND", "No order with that id.")
    owner_company = record.company_of_counterparty(conn, o["owner_id"])
    acceptor_cp = record.counterparty_for(conn, party.company_id)
    invited = bool(_row(conn, "SELECT 1 AS x FROM tb_order_invitee WHERE order_id = ? AND counterparty_id = ?",
                        (order_id, acceptor_cp)))
    if o["visibility"] == "private" or (o["visibility"] == "invited" and not invited):
        _refuse(404, "ORDER_NOT_FOUND", "No order with that id is offered to you.")
    if owner_company == party.company_id:
        _refuse(409, "SELF_TRADE", "A company cannot accept its own order.")
    if o["status"] not in ("open", "partially_filled"):
        _refuse(409, "ORDER_STATE", f"The order is {o['status']}; only an open order can be accepted.")
    if o["order_type"] != "firm":
        _refuse(409, "INDICATIVE_ORDER", "An indicative order cannot be accepted.")
    now = _now()
    if not (o["valid_from"] <= now < o["valid_until"]):
        _refuse(409, "ORDER_EXPIRED", "The order is outside its validity.")
    if _restricted(conn, str(o["owner_id"]), acceptor_cp):
        _refuse(409, "RESTRICTED_COUNTERPARTY", "These two counterparties may not trade with each other.")
    terms = record.load_terms(conn, str(o["terms_id"]))
    total = _product_total(terms)
    filled = _row(conn, "SELECT coalesce(sum(quantity), 0) AS q FROM tb_fill WHERE buy_order_id = ? OR "
                        "sell_order_id = ?", (order_id, order_id))["q"]
    remaining = total - Decimal(filled)
    q = Decimal(quantity) if quantity is not None else remaining
    if q <= 0 or q > remaining:
        _refuse(409, "QUANTITY", f"{remaining} remains on this order; {q} cannot be filled.")
    if o["all_or_nothing"] and q != total:
        _refuse(409, "ALL_OR_NOTHING", "This order is all-or-nothing: accept its whole quantity.")
    if o["min_fill_quantity"] is not None and q < o["min_fill_quantity"] and q != remaining:
        _refuse(409, "BELOW_MIN_FILL", f"The minimum fill is {o['min_fill_quantity']}.")
    buyer, seller = cv.parties_at_acceptance(o["side"], str(o["owner_id"]), acceptor_cp)
    share = _scaled(terms, q / total)
    contract_terms = _with_parties(share, buyer, seller)
    _validate(conn, contract_terms, "contract")
    mirror_side = cv.opposite(cv.Side(o["side"])).value
    mirror = _insert_order(conn, party, share, side=mirror_side, order_type="firm", all_or_nothing=False,
                           min_fill_quantity=None, valid_until=o["valid_until"], visibility="private",
                           invitees=[], status="filled", reason=f"acceptance of order {order_id}")
    buy, sell = (order_id, mirror) if o["side"] == "buy" else (mirror, order_id)
    fill_id = str(uuid.uuid4())
    conn.execute("INSERT INTO tb_fill (id, buy_order_id, sell_order_id, quantity) VALUES (?, ?, ?, ?)",
                 (fill_id, buy, sell, q))
    seller_company = record.company_of_counterparty(conn, seller)
    made = record.create_contract(
        conn, terms=contract_terms, owner_company_id=seller_company, kind="trade",
        project_id=project_id or _project_of(conn, contract_terms), origin_ref=origin_ref or f"fill:{fill_id}",
        correlation_id=correlation_id, actor=party.user_id, company_id=party.company_id,
        note=note or (f"order {order_id} accepted" + (f" (quote on RFQ {quote_of['id']})" if quote_of else "")),
        fill_id=fill_id, token_ids=token_ids)
    conn.execute("UPDATE tb_fill SET contract_id = ? WHERE id = ?", (made["id"], fill_id))
    new_status = "filled" if q == remaining else "partially_filled"
    conn.execute("UPDATE tb_order SET status = ?, updated_at = now() WHERE id = ?", (new_status, order_id))
    _event(conn, order_id, o["status"], new_status, party.user_id, f"accepted: fill {fill_id}")
    return {"fill_id": fill_id, "quantity": str(q), "contract_id": made["id"], "contract_ref": made["contract_ref"],
            "terms_hash": made["terms_hash"]}


@_guard
def accept_order(party: Party, order_id: str, quantity: Optional[Decimal] = None) -> dict:
    _trader(party)
    conn = _conn()
    try:
        result = _accept(conn, party, order_id, quantity)
        conn.commit()
        return result
    finally:
        conn.close()


# ── RFQs and quotes ─────────────────────────────────────────────────────────

@_guard
def create_rfq(party: Party, terms: TermsIn, *, side: str, valid_until: datetime) -> dict:
    """Indicative terms, frozen when published."""
    _trader(party)
    conn = _conn()
    try:
        _validate(conn, terms, "order")
        w = record.write_terms(conn, terms, party.company_id, freeze=False)
        rfq_id = str(uuid.uuid4())
        conn.execute("INSERT INTO tb_rfq (id, requester_id, side, terms_id, valid_until, status) "
                     "VALUES (?, ?, ?, ?, ?, 'draft')",
                     (rfq_id, record.counterparty_for(conn, party.company_id), side, w["terms_id"], valid_until))
        conn.commit()
        return _rfq_view(conn, _row(conn, "SELECT * FROM tb_rfq WHERE id = ?", (rfq_id,)), party)
    finally:
        conn.close()


def _rfq_view(conn, r: dict, party: Party) -> dict:
    requester = record.company_of_counterparty(conn, r["requester_id"])
    out = {"id": str(r["id"]), "side": r["side"], "valid_until": r["valid_until"], "status": r["status"],
           "mine": requester == party.company_id,
           "terms": canonical.canonical_dict(record.load_terms(conn, str(r["terms_id"])))}
    if out["mine"]:
        out["requester_company_id"] = requester
    return out


@_guard
def publish_rfq(party: Party, rfq_id: str) -> dict:
    _trader(party)
    conn = _conn()
    try:
        r = _row(conn, "SELECT * FROM tb_rfq WHERE id = ? FOR UPDATE", (rfq_id,))
        if r is None or record.company_of_counterparty(conn, r["requester_id"]) != party.company_id:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ of yours with that id.")
        if r["status"] != "draft":
            _refuse(409, "RFQ_STATE", f"The RFQ is {r['status']}, not draft.")
        record.freeze(conn, str(r["terms_id"]))
        conn.execute("UPDATE tb_rfq SET status = 'published', updated_at = now() WHERE id = ?", (rfq_id,))
        conn.commit()
        return _rfq_view(conn, _row(conn, "SELECT * FROM tb_rfq WHERE id = ?", (rfq_id,)), party)
    finally:
        conn.close()


def list_rfqs(party: Party) -> list[dict]:
    """My RFQs and every published one (anonymised: no requester)."""
    conn = _conn()
    try:
        out = []
        for r in _rows(conn, "SELECT * FROM tb_rfq ORDER BY created_at DESC"):
            mine = record.company_of_counterparty(conn, r["requester_id"]) == party.company_id
            if mine or r["status"] == "published":
                out.append(_rfq_view(conn, r, party))
        return out
    finally:
        conn.close()


@_guard
def quote(party: Party, rfq_id: str, terms: TermsIn, *, valid_until: datetime) -> dict:
    """Q6: an invited firm quote. Creating it is the quoting party's acceptance."""
    _trader(party)
    conn = _conn()
    try:
        r = _row(conn, "SELECT * FROM tb_rfq WHERE id = ? FOR UPDATE", (rfq_id,))
        if r is None or r["status"] != "published":
            _refuse(404, "RFQ_NOT_FOUND", "No published RFQ with that id.")
        requester = record.company_of_counterparty(conn, r["requester_id"])
        if requester == party.company_id:
            _refuse(409, "SELF_TRADE", "A company does not quote on its own RFQ.")
        _validate(conn, terms, "order")
        side = cv.opposite(cv.Side(r["side"])).value
        order_id = _insert_order(conn, party, terms, side=side, order_type="firm", all_or_nothing=True,
                                 min_fill_quantity=None, valid_until=min(valid_until, r["valid_until"]),
                                 visibility="invited", invitees=[requester], rfq_id=rfq_id, status="open",
                                 reason=f"quote on RFQ {rfq_id}: the quoting party's acceptance")
        conn.commit()
        return _order_view(conn, _row(conn, "SELECT * FROM tb_order WHERE id = ?", (order_id,)), party)
    finally:
        conn.close()


@_guard
def accept_quote(party: Party, rfq_id: str, order_id: str) -> dict:
    """The requester accepts one quote: fill + draft contract, the RFQ closes and
    its other quotes are cancelled — one transaction."""
    _trader(party)
    conn = _conn()
    try:
        r = _row(conn, "SELECT * FROM tb_rfq WHERE id = ? FOR UPDATE", (rfq_id,))
        if r is None or record.company_of_counterparty(conn, r["requester_id"]) != party.company_id:
            _refuse(404, "RFQ_NOT_FOUND", "No RFQ of yours with that id.")
        if r["status"] != "published":
            _refuse(409, "RFQ_STATE", f"The RFQ is {r['status']}, not published.")
        q = _row(conn, "SELECT * FROM tb_order WHERE id = ? AND rfq_id = ?", (order_id, rfq_id))
        if q is None:
            _refuse(404, "QUOTE_NOT_FOUND", "No quote with that id on this RFQ.")
        result = _accept(conn, party, order_id, None, quote_of={"id": rfq_id})
        conn.execute("UPDATE tb_rfq SET status = 'closed', updated_at = now() WHERE id = ?", (rfq_id,))
        for other in _rows(conn, "SELECT id, status FROM tb_order WHERE rfq_id = ? AND id <> ? AND status = 'open'",
                           (rfq_id, order_id)):
            conn.execute("UPDATE tb_order SET status = 'cancelled', updated_at = now() WHERE id = ?", (str(other["id"]),))
            _event(conn, str(other["id"]), "open", "cancelled", party.user_id, f"superseded by quote {order_id}")
        conn.commit()
        return result
    finally:
        conn.close()


# ── contract records ────────────────────────────────────────────────────────

def _contract_for(conn, party: Party, contract_id: str) -> tuple[dict, dict]:
    c = _row(conn, "SELECT * FROM tb_contract WHERE id = ? AND contract_type = 'terms'", (contract_id,))
    who = record.parties(conn, contract_id) if c else {"companies": set()}
    if c is None or not (party.is_admin or party.company_id in who["companies"]):
        _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
    return c, who


def get_contract(party: Party, contract_id: str) -> dict:
    """The record: versions, the event chain and whether it holds. A party also
    reads the terms; GEX staff read state, chain and hashes only (Q5, R0P)."""
    conn = _conn()
    try:
        c, who = _contract_for(conn, party, contract_id)
        versions = _rows(conn, "SELECT version, terms_id, terms_hash, valid_from, superseded_at, reason, "
                               "token_event_ref FROM tb_contract_version WHERE contract_id = ? ORDER BY version",
                         (contract_id,))
        evs = [{k: e[k] for k in ("seq", "event_type", "version", "sub_leg_seq", "terms_hash", "actor",
                                  "company_id", "note", "at", "prev_hash", "event_hash", "hash_scheme")}
               for e in record.events(conn, contract_id)]
        out = {"id": str(c["id"]), "contract_ref": c["contract_ref"], "kind": c["kind"],
               "trade_status": c["trade_status"], "verification_state": c["verification_state"],
               "token_ref": c["token_ref"], "chain_intact": record.chain_intact(conn, contract_id),
               "terms_hold": all(record.stored_hashes_hold(conn, str(v["terms_id"])) for v in versions),
               "versions": [{k: v[k] for k in v if k != "terms_id"} for v in versions], "events": evs,
               "confirmed_by": sorted(_confirmed_companies(conn, contract_id))}
        if not party.is_admin:
            out["parties"] = {"seller": who["seller"], "buyers": who["buyers"]}
            out["project_id"] = c["project_id"]
            current = record.current_version(conn, contract_id)
            out["terms"] = canonical.canonical_dict(record.load_terms(conn, str(current["terms_id"])))
        return out
    finally:
        conn.close()


def _confirmed_companies(conn, contract_id: str) -> set[str]:
    """Companies whose CONFIRMED event names the CURRENT version's hash and has
    no DISPUTED after it."""
    v = record.current_version(conn, contract_id)
    done: set[str] = set()
    for e in record.events(conn, contract_id):
        if e["event_type"] == "CONFIRMED" and v and e["terms_hash"] == v["terms_hash"]:
            done.add(e["company_id"])
        elif e["event_type"] == "DISPUTED":
            done.discard(e["company_id"])
    return done


@_guard
def request_confirmation(party: Party, contract_id: str) -> dict:
    """The first pair of eyes: raise this party's TRADE_CONFIRM (core/wae.py)."""
    from app.core import wae

    _trader(party)
    conn = _conn()
    try:
        c, who = _contract_for(conn, party, contract_id)
        if c["trade_status"] != "pending_confirmation":
            _refuse(409, "CONTRACT_STATE", f"The contract is {c['trade_status']}, not pending confirmation.")
        if party.company_id in _confirmed_companies(conn, contract_id):
            _refuse(409, "ALREADY_CONFIRMED", "Your company has already confirmed this version.")
        v = record.current_version(conn, contract_id)
    finally:
        conn.close()
    initiator = wae._account(party.user_id)
    if not initiator or initiator.get("account_state") != "ACTIVE" or initiator.get("company_id") != party.company_id:
        _refuse(403, "ACCOUNT_NOT_ACTIVE", "Only an active account of a party raises its confirmation.")
    decision = wae.evaluate_authorization(
        initiator_user_id=party.user_id, action_type=wae.TRADE_CONFIRM, resource_id=contract_id,
        project_id=c["project_id"], company_id=None,
        payload={"party_company_id": party.company_id, "contract_ref": c["contract_ref"],
                 "version": v["version"], "terms_hash": v["terms_hash"]})
    return {"request_id": decision.request_id, "outcome": decision.outcome.value,
            "terms_hash": v["terms_hash"], "needs": "a second active account of your company; one of you an executive"}


@_guard
def approve_confirmation(party: Party, contract_id: str, request_id: str) -> dict:
    """The second pair of eyes. On quorum the party's CONFIRMED is written on the
    chain; when the seller and every buyer have confirmed the current version,
    the contract is `confirmed`. Idempotent after quorum: a CONFIRMED that could
    not be written is written on the next call."""
    from app.core import wae
    from app.core.db_backend import PLATFORM_ADMIN

    _trader(party)
    req = wae.get_request(request_id, company_id=PLATFORM_ADMIN)
    if (req is None or req.get("action_type") != wae.TRADE_CONFIRM or req.get("resource_id") != contract_id
            or req["payload_json"].get("party_company_id") != party.company_id):
        _refuse(404, "CONFIRMATION_NOT_FOUND", "No confirmation of yours with that id on this contract.")
    conn = _conn()
    try:
        c, who = _contract_for(conn, party, contract_id)
        v = record.current_version(conn, contract_id)
        if req["payload_json"].get("terms_hash") != v["terms_hash"]:
            _refuse(409, "NOT_THE_LATEST_VERSION", "The terms changed after this confirmation was raised.")
    finally:
        conn.close()
    if req["status"] == "PENDING":
        result = wae.record_decision(request_id, party.user_id, wae.ApprovalDecision.APPROVE,
                                     reason_text="TRADE_CONFIRM second approval")
        if "error" in result:
            code = result.get("code") or "CONFIRMATION_REFUSED"
            _refuse(409 if code == "ALREADY_DECIDED" else 403, code, result["error"])
        if not result["quorum_reached"]:
            return {"request_id": request_id, "quorum_reached": False}
    elif req["status"] != "APPROVED":
        _refuse(409, "CONFIRMATION_STATE", f"This confirmation is {req['status']}.")
    conn = _conn()
    try:
        c = _row(conn, "SELECT * FROM tb_contract WHERE id = ? FOR UPDATE", (contract_id,))
        note = f"TRADE_CONFIRM {request_id}"
        if not _row(conn, "SELECT 1 AS x FROM tb_contract_event WHERE contract_id = ? AND event_type = 'CONFIRMED' "
                          "AND note = ?", (contract_id, note)):
            record.append_event(conn, contract_id, "CONFIRMED", party.user_id, party.company_id,
                                version_id=str(v["id"]), terms_hash=v["terms_hash"], note=note)
        status = c["trade_status"]
        if status == "pending_confirmation" and who["companies"] <= _confirmed_companies(conn, contract_id):
            conn.execute("UPDATE tb_contract SET trade_status = 'confirmed', updated_at = now() WHERE id = ?",
                         (contract_id,))
            record.append_event(conn, contract_id, "STATUS_CHANGED", party.user_id, party.company_id,
                                version_id=str(v["id"]), note="pending_confirmation -> confirmed: every party confirmed")
            status = "confirmed"
        conn.commit()
        return {"request_id": request_id, "quorum_reached": True, "trade_status": status,
                "confirmed_by": sorted(_confirmed_companies(conn, contract_id))}
    finally:
        conn.close()


def confirmations(party: Party, contract_id: str) -> list[dict]:
    """This party's TRADE_CONFIRM requests on the contract (GEX: none — it never confirms)."""
    from app.core import wae
    from app.core.db_backend import PLATFORM_ADMIN, governance_connection

    conn = _conn()
    try:
        _contract_for(conn, party, contract_id)
    finally:
        conn.close()
    gov = governance_connection(company_id=PLATFORM_ADMIN)
    try:
        rows = [dict(r) for r in gov.execute(
            "SELECT id, initiator_user_id, status, created_at, payload_json FROM approval_requests "
            "WHERE action_type = ? AND resource_id = ? ORDER BY created_at", (wae.TRADE_CONFIRM, contract_id)).fetchall()]
    finally:
        gov.close()
    out = []
    for r in rows:
        payload = json.loads(r.pop("payload_json") or "{}")
        if payload.get("party_company_id") == party.company_id:
            out.append({**r, "version": payload.get("version"), "terms_hash": payload.get("terms_hash")})
    return out


# The contract lifecycle (spec §5) after confirmation. `pending_confirmation ->
# confirmed` is NOT here: only TRADE_CONFIRM by every party reaches it.
STATUS_TRANSITIONS = {
    "pending_confirmation": ("cancelled",),
    "confirmed": ("active",),
    "active": ("completed", "terminated"),
}


@_guard
def change_status(party: Party, contract_id: str, new_status: str, note: Optional[str] = None) -> dict:
    _trader(party)
    conn = _conn()
    try:
        _contract_for(conn, party, contract_id)
        c = _row(conn, "SELECT * FROM tb_contract WHERE id = ? FOR UPDATE", (contract_id,))
        current = c["trade_status"]
        if new_status == "confirmed":
            _refuse(409, "CONFIRM_WITH_TRADE_CONFIRM", "A contract is confirmed by every party's TRADE_CONFIRM.")
        if new_status not in STATUS_TRANSITIONS.get(current, ()):
            _refuse(409, "CONTRACT_STATE", f"A {current} contract cannot become {new_status}.")
        conn.execute("UPDATE tb_contract SET trade_status = ?, updated_at = now() WHERE id = ?", (new_status, contract_id))
        v = record.current_version(conn, contract_id)
        ev = record.append_event(conn, contract_id, "STATUS_CHANGED", party.user_id, party.company_id,
                                 version_id=str(v["id"]), note=f"{current} -> {new_status}" + (f": {note}" if note else ""))
        conn.commit()
        return {"contract_id": contract_id, "old_status": current, "new_status": new_status, "event": ev}
    finally:
        conn.close()


def contract_cashflows(party: Party, contract_id: str, as_party: Optional[str] = None) -> dict:
    """Every flow of the contract's current version, priced (spec §7, M4), with payer
    and receiver; signed from `as_party`'s side (default: the caller's company). A
    party reads its own contracts; GEX staff read no amounts (Q5: no terms)."""
    from app.trading_book import flows

    if party.is_admin:
        _refuse(403, "GEX_READS_NO_TERMS", "GEX staff read a contract's state and hashes, not its amounts.")
    conn = _conn()
    try:
        _, who = _contract_for(conn, party, contract_id)
        side = as_party or party.company_id
        if side not in who["companies"]:
            _refuse(422, "NOT_A_PARTY", "as_party must be a party to the contract.")
        lines = flows.contract_lines(conn, contract_id, as_party=side)
        return {"contract_id": contract_id, "as_party": side,
                "lines": [line.model_dump(mode="json") for line in lines]}
    finally:
        conn.close()
