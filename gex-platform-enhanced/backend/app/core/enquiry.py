"""
A non-binding enquiry, and contact released only by consent (discovery Phase 1, R9; D-D; alembic 119).

An enquiry asks one company about ONE listing or ONE RFQ. It binds nothing: a firm proposal is a
separate act (market_engine.create_match). Until the receiving party chooses **Share contact**,
neither side learns who the other is: each sees the other's role and vetting badge only, and the
thread says "you" and "them". Sharing contact releases, to BOTH parties, the legal entity, the
named person on each side (the asker and the one who consented) and the record's private details
(a listing's location; an RFQ's location and contact). By sending, the asker agrees to that
release if, and only if, the other side shares theirs. **Decline** releases nothing. The consent is
an event in the ledger.

Who may act is core/market_policy (D-B): `enquiry.send` to ask or withdraw, `enquiry.reply` to
answer, share or decline. GEX trades nothing, so it neither asks nor answers. Writes go through the
market operator connection after the party is authorised here, as every market write.
"""
from __future__ import annotations

import uuid
from typing import Optional

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse

SHARED = ("contact_shared", "closed")


def _person(conn, user_id: Optional[str]) -> Optional[dict]:
    u = me._row(conn, "SELECT user_name, email, company_name FROM auth_users WHERE user_id = ?", (user_id,)) if user_id else None
    return {"name": u["user_name"], "email": u["email"]} if u else None


def _company_name(conn, company_id: str) -> Optional[str]:
    t = me._row(conn, "SELECT company_name FROM tenants WHERE company_id = ?", (company_id,))
    return (t or {}).get("company_name")


def _target(conn, e: dict) -> dict:
    """The listing or RFQ asked about, as any member sees it, plus its private details (released
    only with consent) and the company that owns it."""
    if e.get("listing_order_id"):
        o = me._listing_by_id(conn, str(e["listing_order_id"]))
        full = me._listing(conn, o)
        public = me._public_listing(conn, full)
        return {"kind": "listing", "public": public, "owner": full["seller_company_id"], "state": full["listing_state"],
                "private": {"location": full.get("location")}}
    r = me._rfq_by_id(conn, str(e["rfq_id"]))
    if r is None:
        _refuse(404, "RFQ_NOT_FOUND", "No RFQ with that id.")
    v = me._rfq(conn, r)
    public = {k: v.get(k) for k in me.RFQ_LISTING_FIELDS}
    return {"kind": "rfq", "public": public, "owner": v["buyer_company_id"], "state": v["status"],
            "private": {"location": v.get("location"), "buyer_contact": v.get("buyer_contact")}}


def _view(conn, party: Party, e: dict, messages: bool = True) -> dict:
    mine_sent = e["from_company_id"] == party.company_id
    other = e["to_company_id"] if mine_sent else e["from_company_id"]
    t = _target(conn, e)
    badges = me._badges(conn, other)
    out = {
        "id": str(e["id"]), "role": "sent" if mine_sent else "received", "status": e["status"],
        "subject": {"kind": t["kind"], **t["public"]}, "subject_state": t["state"],
        "counterparty": {"role": badges["role"], "vetting": badges["vetting"]},
        "about_rfq_id": str(e["about_rfq_id"]) if e.get("about_rfq_id") and mine_sent else None,
        "assessment_id": str(e["assessment_id"]) if e.get("assessment_id") and mine_sent else None,
        "created_at": me._iso(e["created_at"]), "decided_at": me._iso(e.get("decided_at")),
        "can": {"reply": e["status"] in ("open", "contact_shared"),
                "share_contact": not mine_sent and e["status"] == "open",
                "decline": not mine_sent and e["status"] == "open",
                "withdraw": mine_sent and e["status"] == "open"},
    }
    if e["status"] in SHARED:
        # D-D: released to both parties by the receiving party's consent.
        asker = {"company_id": e["from_company_id"], "company_name": _company_name(conn, e["from_company_id"]),
                 "person": _person(conn, e["from_user_id"])}
        owner = {"company_id": e["to_company_id"], "company_name": _company_name(conn, e["to_company_id"]),
                 "person": _person(conn, e.get("decided_by")), "details": t["private"]}
        out["counterparty"]["identity"] = owner if mine_sent else asker
    if messages:
        out["messages"] = [{"side": "you" if m["company_id"] == party.company_id else "them", "body": m["body"],
                            "evidence_request": m.get("evidence_request"), "at": me._iso(m["created_at"])}
                           for m in me._rows(conn, "SELECT * FROM market_enquiry_message WHERE enquiry_id = ? ORDER BY id",
                                             (str(e["id"]),))]
    return out


def _load(conn, party: Party, enquiry_id: str, lock: bool = False) -> dict:
    e = me._row(conn, "SELECT * FROM market_enquiry WHERE id = ?" + (" FOR UPDATE" if lock else ""),
                (enquiry_id,)) if me._is_uuid(enquiry_id) else None
    if e is None or (not party.is_admin and party.company_id not in (e["from_company_id"], e["to_company_id"])):
        _refuse(404, "ENQUIRY_NOT_FOUND", "No enquiry of yours with that id.")
    return e


def _message(conn, enquiry_id: str, party: Party, body: str, evidence_request: Optional[str]) -> None:
    body = (body or "").strip()
    if not body or len(body) > 4000:
        _refuse(422, "ENQUIRY_MESSAGE", "Write a message (at most 4,000 characters).")
    ev = (evidence_request or "").strip() or None
    if ev and len(ev) > 1000:
        _refuse(422, "ENQUIRY_MESSAGE", "An evidence request is at most 1,000 characters.")
    conn.execute("INSERT INTO market_enquiry_message (enquiry_id, company_id, actor_id, body, evidence_request) "
                 "VALUES (?, ?, ?, ?, ?)", (enquiry_id, party.company_id, party.user_id, body, ev))


def send(party: Party, *, body: str, listing_id: Optional[str] = None, rfq_id: Optional[str] = None,
         about_rfq_id: Optional[str] = None, evidence_request: Optional[str] = None) -> dict:
    me._trader(party)
    me._may(party, "enquiry.send")
    if bool(listing_id) == bool(rfq_id):
        _refuse(422, "ENQUIRY_SUBJECT", "An enquiry is about one listing or one RFQ.")
    if about_rfq_id and not listing_id:
        _refuse(422, "ENQUIRY_SUBJECT", "Only an enquiry about a listing can cite your RFQ.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        enquiry_id = str(uuid.uuid4())
        draft = {"listing_order_id": listing_id, "rfq_id": rfq_id}
        if listing_id and not me._is_uuid(listing_id) or rfq_id and not me._is_uuid(rfq_id):
            _refuse(404, "ENQUIRY_SUBJECT_NOT_FOUND", "No open listing or RFQ with that id.")
        try:
            t = _target(conn, draft)
        except me.MarketRefused:
            _refuse(404, "ENQUIRY_SUBJECT_NOT_FOUND", "No open listing or RFQ with that id.")
        if t["kind"] == "listing":
            raw = me._listing_by_id(conn, listing_id)
            if t["state"] != "OPEN" or raw.get("visibility") != "platform" or raw.get("origin_book"):
                _refuse(404, "ENQUIRY_SUBJECT_NOT_FOUND", "No open listing or RFQ with that id.")
        elif t["state"] != "open":
            _refuse(404, "ENQUIRY_SUBJECT_NOT_FOUND", "No open listing or RFQ with that id.")
        if t["owner"] == party.company_id:
            _refuse(409, "SELF_ENQUIRY", "That listing or RFQ is your own company's.")
        if me._row(conn, "SELECT 1 AS x FROM market_enquiry WHERE from_company_id = ? AND status = 'open' AND "
                         + ("listing_order_id = ?" if listing_id else "rfq_id = ?"), (party.company_id, listing_id or rfq_id)):
            _refuse(409, "ENQUIRY_OPEN", "Your company already has an open enquiry about this; continue it in Deals.")
        assessment_id = None
        if about_rfq_id:
            r = me._rfq_by_id(conn, about_rfq_id)
            rfq = me._rfq(conn, r) if r else None
            if rfq is None or rfq["buyer_company_id"] != party.company_id:
                _refuse(404, "RFQ_NOT_FOUND", "No RFQ of yours with that id.")
            from app.core import compatibility as cx
            assessment = cx.assess(rfq, t["public"])
            assessment_id = me._store_assessment(conn, party, rfq, t["public"], assessment, purpose="enquiry")
        conn.execute("INSERT INTO market_enquiry (id, listing_order_id, rfq_id, about_rfq_id, from_company_id, from_user_id, "
                     "to_company_id, assessment_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (enquiry_id, listing_id, rfq_id, about_rfq_id, party.company_id, party.user_id, t["owner"],
                      assessment_id))
        _message(conn, enquiry_id, party, body, evidence_request)
        trail.add("enquiry.sent", "enquiry", enquiry_id, {"subject": t["kind"], "assessment_id": assessment_id},
                  f"ENQ-{enquiry_id[:8].upper()}")
        me._commit(conn, trail)
        return _view(conn, party, _load(conn, party, enquiry_id))
    finally:
        conn.close()


def mine(party: Party) -> list[dict]:
    if not party.company_id:
        return []
    conn = me._conn()
    try:
        rows = me._rows(conn, "SELECT * FROM market_enquiry WHERE from_company_id = ? OR to_company_id = ? "
                              "ORDER BY created_at DESC", (party.company_id, party.company_id))
        return [_view(conn, party, e, messages=False) for e in rows]
    finally:
        conn.close()


def get(party: Party, enquiry_id: str) -> dict:
    conn = me._conn()
    try:
        return _view(conn, party, _load(conn, party, enquiry_id))
    finally:
        conn.close()


def reply(party: Party, enquiry_id: str, body: str, evidence_request: Optional[str] = None) -> dict:
    me._trader(party)
    conn, trail = me._conn(), me._Trail(party)
    try:
        e = _load(conn, party, enquiry_id, lock=True)
        me._may(party, "enquiry.send" if e["from_company_id"] == party.company_id else "enquiry.reply")
        if e["status"] not in ("open", "contact_shared"):
            _refuse(409, "ENQUIRY_CLOSED", f"This enquiry is {e['status'].replace('_', ' ')}; nothing more can be added.")
        _message(conn, enquiry_id, party, body, evidence_request)
        trail.add("enquiry.message", "enquiry", enquiry_id, {}, f"ENQ-{enquiry_id[:8].upper()}")
        me._commit(conn, trail)
        return _view(conn, party, _load(conn, party, enquiry_id))
    finally:
        conn.close()


def decide(party: Party, enquiry_id: str, decision: str) -> dict:
    """share_contact | decline (the receiving party) | withdraw (the asker)."""
    me._trader(party)
    target = {"share_contact": "contact_shared", "decline": "declined", "withdraw": "withdrawn"}.get(decision)
    if target is None:
        _refuse(422, "ENQUIRY_DECISION", "Share contact, decline or withdraw.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        e = _load(conn, party, enquiry_id, lock=True)
        asker = e["from_company_id"] == party.company_id
        if decision == "withdraw":
            me._may(party, "enquiry.send")
            if not asker:
                _refuse(403, "NOT_THE_ASKER", "Only the company that sent an enquiry withdraws it.")
        else:
            me._may(party, "enquiry.reply")
            if asker:
                _refuse(403, "NOT_THE_RECEIVER", "Only the company asked can share its contact or decline.")
        if e["status"] != "open":
            _refuse(409, "ENQUIRY_STATE", f"This enquiry is {e['status'].replace('_', ' ')}, not open.")
        conn.execute("UPDATE market_enquiry SET status = ?, decided_at = now(), decided_by = ? WHERE id = ?",
                     (target, party.user_id, enquiry_id))
        trail.add(f"enquiry.{target}", "enquiry", enquiry_id,
                  {"released_to": [e["from_company_id"], e["to_company_id"]]} if target == "contact_shared" else {},
                  f"ENQ-{enquiry_id[:8].upper()}")
        me._commit(conn, trail)
        return _view(conn, party, _load(conn, party, enquiry_id))
    finally:
        conn.close()
