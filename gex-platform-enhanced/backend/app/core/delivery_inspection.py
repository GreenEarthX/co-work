"""
Quality before title (GreenMesh Phase 2 Step 3, sub-step 3; alembic 107; D1, D2, D3, B4).

  1. A party PROPOSES an inspector company, with the appointment on file (D1). Never the
     seller's or the buyer's company, never GEX, an active tenant with an ACTIVE account.
  2. The OTHER party AGREES it, with four eyes inside that party: DELIVERY_CONFIRM, the same
     rules as TRADE_CONFIRM (core/wae.py) — a second ACTIVE person of the same company, one of
     the two an executive, never GEX. Until then there is no inspector; GEX appoints none.
  3. The agreed inspector CERTIFIES: the certificate on file, and the measured value of every
     parameter of the confirmed spec sheet (D2, trading_book/quality.py), judged PASS/FAIL.
     A contract with no confirmed sheet cannot be certified, so it never reaches ACCEPTED.
  4. PASS -> ACCEPTED, derived (no party act). FAIL -> either a WAIVER proposed by a party with
     the waiver on file and confirmed by the other with four eyes (D3) -> ACCEPTED, labelled
     DECLARED and FAIL; or the buyer REJECTS, which releases the draws (B4).

Every step is a contract event on the delivery (core/delivery_record.py, 107's trigger).
"""
from __future__ import annotations

import json
from typing import Optional

from app.core import delivery_documents as docs
from app.core import delivery_record as dr
from app.core import market_engine as me
from app.core.market_engine import Party, _refuse
from app.trading_book import record

ACCEPT_ACTOR = "system:inspection"


def _then_title(conn, delivery_id: str) -> None:
    """At ACCEPTED, title passes if the title clause is already met (109, core/delivery_title.py)."""
    from app.core import delivery_title as dt

    dt.maybe_transfer(conn, delivery_id)


def _latest_fact(conn, delivery_id: str, fact: str) -> Optional[dict]:
    e = record._row(conn, "SELECT company_id, note, event_hash, at FROM tb_contract_event WHERE delivery_id = ? "
                          "AND event_type = ? ORDER BY seq DESC LIMIT 1", (delivery_id, f"DELIVERY_FACT_{fact}"))
    if e:
        e["facts"] = json.loads(e["note"] or "{}")
    return e


def _fact(conn, d: dict, fact: str, actor: str, company: Optional[str], **facts) -> dict:
    v = record.current_version(conn, str(d["contract_id"]))
    return record.append_event(conn, str(d["contract_id"]), f"DELIVERY_FACT_{fact}", actor, company,
                               version_id=str(v["id"]), delivery_id=d["id"],
                               note=dr._note(delivery=d["id"], fact=fact, **facts))


def _party_delivery(conn, party: Party, delivery_id: str) -> tuple[dict, str]:
    company = dr._party_company(party)
    d = dr._delivery(conn, delivery_id, lock=True)
    if company not in (d["seller_company_id"], d["buyer_company_id"]):
        _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
    return d, company


def _independence_refusal(conn, d: dict, inspector: str) -> None:
    if inspector in (d["seller_company_id"], d["buyer_company_id"]):
        _refuse(422, "DELIVERY_INSPECTOR_NOT_INDEPENDENT", "The inspector is never the seller's or the buyer's company.")
    t = record._row(conn, "SELECT is_active FROM tenants WHERE company_id = ?", (inspector,))
    gex = record._row(conn, "SELECT 1 AS x FROM auth_users WHERE company_id = ? AND coalesce(is_platform_admin, 0) <> 0", (inspector,))
    active = record._row(conn, "SELECT 1 AS x FROM auth_users WHERE company_id = ? AND account_state = 'ACTIVE'",
                         (inspector,))
    if inspector == "greenearthx" or gex:
        _refuse(422, "DELIVERY_INSPECTOR_NOT_INDEPENDENT", "GEX inspects nothing and appoints no inspector.")
    if t is None or not t["is_active"] or active is None:
        _refuse(422, "DELIVERY_INSPECTOR_NOT_INDEPENDENT", f"{inspector} is not an active, registered company.")


def _no_certificate_yet(conn, d: dict) -> None:
    if d["status"] not in ("SCHEDULED", "IN_TRANSIT", "ARRIVED", "QUALITY_VERIFICATION"):
        _refuse(409, "DELIVERY_FACT_ORDER", f"An inspector is appointed before certification; the delivery is {d['status']}.")
    if _latest_fact(conn, d["id"], "CERTIFIED"):
        _refuse(409, "DELIVERY_FACT_ORDER", "The delivery is already certified.")


# ── 1. propose ──────────────────────────────────────────────────────────────

def propose_inspector(party: Party, delivery_id: str, inspector_company_id: str, document_sha256: str) -> dict:
    conn = dr._conn()
    try:
        def go():
            d, company = _party_delivery(conn, party, delivery_id)
            _no_certificate_yet(conn, d)
            _independence_refusal(conn, d, inspector_company_id)
            doc = docs.on_file(conn, delivery_id, "INSPECTOR_APPOINTMENT", document_sha256)
            return _fact(conn, d, "INSPECTOR_PROPOSED", party.user_id, company,
                         inspector_company_id=inspector_company_id, document_sha256=doc["sha256"].strip())
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


# ── 2 and 4. four eyes inside the confirming party (DELIVERY_CONFIRM) ───────

ACTS = ("INSPECTOR_AGREED", "WAIVER_CONFIRMED", "RESOLUTION_CONFIRMED")
PROPOSAL = {"INSPECTOR_AGREED": "INSPECTOR_PROPOSED", "WAIVER_CONFIRMED": "WAIVER_PROPOSED",
            "RESOLUTION_CONFIRMED": "RESOLUTION_PROPOSED"}


def _since_dispute(conn, d: dict, fact: str) -> Optional[dict]:
    """The latest `fact` written after the delivery's latest DISPUTED event (108)."""
    last = record._row(conn, "SELECT max(seq) AS s FROM tb_contract_event WHERE delivery_id = ? AND event_type = "
                             "'DELIVERY_DISPUTED'", (d["id"],))["s"] or 0
    e = record._row(conn, "SELECT company_id, note, event_hash, at, seq FROM tb_contract_event WHERE delivery_id = ? "
                          "AND event_type = ? AND seq > ? ORDER BY seq DESC LIMIT 1",
                    (d["id"], f"DELIVERY_FACT_{fact}", last))
    if e:
        e["facts"] = json.loads(e["note"] or "{}")
    return e


def _pending(conn, d: dict, act: str, company: str) -> dict:
    """The proposal this act confirms: the latest one, made by the OTHER party."""
    if act == "RESOLUTION_CONFIRMED":
        if d["status"] != "DISPUTED":
            _refuse(409, "DELIVERY_RESOLUTION_ORDER", f"A resolution is confirmed on a DISPUTED delivery; it is {d['status']}.")
        p = _since_dispute(conn, d, "RESOLUTION_PROPOSED")
    else:
        p = _latest_fact(conn, d["id"], PROPOSAL[act])
    if p is None:
        _refuse(409, "DELIVERY_NOTHING_TO_CONFIRM", f"There is no {PROPOSAL[act].lower().replace('_', ' ')} to confirm.")
    if p["company_id"] == company:
        _refuse(403, "DELIVERY_SAME_PARTY", "The other party confirms a proposal.")
    if act == "RESOLUTION_CONFIRMED":
        pass
    elif act == "INSPECTOR_AGREED":
        _no_certificate_yet(conn, d)
        agreed = _latest_fact(conn, d["id"], "INSPECTOR_AGREED")
        if agreed and agreed["at"] > p["at"]:
            _refuse(409, "DELIVERY_ALREADY_AGREED", "The latest proposal is already agreed.")
    else:
        if d["status"] != "QUALITY_VERIFICATION" or _latest_fact(conn, d["id"], "WAIVER_CONFIRMED"):
            _refuse(409, "DELIVERY_WAIVER_ORDER", "A waiver is confirmed once, in QUALITY_VERIFICATION.")
    return p


def request_confirmation(party: Party, delivery_id: str, act: str) -> dict:
    """The first pair of eyes on agreeing an inspector or confirming a waiver."""
    from app.core import wae

    if act not in ACTS:
        _refuse(422, "DELIVERY_CONFIRM_ACT", f"Confirmable acts: {', '.join(ACTS)}.")
    conn = dr._conn()
    try:
        d, company = _party_delivery(conn, party, delivery_id)
        p = _pending(conn, d, act, company)
        conn.rollback()
    finally:
        conn.close()
    initiator = wae._account(party.user_id)
    if not initiator or initiator.get("account_state") != "ACTIVE" or initiator.get("company_id") != company:
        _refuse(403, "ACCOUNT_NOT_ACTIVE", "Only an active account of a party raises its confirmation.")
    decision = wae.evaluate_authorization(
        initiator_user_id=party.user_id, action_type=wae.DELIVERY_CONFIRM, resource_id=delivery_id,
        project_id=d["project_id"], company_id=None,
        payload={"party_company_id": company, "act": act, "proposal_event_hash": p["event_hash"],
                 **({"outcome": p["facts"].get("outcome")} if act == "RESOLUTION_CONFIRMED" else {}),
                 **({"inspector_company_id": p["facts"].get("inspector_company_id")} if act == "INSPECTOR_AGREED" else {})})
    return {"request_id": decision.request_id, "outcome": decision.outcome.value, "act": act,
            "needs": "a second active account of your company; one of you an executive"}


def approve_confirmation(party: Party, delivery_id: str, request_id: str) -> dict:
    """The second pair of eyes. On quorum the act is written; a waiver's confirmation also
    accepts the delivery (D3), labelled DECLARED and FAIL."""
    from app.core import wae
    from app.core.db_backend import PLATFORM_ADMIN

    me._trader(party)
    req = wae.get_request(request_id, company_id=PLATFORM_ADMIN)
    payload = (req or {}).get("payload_json") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    if (req is None or req.get("action_type") != wae.DELIVERY_CONFIRM or req.get("resource_id") != delivery_id
            or payload.get("party_company_id") != party.company_id):
        _refuse(404, "CONFIRMATION_NOT_FOUND", "No confirmation of yours with that id on this delivery.")
    if req["status"] == "PENDING":
        result = wae.record_decision(request_id, party.user_id, wae.ApprovalDecision.APPROVE,
                                     reason_text=f"DELIVERY_CONFIRM {payload.get('act')} second approval")
        if "error" in result:
            code = result.get("code") or "CONFIRMATION_REFUSED"
            _refuse(409 if code == "ALREADY_DECIDED" else 403, code, result["error"])
        if not result["quorum_reached"]:
            return {"request_id": request_id, "quorum_reached": False}
    elif req["status"] != "APPROVED":
        _refuse(409, "CONFIRMATION_STATE", f"This confirmation is {req['status']}.")
    act = payload["act"]
    conn = dr._conn()
    try:
        def go():
            d, company = _party_delivery(conn, party, delivery_id)
            done = record._row(conn, "SELECT 1 AS x FROM tb_contract_event WHERE delivery_id = ? AND event_type = ? "
                                     "AND note LIKE ?", (delivery_id, f"DELIVERY_FACT_{act}",
                                                         f'%"request_id":"{request_id}"%'))   # canonical note (_note)
            if done:
                return None
            p = _pending(conn, d, act, company)
            if p["event_hash"] != payload.get("proposal_event_hash"):
                _refuse(409, "DELIVERY_PROPOSAL_CHANGED", "A newer proposal was made after this confirmation was raised.")
            if act == "INSPECTOR_AGREED":
                insp = p["facts"]["inspector_company_id"]
                ev = _fact(conn, d, act, party.user_id, company, inspector_company_id=insp,
                           proposal_event_hash=p["event_hash"], request_id=request_id)
                conn.execute("UPDATE deliveries SET inspector_company_id = ? WHERE id = ?", (insp, delivery_id))
                return ev
            if act == "RESOLUTION_CONFIRMED":
                outcome = p["facts"]["outcome"]
                ev = _fact(conn, d, act, party.user_id, company, outcome=outcome, proposal_event_hash=p["event_hash"],
                           request_id=request_id)
                cert = _latest_fact(conn, delivery_id, "CERTIFIED")
                passed = bool(cert) and cert["facts"].get("result") == "PASS"
                facts = {"basis": "RESOLUTION", "resolved": True, "resolution_event_hash": ev["event_hash"]}
                if outcome == "ACCEPTED":
                    facts.update(label="VERIFIED" if passed else "DECLARED", result="PASS" if passed else "FAIL")
                dr._transition(conn, d, outcome, None, ACCEPT_ACTOR, facts)
                _then_title(conn, delivery_id)
                return ev
            ev = _fact(conn, d, act, party.user_id, company, proposal_event_hash=p["event_hash"], request_id=request_id)
            dr._transition(conn, d, "ACCEPTED", None, ACCEPT_ACTOR,
                           {"basis": "WAIVER", "label": "DECLARED", "result": "FAIL", "waiver_event_hash": ev["event_hash"]})
            _then_title(conn, delivery_id)
            return ev
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


# ── 3. certify ──────────────────────────────────────────────────────────────

def certify(party: Party, delivery_id: str, document_sha256: str, measured: dict) -> dict:
    """The agreed inspector's certificate. PASS on every parameter accepts the delivery."""
    from app.trading_book import quality

    me._trader(party)
    conn = dr._conn()
    try:
        def go():
            d = dr._delivery(conn, delivery_id, lock=True)
            if not d["inspector_company_id"] or party.company_id != d["inspector_company_id"]:
                _refuse(403, "DELIVERY_NOT_THE_AGREED_INSPECTOR",
                        "Only the inspector both parties agreed certifies this delivery.")
            if d["status"] != "QUALITY_VERIFICATION":
                _refuse(409, "DELIVERY_FACT_ORDER", f"A certificate is recorded in QUALITY_VERIFICATION; the "
                                                    f"delivery is {d['status']}.")
            v = record._row(conn, "SELECT t.quality_spec FROM tb_contract_version v JOIN tb_terms t ON t.id = v.terms_id "
                                  "WHERE v.contract_id = ? AND v.terms_hash = ?", (str(d["contract_id"]), d["terms_hash"]))
            spec = (v or {}).get("quality_spec") or {}
            spec = spec if isinstance(spec, dict) else json.loads(spec)
            params = quality.sheet(spec)
            if params is None:
                _refuse(409, "DELIVERY_NO_CONFIRMED_SPEC", "The confirmed terms carry no quality specification sheet "
                                                           "(D2): the delivery cannot be certified against it.")
            try:
                results = quality.judge(params, measured)
            except ValueError as exc:
                _refuse(422, "DELIVERY_CERTIFICATE_INCOMPLETE", str(exc))
            doc = docs.on_file(conn, delivery_id, "INSPECTION_CERTIFICATE", document_sha256)
            overall = "PASS" if all(r["result"] == "PASS" for r in results) else "FAIL"
            ev = _fact(conn, d, "CERTIFIED", party.user_id, party.company_id, document_sha256=doc["sha256"].strip(),
                       results=results, result=overall)
            if overall == "PASS":
                dr._transition(conn, d, "ACCEPTED", None, ACCEPT_ACTOR,
                               {"basis": "CERTIFICATE", "label": "VERIFIED", "result": "PASS",
                                "certificate_event_hash": ev["event_hash"]})
                _then_title(conn, delivery_id)
            return ev
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


# ── 4. waiver and rejection ─────────────────────────────────────────────────

def propose_waiver(party: Party, delivery_id: str, document_sha256: str) -> dict:
    conn = dr._conn()
    try:
        def go():
            d, company = _party_delivery(conn, party, delivery_id)
            cert = _latest_fact(conn, delivery_id, "CERTIFIED")
            if d["status"] != "QUALITY_VERIFICATION" or cert is None or cert["facts"].get("result") != "FAIL":
                _refuse(409, "DELIVERY_WAIVER_ORDER", "A waiver follows a FAIL certificate, in QUALITY_VERIFICATION.")
            doc = docs.on_file(conn, delivery_id, "WAIVER", document_sha256)
            return _fact(conn, d, "WAIVER_PROPOSED", party.user_id, company, document_sha256=doc["sha256"].strip())
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


def propose_resolution(party: Party, delivery_id: str, outcome: str, document_sha256: str) -> dict:
    """A party proposes how a dispute ends (108): ACCEPTED (only with the agreed inspector's
    certificate, R4) or REJECTED, with the resolution on file. The other party confirms it."""
    if outcome not in ("ACCEPTED", "REJECTED"):
        _refuse(422, "DELIVERY_RESOLUTION_OUTCOME", "A dispute resolves to ACCEPTED or REJECTED.")
    conn = dr._conn()
    try:
        def go():
            d, company = _party_delivery(conn, party, delivery_id)
            if d["status"] != "DISPUTED":
                _refuse(409, "DELIVERY_RESOLUTION_ORDER", f"The delivery is {d['status']}, not DISPUTED.")
            if outcome == "ACCEPTED" and not _latest_fact(conn, delivery_id, "CERTIFIED"):
                _refuse(409, "DELIVERY_RESOLUTION_NO_CERTIFICATE",
                        "Acceptance needs the agreed inspector's certificate (R4); this dispute can resolve only to REJECTED.")
            doc = docs.on_file(conn, delivery_id, "DISPUTE_RESOLUTION", document_sha256)
            return _fact(conn, d, "RESOLUTION_PROPOSED", party.user_id, company, outcome=outcome,
                         document_sha256=doc["sha256"].strip())
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


def reject(party: Party, delivery_id: str, reason: str) -> dict:
    """The buyer rejects on a FAIL certificate with no confirmed waiver. The draws are released (B4)."""
    if not (reason or "").strip():
        _refuse(422, "REJECTION_REASON", "A rejection states its reason.")
    conn = dr._conn()
    try:
        def go():
            d, company = _party_delivery(conn, party, delivery_id)
            cert = _latest_fact(conn, delivery_id, "CERTIFIED")
            if cert is None or cert["facts"].get("result") != "FAIL" or _latest_fact(conn, delivery_id, "WAIVER_CONFIRMED"):
                _refuse(409, "DELIVERY_NOT_REJECTABLE", "A delivery is rejected on a FAIL certificate with no "
                                                        "confirmed waiver.")
            return dr._transition(conn, d, "REJECTED", company, party.user_id,
                                  {"reason": reason.strip(), "certificate_event_hash": cert["event_hash"]})
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


def quality_view(conn, d: dict, events: list[dict]) -> dict:
    """The delivery's inspection, as a reader states it."""
    def last(fact):
        es = [e for e in events if e["event_type"] == f"DELIVERY_FACT_{fact}"]
        return json.loads(es[-1]["note"]) if es else None
    cert, proposed = last("CERTIFIED"), last("INSPECTOR_PROPOSED")
    acc = [json.loads(e["note"]) for e in events if e["event_type"] == "DELIVERY_ACCEPTED"]
    accepted = acc[-1] if acc else None
    out = {"inspector_company_id": d.get("inspector_company_id"),
           "inspector_proposed": proposed and proposed.get("inspector_company_id"),
           "certificate": cert and {"result": cert["result"], "results": cert["results"]},
           "waiver_confirmed": last("WAIVER_CONFIRMED") is not None}
    if accepted:
        basis = accepted.get("basis")
        out["acceptance"] = ({"basis": "CERTIFICATE", "label": "VERIFIED", "result": "PASS"} if basis == "CERTIFICATE"
                             else {"basis": "WAIVER", "label": "DECLARED", "result": "FAIL"} if basis == "WAIVER"
                             else {"basis": "RESOLUTION", "label": accepted.get("label"), "result": accepted.get("result"),
                                   "resolved": True})
    return out
