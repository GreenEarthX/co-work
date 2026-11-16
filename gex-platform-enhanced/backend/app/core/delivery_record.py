"""
The delivery record (GreenMesh Phase 2, Step 2; alembic 103; gap G-08).

A delivery is a physical movement under ONE confirmed trade contract. It has no history of
its own: every state change is a contract event (trading_book/record.py) that names the
delivery, so it is hash-chained with the contract and anchored with it. The row in
`deliveries` holds the current state and the recorded facts; the database checks at commit
that its state is its latest event's (103).

    SCHEDULED -> IN_TRANSIT -> ARRIVED -> QUALITY_VERIFICATION -> ACCEPTED ->
    TITLE_TRANSFERRED -> SETTLED;  REJECTED after inspection;  DISPUTED from any open state.

Who acts (also enforced by 103's event trigger):
  schedule, dispatch          the seller
  receipt (ARRIVED)           the buyer
  inspection, dispute         either party
  unloading (DPU)             the buyer, naming its unloading record on file (106)
  risk (RISK_PASSED)          derived, never a party's act: written with the act that passes it
                              under the confirmed Incoterm (106; Step 3 sub-step 2)
  accept, reject, title, settle   NOT BUILT: Step 3 (an agreed independent inspector's
                              certificate against the confirmed spec, D1-D3). Refused here
                              and by the trigger, so nothing passes title on Step 2.

None of these acts takes four eyes: TRADE_CONFIRM (core/wae.py) asks for them on a party's
confirmation of terms, and these are operational records under terms already confirmed so.
GEX staff read a delivery's state and events; they never act (GEX trades nothing).

What the seller states and what is read:
  * the PHYSICAL flow the delivery fulfils, in the contract's current version; the buyer is
    that flow's receiver, and the delivery window must start inside the flow's period;
  * the tokens it draws on, kg each: tokens of the contract, never beyond what custody
    allocated to them (mass_balance_allocations), across all deliveries;
  * the Incoterm and named place are READ from the confirmed terms (a typed `delivery`
    clause, trading_book/clauses.py), never from the scheduler. They govern RISK only (JML
    ruling R1, 12 Nov 2026, amending D4): title follows the contract's title clause and
    payment its payment clause. A delivery reports the three bases separately; a contract
    that names no Incoterm gets a delivery whose risk basis is MISSING.

A delivery may not be scheduled or dispatched at a time inside a CLOSED custody period of
the facility its lots come from: a closed period's statement is final, so nothing is booked
into it afterwards. (Arrival and later acts touch no custody period.)
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse
from app.trading_book import record

STATES = ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION", "ACCEPTED", "REJECTED",
          "TITLE_TRANSFERRED", "SETTLED", "DISPUTED")
NOT_BUILT = ("SETTLED",)     # ACCEPTED / REJECTED: delivery_inspection (107); TITLE: delivery_title (109)
DISPUTABLE = ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION", "ACCEPTED", "TITLE_TRANSFERRED")
NEXT = {"SCHEDULED": ("IN_TRANSIT",), "IN_TRANSIT": ("ARRIVED",), "ARRIVED": ("QUALITY_VERIFICATION",),
        "QUALITY_VERIFICATION": ("ACCEPTED", "REJECTED"), "ACCEPTED": ("TITLE_TRANSFERRED",),
        "TITLE_TRANSFERRED": ("SETTLED",), "DISPUTED": ("ACCEPTED", "REJECTED")}   # DISPUTED exit: 108
from app.trading_book.clauses import INCOTERMS, SEA_ONLY  # noqa: E402,F401  (re-exported)
MODES = ("PIPELINE", "SHIP", "TRUCK", "RAIL", "ISO_CONTAINER")
LOCODE = re.compile(r"^[A-Z]{2}[A-Z2-9]{3}$")
TRADABLE = ("confirmed", "active")


# ── plumbing ────────────────────────────────────────────────────────────────

def _conn():
    return me._conn()          # the operator connection; every caller authorises its Party first


def _row(conn, sql, params=()):
    return record._row(conn, sql, params)


def _rows(conn, sql, params=()):
    return record._rows(conn, sql, params)


def _dec(v) -> Decimal:
    try:
        d = Decimal(str(v))
    except Exception:
        _refuse(422, "DELIVERY_QUANTITY", f"{v!r} is not a quantity in kg.")
    if not d.is_finite():
        _refuse(422, "DELIVERY_QUANTITY", f"{v!r} is not a quantity in kg.")
    return d


def _ts(v, what: str) -> datetime:
    try:
        t = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    except ValueError:
        _refuse(422, "DELIVERY_TIME", f"{what}: {v!r} is not an ISO-8601 time.")
    if t.tzinfo is None:
        _refuse(422, "DELIVERY_TIME", f"{what} needs a UTC offset.")
    return t.astimezone(timezone.utc)


def _not_future(t: datetime, what: str) -> None:
    if t > datetime.now(timezone.utc):
        _refuse(422, "DELIVERY_TIME", f"{what} is in the future: a record states what has happened.")


def _note(**facts) -> str:
    """The event's note: the facts of the act as canonical JSON, so the event hash covers them."""
    return json.dumps({k: (str(v) if isinstance(v, (Decimal, datetime)) else v) for k, v in facts.items()},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _db_refusal(exc: Exception):
    """103's triggers answer check_violation with 'CODE: message'; anything else propagates."""
    if getattr(exc, "pgcode", None) == "23514" or "check_violation" in type(exc).__name__.lower():
        text = str(getattr(exc, "diag", None) and exc.diag.message_primary or exc).strip()
        code, _, msg = text.partition(":")
        if code.isupper() and code.replace("_", "").isalpha():
            _refuse(409, code, msg.strip() or text)
        _refuse(409, "DELIVERY_REFUSED", text)
    raise exc


def _party_company(party: Party) -> str:
    me._trader(party)          # GEX operates the market; it records no delivery
    return party.company_id


def _delivery(conn, delivery_id: str, *, lock: bool = False) -> dict:
    d = _row(conn, "SELECT * FROM deliveries WHERE id = ?" + (" FOR UPDATE" if lock else ""), (delivery_id,))
    if d is None:
        _refuse(404, "DELIVERY_NOT_FOUND", "No delivery with that id.")
    return d


# ── reading the contract ────────────────────────────────────────────────────

def _physical_flow(conn, terms_id: str, leg_seq: int, flow_seq: int) -> dict:
    f = _row(conn, "SELECT f.id, f.flow_type::text AS flow_type, f.period_start, f.period_end, f.unit, "
                   "l.sub_leg_id, pc.company_id AS payer, rc.company_id AS receiver FROM tb_flow f "
                   "JOIN tb_leg l ON l.id = f.leg_id LEFT JOIN tb_counterparty pc ON pc.id = l.payer_id "
                   "LEFT JOIN tb_counterparty rc ON rc.id = l.receiver_id "
                   "WHERE l.terms_id = ? AND l.seq = ? AND f.seq = ?", (terms_id, leg_seq, flow_seq))
    if f is None:
        _refuse(422, "DELIVERY_FLOW", f"The contract's current version has no flow {leg_seq}.{flow_seq}.")
    if f["flow_type"].lower() != "physical":
        _refuse(422, "DELIVERY_FLOW", f"Flow {leg_seq}.{flow_seq} is a {f['flow_type']} flow, not a physical one.")
    return f


def incoterm_of(conn, terms_id: str, sub_leg_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(Incoterm, named place) from the confirmed terms' typed `delivery` clause: the flow's
    sub-leg's own clause first, else a shared one. Free text ("FOB Rotterdam") is not read
    as an Incoterm. Governs risk only (R1)."""
    from app.trading_book import clauses

    risk = clauses.for_terms(conn, terms_id, sub_leg_id)["risk"]
    return (risk["incoterm"], risk["named_place"].strip()) if risk else (None, None)


def contract_clauses(conn, d: dict) -> dict:
    """The typed clauses of the terms version the delivery was scheduled under."""
    from app.trading_book import clauses

    v = _row(conn, "SELECT terms_id FROM tb_contract_version WHERE contract_id = ? AND terms_hash = ?",
             (str(d["contract_id"]), d["terms_hash"]))
    if v is None:
        return {"risk": None, "title": None, "payment": None}
    return clauses.for_terms(conn, str(v["terms_id"]), d["sub_leg_id"] and str(d["sub_leg_id"]))


def _closed_period_at(conn, token_ids: list[str], at: datetime) -> Optional[dict]:
    """A CLOSED custody period, of a facility the tokens' lots come from, that contains `at`."""
    if not token_ids:
        return None
    # A carved token (109/114) has no allocation of its own: its lot is allocated to its root.
    from app.core.delivery_title import root_of
    token_ids = sorted({root_of(conn, t) for t in token_ids})
    marks = ", ".join("?" for _ in token_ids)
    return _row(conn, f"SELECT p.period_id, p.facility_id, p.period_start, p.period_end FROM coc_period p "
                      f"JOIN mass_balance_lots l ON l.project_id = p.project_id AND l.facility_id = p.facility_id "
                      f"AND l.molecule = p.molecule JOIN mass_balance_allocations a ON a.lot_id = l.lot_id "
                      f"WHERE a.token_id IN ({marks}) AND p.status = 'CLOSED' "
                      f"AND ? BETWEEN p.period_start AND p.period_end LIMIT 1", (*token_ids, at.date()))


def _refuse_closed(conn, token_ids: list[str], at: datetime, what: str) -> None:
    p = _closed_period_at(conn, token_ids, at)
    if p:
        _refuse(409, "COC_PERIOD_CLOSED", f"{what} falls in custody period {p['period_id']} of facility "
                                          f"{p['facility_id']} ({p['period_start']}..{p['period_end']}), "
                                          f"which is closed.")


def _place(conn, side: str, place: dict, seller_project: str) -> tuple[Optional[str], Optional[str]]:
    locode, facility = (place or {}).get("locode"), (place or {}).get("facility_id")
    if bool(locode) == bool(facility):
        _refuse(422, "DELIVERY_PLACE", f"The {side} is ONE of a UN/LOCODE or a registered facility.")
    if locode:
        if not LOCODE.match(locode):
            _refuse(422, "DELIVERY_PLACE", f"{locode!r} is not a UN/LOCODE (two letters, three letters or digits).")
        return locode, None
    sql = "SELECT 1 AS x FROM coc_facility_profile WHERE facility_id = ?"
    params: tuple = (facility,)
    if side == "origin":                      # the seller ships from its own facility
        sql, params = sql + " AND project_id = ?", (facility, seller_project)
    if not _row(conn, sql, params):
        _refuse(422, "DELIVERY_PLACE", f"Facility {facility!r} is not a registered facility"
                                       + (" of the contract's project." if side == "origin" else "."))
    return None, facility


# ── the one transition ──────────────────────────────────────────────────────

def _transition(conn, d: dict, to: str, party_company: str, actor: str, facts: dict,
                updates: Optional[dict] = None) -> dict:
    """Every state change: check the order and the party, write the contract event, move
    the row. In the caller's transaction; 103's triggers check the same at insert and commit."""
    frm = d["status"]
    if to in NOT_BUILT:
        _refuse(409, "DELIVERY_STEP_NOT_BUILT", f"{to} comes after Phase 2 Step 3 (stop before SETTLED).")
    if not ((to == "DISPUTED" and frm in DISPUTABLE) or to in NEXT.get(frm, ())):
        _refuse(409, "DELIVERY_STATE_ORDER", f"A {frm} delivery cannot become {to}.")
    seller, buyer = d["seller_company_id"], d["buyer_company_id"]
    # ACCEPTED is derived (no party): a PASS certificate or a confirmed waiver (107).
    allowed = {"IN_TRANSIT": (seller,), "ARRIVED": (buyer,), "ACCEPTED": (None,),
               "REJECTED": (buyer,), "TITLE_TRANSFERRED": (None,)}.get(to, (seller, buyer))
    if frm == "DISPUTED":                   # 108: a dispute moves only by its confirmed resolution
        allowed = (None,)
    if party_company not in allowed:
        who = "the seller" if allowed == (seller,) else "the buyer" if allowed == (buyer,) else "a party"
        _refuse(403, "DELIVERY_WRONG_PARTY", f"{to} is recorded by {who} of the delivery.")
    v = record.current_version(conn, str(d["contract_id"]))
    ev = record.append_event(conn, str(d["contract_id"]), f"DELIVERY_{to}", actor, party_company,
                             version_id=str(v["id"]), note=_note(delivery=d["id"], **{"from": frm, "to": to}, **facts),
                             delivery_id=d["id"])
    sets = {"status": to, **(updates or {})}
    conn.execute("UPDATE deliveries SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
                 (*sets.values(), d["id"]))
    return ev


def _commit(conn, fn):
    try:
        out = fn()
        conn.commit()
        return out
    except me.MarketRefused:
        conn.rollback()
        raise
    except Exception as exc:                  # a trigger's refusal reaches here at INSERT or COMMIT
        conn.rollback()
        _db_refusal(exc)


# ── acts ────────────────────────────────────────────────────────────────────

def schedule(party: Party, contract_id: str, body: dict) -> dict:
    """The seller nominates a delivery: flow, draws, window, mode, route."""
    company = _party_company(party)
    conn = _conn()
    try:
        def go():
            c = _row(conn, "SELECT * FROM tb_contract WHERE id = ? FOR UPDATE", (contract_id,))
            who = record.parties(conn, contract_id) if c else {"companies": set()}
            if c is None or company not in who["companies"]:
                _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
            if c["kind"] != "trade":
                _refuse(409, "DELIVERY_CONTRACT_KIND", "Deliveries are recorded on trade contracts, whose tokens "
                                                      "carry custody-allocated quantities. An offtake frame's market "
                                                      "sub-leg is a trade: record its delivery there.")
            if c["trade_status"] not in TRADABLE:
                _refuse(409, "CONTRACT_STATE", f"The contract is {c['trade_status']}: a delivery needs terms every "
                                               f"party has confirmed.")
            if company != who["seller"]:
                _refuse(403, "DELIVERY_WRONG_PARTY", "A delivery is scheduled by the seller.")
            v = record.current_version(conn, contract_id)
            flow_ref = body.get("flow") or {}
            f = _physical_flow(conn, str(v["terms_id"]), int(flow_ref.get("leg_seq", 0)),
                               int(flow_ref.get("flow_seq", 0)))
            if f["payer"] != who["seller"] or f["receiver"] not in who["buyers"]:
                _refuse(422, "DELIVERY_FLOW", "That flow does not move product from the seller to a buyer.")
            start, end = _ts(body.get("window_start"), "window_start"), _ts(body.get("window_end"), "window_end")
            if end <= start:
                _refuse(422, "DELIVERY_WINDOW", "The delivery window ends before it starts.")
            if not (f["period_start"] <= start.date() <= f["period_end"]):
                _refuse(422, "DELIVERY_WINDOW", f"The window starts outside the flow's period "
                                                f"{f['period_start']}..{f['period_end']}.")
            mode = body.get("transport_mode")
            if mode not in MODES:
                _refuse(422, "DELIVERY_MODE", f"Transport mode is one of {', '.join(MODES)}.")
            o_loc, o_fac = _place(conn, "origin", body.get("origin"), c["project_id"])
            d_loc, d_fac = _place(conn, "destination", body.get("destination"), c["project_id"])

            draws, seen = [], set()
            for item in body.get("draws") or []:
                tid, kg = item.get("token_id"), _dec(item.get("kg"))
                if not tid or tid in seen or kg <= 0:
                    _refuse(422, "DELIVERY_DRAWS", "Each draw names a distinct token and a positive kg.")
                seen.add(tid)
                draws.append((tid, kg))
            if not draws:
                _refuse(422, "DELIVERY_DRAWS", "A delivery draws on at least one of the contract's tokens.")
            molecules = set()
            for tid, kg in draws:
                t = _row(conn, "SELECT t.molecule, t.lifecycle_state FROM tokens t JOIN tb_contract_version_token vt "
                               "ON vt.token_id = t.id WHERE vt.version_id = ? AND t.id = ? FOR UPDATE OF t",
                         (str(v["id"]), tid))
                if t is None:
                    _refuse(422, "DELIVERY_TOKEN_NOT_ON_CONTRACT", f"Token {tid} is not on the contract's current version.")
                if t["lifecycle_state"] in ("RETIRED", "ANNULLED", "VOIDED"):
                    _refuse(409, "DELIVERY_TOKEN_STATE", f"Token {tid} is {t['lifecycle_state']}.")
                molecules.add(t["molecule"])
                # app_token_kg (114): a carved token holds the kg its split recorded, not a direct allocation.
                q = _row(conn, "SELECT app_token_kg(?) AS allocated, (SELECT coalesce(sum(x.kg), 0) FROM delivery_draw x "
                               "JOIN deliveries y ON y.id = x.delivery_id WHERE x.token_id = ? AND y.status <> "
                               "'REJECTED') AS drawn", (tid, tid))   # B4: a rejected delivery's draws are released
                free = _dec(q["allocated"]) - _dec(q["drawn"])
                if kg > free:
                    _refuse(409, "DELIVERY_OVER_ALLOCATION", f"Token {tid} has {free} kg allocated from custody and "
                                                             f"not yet drawn; {kg} kg asked.")
            if len(molecules) != 1:
                _refuse(422, "DELIVERY_DRAWS", "A delivery carries one molecule.")
            _refuse_closed(conn, [t for t, _ in draws], start, "The delivery window's start")
            from app.trading_book import clauses as _cl

            risk = _cl.for_terms(conn, str(v["terms_id"]), f["sub_leg_id"] and str(f["sub_leg_id"]))["risk"]
            term, place = (risk["incoterm"], risk["named_place"].strip()) if risk else (None, None)
            point = ((risk.get("shipment_point") or "").strip() or None) if risk else None
            title = _cl.for_terms(conn, str(v["terms_id"]), f["sub_leg_id"] and str(f["sub_leg_id"]))["title"]
            passes = title["passes"] if title else None         # 109: read once, fixed by trigger
            if term in SEA_ONLY and mode != "SHIP":
                _refuse(422, "DELIVERY_MODE", f"The contract's Incoterm {term} is a sea and inland waterway rule; "
                                              f"the mode must be SHIP.")
            frame = _row(conn, "SELECT id FROM tb_sub_leg WHERE source_contract_id = ? LIMIT 1", (contract_id,))
            nominated = sum((kg for _, kg in draws), Decimal(0))
            did = f"DLV-{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO deliveries (id, project_id, contract_id, flow_id, sub_leg_id, frame_sub_leg_id, terms_hash, "
                "seller_company_id, buyer_company_id, molecule, status, window_start, window_end, nominated_kg, "
                "transport_mode, origin_locode, origin_facility_id, destination_locode, destination_facility_id, "
                "incoterm, named_place, shipment_point, title_passes, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'SCHEDULED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (did, c["project_id"], contract_id, str(f["id"]), f["sub_leg_id"] and str(f["sub_leg_id"]),
                 frame and str(frame["id"]), v["terms_hash"], who["seller"], f["receiver"], molecules.pop(), start,
                 end, nominated, mode, o_loc, o_fac, d_loc, d_fac, term, place, point, passes, party.user_id))
            for tid, kg in draws:
                conn.execute("INSERT INTO delivery_draw (delivery_id, token_id, kg) VALUES (?, ?, ?)", (did, tid, kg))
            ev = record.append_event(conn, contract_id, "DELIVERY_SCHEDULED", party.user_id, company,
                                     version_id=str(v["id"]), delivery_id=did, note=_note(
                                         delivery=did, to="SCHEDULED", flow=f"{flow_ref['leg_seq']}.{flow_ref['flow_seq']}",
                                         draws=[[t, str(k)] for t, k in draws], nominated_kg=nominated,
                                         window=[start.isoformat(), end.isoformat()], transport_mode=mode,
                                         origin=o_loc or o_fac, destination=d_loc or d_fac, incoterm=term,
                                         named_place=place, shipment_point=point, title_passes=passes,
                                         terms_hash=v["terms_hash"]))
            return {"delivery_id": did, "event": ev}
        out = _commit(conn, go)
        return get_delivery(party, out["delivery_id"])
    finally:
        conn.close()


def _act(party: Party, delivery_id: str, to: str, facts_fn) -> dict:
    company = _party_company(party)
    conn = _conn()
    try:
        def go():
            d = _delivery(conn, delivery_id, lock=True)
            if company not in (d["seller_company_id"], d["buyer_company_id"]):
                _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
            facts, updates = facts_fn(conn, d)
            ev = _transition(conn, d, to, company, party.user_id, facts, updates)
            _pass_risk(conn, d, to, ev["event_hash"])
            return ev
        _commit(conn, go)
    finally:
        conn.close()
    return get_delivery(party, delivery_id)


def dispatch(party: Party, delivery_id: str, dispatched_kg, dispatched_at) -> dict:
    """The seller's dispatch: the quantity that left, and when."""
    def facts(conn, d):
        kg, at = _dec(dispatched_kg), _ts(dispatched_at, "dispatched_at")
        if kg <= 0 or kg > _dec(d["nominated_kg"]):
            _refuse(409, "DELIVERY_OVER_NOMINATION", f"Dispatched {kg} kg; the delivery nominates "
                                                     f"{d['nominated_kg']} kg from its tokens.")
        _not_future(at, "dispatched_at")
        if d["status"] == "SCHEDULED":
            tokens = [r["token_id"] for r in _rows(conn, "SELECT token_id FROM delivery_draw WHERE delivery_id = ?",
                                                   (d["id"],))]
            _refuse_closed(conn, tokens, at, "The dispatch")
        return {"dispatched_kg": kg, "dispatched_at": at.isoformat()}, {"dispatched_kg": kg, "dispatched_at": at}
    return _act(party, delivery_id, "IN_TRANSIT", facts)


def receive(party: Party, delivery_id: str, delivered_kg, arrived_at) -> dict:
    """The buyer's receipt: the quantity that arrived, and when."""
    def facts(conn, d):
        kg, at = _dec(delivered_kg), _ts(arrived_at, "arrived_at")
        if kg < 0 or kg > _dec(d["nominated_kg"]):
            _refuse(409, "DELIVERY_OVER_NOMINATION", f"Received {kg} kg; the delivery nominates "
                                                     f"{d['nominated_kg']} kg from its tokens.")
        _not_future(at, "arrived_at")
        if d["dispatched_at"] is not None and at < d["dispatched_at"]:
            _refuse(422, "DELIVERY_TIME", "The cargo arrived before it was dispatched.")
        return {"delivered_kg": kg, "arrived_at": at.isoformat()}, {"delivered_kg": kg, "arrived_at": at}
    return _act(party, delivery_id, "ARRIVED", facts)


def request_inspection(party: Party, delivery_id: str, note: Optional[str] = None) -> dict:
    return _act(party, delivery_id, "QUALITY_VERIFICATION", lambda conn, d: ({"note": (note or "").strip() or None}, {}))


def dispute(party: Party, delivery_id: str, reason: str) -> dict:
    if not (reason or "").strip():
        _refuse(422, "DISPUTE_REASON", "A dispute states its reason.")
    return _act(party, delivery_id, "DISPUTED", lambda conn, d: ({"reason": reason.strip()}, {}))


# ── risk: derived from the Incoterm (Step 3 sub-step 2; alembic 106) ───────

RISK_AT_DISPATCH = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP")
RISK_ON_ARRIVAL = ("DAP", "DDP")
RISK_ACTOR = "system:incoterm"


def _pass_risk(conn, d: dict, at_state: str, cause_hash: str) -> Optional[dict]:
    """Write DELIVERY_FACT_RISK_PASSED when `at_state` is where the confirmed Incoterm passes
    risk. Nothing is written without an Incoterm, or for a C term without its shipment point:
    the delivery's risk basis then says why (clauses.bases)."""
    from app.trading_book.clauses import C_TERMS

    term = d["incoterm"]
    if term is None or (term in C_TERMS and not d["shipment_point"]):
        return None
    due = ((term in RISK_AT_DISPATCH and at_state == "IN_TRANSIT") or (term in RISK_ON_ARRIVAL and at_state == "ARRIVED")
           or (term == "DPU" and at_state == "UNLOADED"))
    if not due:
        return None
    v = record.current_version(conn, str(d["contract_id"]))
    return record.append_event(conn, str(d["contract_id"]), "DELIVERY_FACT_RISK_PASSED", RISK_ACTOR, None,
                               version_id=str(v["id"]), delivery_id=d["id"], note=_note(
                                   delivery=d["id"], fact="RISK_PASSED", incoterm=term, named_place=d["named_place"],
                                   shipment_point=d["shipment_point"], at_state=at_state, cause=cause_hash))


def record_unloading(party: Party, delivery_id: str, document_sha256: str, unloaded_at) -> dict:
    """DPU: the buyer records unloading at the named place, naming the unloading record on
    file (delivery_documents). Risk then passes."""
    from app.core import delivery_documents as docs

    company = _party_company(party)
    conn = _conn()
    try:
        def go():
            d = _delivery(conn, delivery_id, lock=True)
            if company not in (d["seller_company_id"], d["buyer_company_id"]):
                _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
            if company != d["buyer_company_id"]:
                _refuse(403, "DELIVERY_WRONG_PARTY", "Unloading is recorded by the buyer.")
            if d["incoterm"] != "DPU":
                _refuse(409, "DELIVERY_FACT_ORDER", "Unloading is recorded for a DPU delivery.")
            if d["status"] not in ("ARRIVED", "QUALITY_VERIFICATION"):
                _refuse(409, "DELIVERY_FACT_ORDER", f"Unloading follows arrival; the delivery is {d['status']}.")
            if _row(conn, "SELECT 1 AS x FROM tb_contract_event WHERE delivery_id = ? AND event_type = "
                          "'DELIVERY_FACT_UNLOADED'", (delivery_id,)):
                _refuse(409, "DELIVERY_FACT_ONCE", "Unloading is already recorded.")
            doc = docs.on_file(conn, delivery_id, "UNLOADING_RECORD", document_sha256)
            at = _ts(unloaded_at, "unloaded_at")
            _not_future(at, "unloaded_at")
            if at < d["arrived_at"]:
                _refuse(422, "DELIVERY_TIME", "Unloading cannot precede arrival.")
            v = record.current_version(conn, str(d["contract_id"]))
            ev = record.append_event(conn, str(d["contract_id"]), "DELIVERY_FACT_UNLOADED", party.user_id, company,
                                     version_id=str(v["id"]), delivery_id=delivery_id, note=_note(
                                         delivery=delivery_id, fact="UNLOADED", document_sha256=doc["sha256"].strip(),
                                         unloaded_at=at.isoformat()))
            _pass_risk(conn, d, "UNLOADED", ev["event_hash"])
            return ev
        _commit(conn, go)
    finally:
        conn.close()
    return get_delivery(party, delivery_id)


# ── reading ─────────────────────────────────────────────────────────────────

def _view(conn, d: dict) -> dict:
    out = {k: (str(v) if isinstance(v, (Decimal, uuid.UUID)) else v.isoformat() if isinstance(v, datetime) else v)
           for k, v in d.items()}
    out["draws"] = [{"token_id": r["token_id"], "kg": str(r["kg"])} for r in _rows(
        conn, "SELECT token_id, kg FROM delivery_draw WHERE delivery_id = ? ORDER BY token_id", (d["id"],))]
    out["events"] = [{"seq": e["seq"], "event_type": e["event_type"], "actor": e["actor"], "company_id": e["company_id"],
                      "at": e["at"].isoformat() if isinstance(e["at"], datetime) else e["at"], "note": e["note"],
                      "event_hash": e["event_hash"]}
                     for e in _rows(conn, "SELECT seq, event_type, actor, company_id, at, note, event_hash FROM "
                                          "tb_contract_event WHERE delivery_id = ? ORDER BY seq", (d["id"],))]
    from app.core import delivery_documents as docs
    from app.trading_book import clauses

    out.update(clauses.bases(contract_clauses(conn, d)))   # risk, title and payment: three records (R1)
    passed = next((e for e in out["events"] if e["event_type"] == "DELIVERY_FACT_RISK_PASSED"), None)
    out["risk"] = ({"passed": True, "at": passed["at"], "at_state": json.loads(passed["note"])["at_state"],
                    "event_hash": passed["event_hash"], "note": passed["note"]} if passed else {"passed": False})
    out["documents"] = docs.documents_for(conn, d["id"])
    from app.core import delivery_inspection as di

    out["quality"] = di.quality_view(conn, d, out["events"])
    from app.core import delivery_title as dt

    out["title"] = dt.title_view(conn, d, out["events"])
    return out


def _reader(party: Party):
    """A connection that sees what the caller's company may see (103's RLS)."""
    from app.core.db_backend import PLATFORM_ADMIN, market_connection

    if not party.is_admin and not party.company_id:
        _refuse(403, "NO_COMPANY", "Your account belongs to no company.")
    return market_connection(company_id=PLATFORM_ADMIN if party.is_admin else party.company_id)


def get_delivery(party: Party, delivery_id: str) -> dict:
    conn = _reader(party)
    try:
        d = _row(conn, "SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
        if d is None:
            _refuse(404, "DELIVERY_NOT_FOUND", "No delivery you may read with that id.")
        return _view(conn, d)
    finally:
        conn.close()


def deliveries_for(party: Party, contract_id: str) -> list[dict]:
    conn = _reader(party)
    try:
        return [_view(conn, d) for d in _rows(conn, "SELECT * FROM deliveries WHERE contract_id = ? "
                                                    "ORDER BY window_start, id", (contract_id,))]
    finally:
        conn.close()
