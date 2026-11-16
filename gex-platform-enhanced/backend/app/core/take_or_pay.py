"""
Take-or-pay shortfall per contract year (GreenMesh Phase 2 Step 4; gap G-11, partly).

Deliveries happen on trade contracts (103), so the terms are the trade's own CONFIRMED terms:

  * the typed `commitment` clause (trading_book/clauses.py): commitment_form TAKE_OR_PAY,
    take_or_pay_pct, and an optional shortfall_price per tonne in the terms' currency;
  * the contracted quantity per contract year: the trade's PHYSICAL flows in tonnes, years
    counted from the first physical period_start (as contract_tokens.derive_projection does);
  * the delivered-and-accepted quantity: its deliveries now ACCEPTED, TITLE_TRANSFERRED or
    SETTLED, the buyer's received kg, counted in the contract year of the PHYSICAL FLOW each
    delivery fulfils (the obligation it delivers), not the day it was accepted.

    shortfall_t = max(0, take_or_pay_pct / 100 x contracted_t - accepted_t)
    amount      = shortfall_t x shortfall_price   ONLY when the confirmed terms state a price

GEX computes; it does not invoice. A missing term gives no figure, naming what is missing. A
delivery accepted on a PASS certificate counts VERIFIED; one accepted under a waiver (D3) or a
resolution labelled DECLARED counts DECLARED, and any DECLARED quantity makes the year's figure
DECLARED. A year not yet over is provisional.

Availability and penalties: the confirmed terms carry no availability guarantee and no rate
(no such clause exists), so neither is computed; the design source's 80 % material-breach
threshold is never used (brief Step 4).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from app.trading_book import clauses as cl
from app.trading_book import record

COUNTED = ("ACCEPTED", "TITLE_TRANSFERRED", "SETTLED")
T = Decimal(1000)


def _q(x: Decimal) -> str:
    """A quantity as plain decimal text, without the storage scale's trailing zeros."""
    return format(x.normalize(), "f") if x != 0 else "0"


def _year_bounds(start: date, n: int) -> tuple[date, date]:
    return start.replace(year=start.year + n), start.replace(year=start.year + n + 1)


def compute(conn, contract_id: str, as_of: Optional[date] = None) -> dict:
    as_of = as_of or datetime.now(timezone.utc).date()
    c = record._row(conn, "SELECT id, kind, trade_status FROM tb_contract WHERE id = ?", (contract_id,))
    out = {"contract_id": contract_id, "as_of": as_of.isoformat(),
           "availability": {"computed": False, "reason": "the confirmed terms carry no availability guarantee or "
                                                         "rate, so neither availability nor a penalty is computed"}}
    if c is None:
        return {**out, "computed": False, "reason": "no such contract"}
    if c["trade_status"] not in ("confirmed", "active", "completed"):
        return {**out, "computed": False, "reason": f"the contract is {c['trade_status']}: no confirmed terms yet"}
    v = record.current_version(conn, contract_id)
    commit = cl.for_terms(conn, str(v["terms_id"]), None)["commitment"]
    if commit is None:
        return {**out, "computed": False, "reason": "MISSING: the confirmed terms carry no typed commitment clause"}
    if commit["commitment_form"] != "TAKE_OR_PAY":
        return {**out, "computed": False, "commitment_form": commit["commitment_form"],
                "reason": f"the commitment is {commit['commitment_form']}, not TAKE_OR_PAY: no shortfall applies"}
    pct = Decimal(str(commit["take_or_pay_pct"]))
    price = None if commit.get("shortfall_price") is None else Decimal(str(commit["shortfall_price"]))
    flows = record._rows(conn, "SELECT f.period_start, f.quantity, f.unit FROM tb_flow f JOIN tb_leg l ON l.id = f.leg_id "
                               "WHERE l.terms_id = ? AND f.flow_type::text = 'physical'", (str(v["terms_id"]),))
    if not flows or any((f["unit"] or "").strip().lower() not in ("t", "mt", "tonne", "tonnes") for f in flows):
        return {**out, "computed": False, "reason": "the contracted quantity is not stated in tonnes on physical flows"}
    currency = record._row(conn, "SELECT currency FROM tb_terms WHERE id = ?", (str(v["terms_id"]),))["currency"]
    start = min(f["period_start"] for f in flows)
    last = max(f["period_start"] for f in flows)
    delivered = []
    for d in record._rows(conn, "SELECT d.id, d.status, d.delivered_kg, f.period_start AS flow_start, "
                                "(SELECT e.note FROM tb_contract_event e WHERE e.delivery_id = d.id AND "
                                "e.event_type = 'DELIVERY_ACCEPTED' ORDER BY e.seq DESC LIMIT 1) AS accepted_note "
                                "FROM deliveries d JOIN tb_flow f ON f.id = d.flow_id WHERE d.contract_id = ?",
                          (contract_id,)):
        if d["status"] in COUNTED and d["accepted_note"] is not None and d["delivered_kg"] is not None:
            note = json.loads(d["accepted_note"] or "{}")
            label = "VERIFIED" if note.get("label") == "VERIFIED" else "DECLARED"     # 107/108 label it
            delivered.append({"delivery_id": d["id"], "on": d["flow_start"], "t": Decimal(str(d["delivered_kg"])) / T,
                              "label": label})
    years, n = [], 0
    while True:
        a, b = _year_bounds(start, n)
        if a > last:
            break
        contracted = sum((Decimal(str(f["quantity"])) for f in flows if a <= f["period_start"] < b), Decimal(0))
        mine = [x for x in delivered if a <= x["on"] < b]
        verified = sum((x["t"] for x in mine if x["label"] == "VERIFIED"), Decimal(0))
        declared = sum((x["t"] for x in mine if x["label"] == "DECLARED"), Decimal(0))
        required = (pct / 100 * contracted)
        shortfall = max(Decimal(0), required - verified - declared)
        year = {"year": n + 1, "start": a.isoformat(), "end": b.isoformat(), "contracted_t": _q(contracted),
                "required_t": _q(required), "accepted_t": _q(verified + declared),
                "accepted_verified_t": _q(verified), "accepted_declared_t": _q(declared),
                "shortfall_t": _q(shortfall), "label": "DECLARED" if declared else "VERIFIED",
                "provisional": b > as_of, "deliveries": [x["delivery_id"] for x in mine]}
        if price is None:
            year.update(amount=None, amount_reason="the confirmed terms state no shortfall price")
        else:
            year.update(amount=str((shortfall * price).quantize(Decimal("0.01"))), currency=currency,
                        amount_reason="computed from the confirmed shortfall price; GEX does not invoice")
        years.append(year)
        n += 1
    return {**out, "computed": True, "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": _q(pct),
            "shortfall_price": None if price is None else _q(price), "currency": currency, "years": years}


def for_party(party, contract_id: str, as_of: Optional[date] = None) -> dict:
    """The parties read it; GEX staff read no amounts (Q5), as with cashflows."""
    from app.core import market_engine as me
    from app.core.market_engine import _refuse

    if party.is_admin:
        _refuse(403, "GEX_READS_NO_TERMS", "GEX staff read a contract's state and hashes, not its amounts.")
    conn = me._conn()
    try:
        who = record.parties(conn, contract_id)
        if party.company_id not in who["companies"]:
            _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
        return compute(conn, contract_id, as_of)
    finally:
        conn.close()


# ── G11 `first_deliveries_accepted`: evidence for the reviewer, not a verification ──
#
# The delivery record attaches its acceptance record as an evidence DOCUMENT on the project
# (evidence_documents, key first_deliveries_accepted): the delivery's events with their hashes,
# the certificate's sha256 and result, the acceptance basis and label, the chain head. The
# reviewer verifies the item, or does not; GEX verifies nothing (Attack A) and sets no status.

G11_KEY = "first_deliveries_accepted"


def acceptance_record(conn, delivery_id: str) -> Optional[dict]:
    d = record._row(conn, "SELECT d.*, c.contract_ref FROM deliveries d JOIN tb_contract c ON c.id = d.contract_id "
                          "WHERE d.id = ?", (delivery_id,))
    if d is None:
        return None
    evs = record._rows(conn, "SELECT seq, event_type, company_id, at, note, event_hash FROM tb_contract_event "
                             "WHERE delivery_id = ? ORDER BY seq", (delivery_id,))
    acc = [json.loads(e["note"]) for e in evs if e["event_type"] == "DELIVERY_ACCEPTED"]
    cert = [json.loads(e["note"]) for e in evs if e["event_type"] == "DELIVERY_FACT_CERTIFIED"]
    head = record._row(conn, "SELECT event_hash FROM tb_contract_event WHERE contract_id = ? ORDER BY seq DESC LIMIT 1",
                       (str(d["contract_id"]),))
    return {"record": "GEX delivery acceptance record", "schema": 1, "delivery_id": d["id"],
            "contract_ref": d["contract_ref"], "project_id": d["project_id"], "status": d["status"],
            "delivered_kg": None if d["delivered_kg"] is None else _q(Decimal(str(d["delivered_kg"]))),
            "acceptance": acc[-1] if acc else None,
            "certificate": {"document_sha256": cert[-1]["document_sha256"], "result": cert[-1]["result"]} if cert else None,
            "events": [{"seq": e["seq"], "event_type": e["event_type"], "company_id": e["company_id"],
                        "at": e["at"].isoformat(), "event_hash": e["event_hash"]} for e in evs],
            "contract_chain_head": head["event_hash"] if head else None,
            "verification": "NOT VERIFIED BY GEX: for the reviewer of G11 (Attack A)"}


def attach_g11_evidence(party, delivery_id: str) -> dict:
    """The seller (the project's owner) files the acceptance record as G11 evidence. Idempotent."""
    import hashlib
    import os
    from pathlib import Path

    from app.core import market_engine as me
    from app.core.db_backend import evidence_connection
    from app.core.market_engine import _refuse

    me._trader(party)
    conn = me._conn()
    try:
        d = record._row(conn, "SELECT seller_company_id, buyer_company_id, project_id, status FROM deliveries WHERE id = ?",
                        (delivery_id,))
        if d is None or party.company_id not in (d["seller_company_id"], d["buyer_company_id"]):
            _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
        if party.company_id != d["seller_company_id"]:
            _refuse(403, "DELIVERY_WRONG_PARTY", "The project's owner, the seller, files its G11 evidence.")
        if d["status"] not in COUNTED:
            _refuse(409, "DELIVERY_NOT_ACCEPTED", f"The delivery is {d['status']}: there is no acceptance to evidence.")
        rec = acceptance_record(conn, delivery_id)
    finally:
        conn.close()
    body = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    ev = evidence_connection(company_id=party.company_id)       # RLS: the owner files on its own project
    try:
        found = ev.execute("SELECT id FROM evidence_documents WHERE project_id = ? AND evidence_key = ? AND sha256 = ?",
                           (d["project_id"], G11_KEY, sha)).fetchone()
        if found is None:
            dest = Path(os.getenv("GEX_EVIDENCE_DOCS_DIR", "data/evidence_docs")) / d["project_id"] / G11_KEY
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"{sha}_delivery_{delivery_id}.json"
            path.write_bytes(body)
            ev.execute("INSERT INTO evidence_documents (project_id, evidence_key, filename, sha256, size_bytes, "
                       "stored_path, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (d["project_id"], G11_KEY, path.name, sha, len(body), str(path), party.user_id,
                        datetime.now(timezone.utc).isoformat()))
            ev.commit()
    finally:
        ev.close()
    return {"evidence_key": G11_KEY, "project_id": d["project_id"], "sha256": sha, "size_bytes": len(body),
            "label": "attached for the reviewer; not verified by GEX", "record": rec}
