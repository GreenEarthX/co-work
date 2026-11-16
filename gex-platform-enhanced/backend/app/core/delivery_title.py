"""
Title transfer and the token split (GreenMesh Phase 2 Step 3, sub-step 5; alembic 109;
amendment B1, B2; rulings R2, R3; decision T1 open). Stops before SETTLED.

Title follows the contract's title clause (`deliveries.title_passes`, read from the confirmed
terms at scheduling). GEX moves the token holder at the LATER of ACCEPTED and the clause's
trigger (T1, as proposed: "hold the token until ACCEPTED"):

    ON_ACCEPTANCE          at ACCEPTED
    ON_RISK                at ACCEPTED, once risk has passed
    ON_DOCUMENT_TRANSFER   at ACCEPTED, once the buyer acknowledges the B/L or delivery order
    ON_PAYMENT_IN_FULL     not built (payment in full is recorded with settlement, after Step 3)

`maybe_transfer` is called after every act that can complete the pair (acceptance, the
document acknowledgement). When legal title under the clause passed before acceptance
(ON_RISK with risk passed at dispatch, ON_DOCUMENT_TRANSFER acknowledged before ACCEPTED), the
event says "legal title clause precedes acceptance; token held until ACCEPTED". When title is
recorded before risk has passed (invariant 4), the event says so; it is not refused.

The quantity: each token's DRAW on the delivery (the custody withdrawal the delivery carries).
Draws reference the contract's token; once that token is SPLIT, the seller's current part is
its seller-held descendant (`current_part`). For the whole of a part: only the holder moves.
For less: the part goes to SPLIT and two children are made (`parent_token_id`): the drawn kg
(holder the buyer) and the remainder (holder the seller); kg exactly, decimal, nothing rounded
away (109 checks the sum at commit); the certificate id and custody lineage are inherited
unchanged; `energy_mj` and `tokenised_mtpd` are apportioned by the same ratio and are DECLARED
(R3: floats, never verified). One TITLE_TRANSFERRED event carries every move.

Token state: the buyer's part becomes SETTLED ("molecule delivered, claim live and claimable by
the holder", tokens_sqlite) at title, from MATCHED; the seller's remainder keeps the parent's
state. On a contract with deliveries the market's settlement no longer moves token or holder
(R2), so this is where a delivered molecule's claim reaches its holder.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Optional

from app.core import delivery_record as dr
from app.core.market_engine import _refuse
from app.trading_book import record

TITLE_ACTOR = "system:title"
COPIED = ("capacity_id", "delivery_start", "delivery_end", "compliance_certifications", "correlation_id",
          "sovereign_provenance", "molecule", "production_window_start", "production_window_end",
          "certification_pathway", "carbon_intensity_gco2e_mj", "mass_balance_lot_id", "provenance_hash",
          "verification_state", "lifecycle_state", "production_pathway", "physical_form", "specification_standard")
T1_LABEL = "legal title clause precedes acceptance; token held until ACCEPTED"


def token_kg(conn, token_id: str) -> Decimal:
    return Decimal(str(record._row(conn, "SELECT app_token_kg(?) AS kg", (token_id,))["kg"]))


def current_part(conn, token_id: str, seller: str) -> dict:
    """The seller-held part of a (possibly split) contract token: follow SPLIT parents down the
    remainder children until a token that is not SPLIT."""
    t = record._row(conn, "SELECT * FROM tokens WHERE id = ? FOR UPDATE", (token_id,))
    while t and t["lifecycle_state"] == "SPLIT":
        t = record._row(conn, "SELECT t.* FROM tokens t JOIN token_split s ON s.child_token_id = t.id "
                              "WHERE s.parent_token_id = ? AND s.holder_company_id = ? FOR UPDATE OF t", (t["id"], seller))
    if t is None:
        _refuse(409, "TOKEN_NO_SELLER_PART", f"Token {token_id} has no part left with the seller.")
    return t


def root_of(conn, token_id: str) -> str:
    t = token_id
    while True:
        p = record._row(conn, "SELECT parent_token_id FROM tokens WHERE id = ?", (t,))
        if p is None or p["parent_token_id"] is None:
            return t
        t = p["parent_token_id"]


def lineage(conn, token_id: str) -> dict:
    """Custody lineage of a token, through its root: lot, period, and the period's RFNBO result."""
    root = root_of(conn, token_id)
    r = record._row(conn, "SELECT t.mass_balance_lot_id AS lot_id, l.period_id, p.status AS period_status, "
                          "p.statement -> 'rfnbo_correlation' ->> 'status' AS rfnbo FROM tokens t "
                          "LEFT JOIN mass_balance_lots l ON l.lot_id = t.mass_balance_lot_id "
                          "LEFT JOIN coc_period p ON p.period_id = l.period_id WHERE t.id = ?", (root,))
    return {"root_token_id": root, **(r or {})}


def _trigger_met(conn, d: dict) -> tuple[bool, Optional[str]]:
    passes = d["title_passes"]
    if passes is None:
        return False, "MISSING: the confirmed terms carry no title clause, so title cannot pass"
    if passes == "ON_PAYMENT_IN_FULL":
        return False, "ON_PAYMENT_IN_FULL: payment in full is recorded with settlement, after Step 3"
    if passes == "ON_RISK" and not dr._row(conn, "SELECT 1 AS x FROM tb_contract_event WHERE delivery_id = ? AND "
                                                 "event_type = 'DELIVERY_FACT_RISK_PASSED'", (d["id"],)):
        return False, "ON_RISK: risk has not passed"
    if passes == "ON_DOCUMENT_TRANSFER" and not dr._row(conn, "SELECT 1 AS x FROM tb_contract_event WHERE delivery_id = ? "
                                                              "AND event_type = 'DELIVERY_FACT_DOCUMENT_TRANSFERRED'", (d["id"],)):
        return False, "ON_DOCUMENT_TRANSFER: the buyer has not acknowledged the documents"
    return True, None


def _seq_of(conn, delivery_id: str, event_type: str) -> Optional[int]:
    r = dr._row(conn, "SELECT min(seq) AS s FROM tb_contract_event WHERE delivery_id = ? AND event_type = ?",
                (delivery_id, event_type))
    return r["s"] if r else None


def maybe_transfer(conn, delivery_id: str) -> Optional[dict]:
    """Transfer title now if the delivery is ACCEPTED and its title clause is met. In the
    caller's transaction (operator connection). Returns the event, or None."""
    d = dr._delivery(conn, delivery_id, lock=True)
    if d["status"] != "ACCEPTED":
        return None
    met, _why = _trigger_met(conn, d)
    if not met:
        return None
    seller, buyer = d["seller_company_id"], d["buyer_company_id"]
    accepted_seq = _seq_of(conn, delivery_id, "DELIVERY_ACCEPTED")
    risk_seq = _seq_of(conn, delivery_id, "DELIVERY_FACT_RISK_PASSED")
    doc_seq = _seq_of(conn, delivery_id, "DELIVERY_FACT_DOCUMENT_TRANSFERRED")
    labels = []
    if (d["title_passes"] == "ON_RISK" and risk_seq and risk_seq < accepted_seq) or \
            (d["title_passes"] == "ON_DOCUMENT_TRANSFER" and doc_seq and doc_seq < accepted_seq):
        labels.append(T1_LABEL)
    if risk_seq is None:
        labels.append("title recorded before risk has passed")          # invariant 4: labelled, not refused
    plan = []
    for draw in dr._rows(conn, "SELECT token_id, kg FROM delivery_draw WHERE delivery_id = ? ORDER BY token_id",
                         (delivery_id,)):
        part = current_part(conn, draw["token_id"], seller)
        whole, kg = token_kg(conn, part["id"]), Decimal(str(draw["kg"]))
        if kg > whole:
            _refuse(409, "TOKEN_PART_TOO_SMALL", f"Token {part['id']} holds {whole} kg; the delivery drew {kg} kg.")
        if part["lifecycle_state"] != "MATCHED":
            _refuse(409, "TOKEN_STATE", f"Token {part['id']} is {part['lifecycle_state']}; title moves a MATCHED token.")
        if kg == whole:
            plan.append({"token_id": draw["token_id"], "part": part["id"], "kg": str(kg), "move": "HOLDER"})
        else:
            stem = root_of(conn, part["id"])
            plan.append({"token_id": draw["token_id"], "part": part["id"], "kg": str(kg), "move": "SPLIT",
                         "to_buyer": f"{stem}-T{uuid.uuid4().hex[:8]}", "to_seller": f"{stem}-R{uuid.uuid4().hex[:8]}",
                         "remainder_kg": str(whole - kg)})
    ev = dr._transition(conn, d, "TITLE_TRANSFERRED", None, TITLE_ACTOR, {
        "title_passes": d["title_passes"], "labels": labels, "transfers": plan, "buyer": buyer, "seller": seller})
    for p in plan:
        if p["move"] == "HOLDER":
            conn.execute("UPDATE tokens SET holder_company_id = ?, lifecycle_state = 'SETTLED' WHERE id = ?",
                         (buyer, p["part"]))
            continue
        parent = dr._row(conn, "SELECT * FROM tokens WHERE id = ?", (p["part"],))
        whole = token_kg(conn, p["part"])
        for child, kg, holder in ((p["to_buyer"], Decimal(p["kg"]), buyer),
                                  (p["to_seller"], Decimal(p["remainder_kg"]), seller)):
            ratio = kg / whole
            energy = None if parent["energy_mj"] is None else float(Decimal(str(parent["energy_mj"])) * ratio)
            rate = None if parent["tokenised_mtpd"] is None else float(Decimal(str(parent["tokenised_mtpd"])) * ratio)
            cols = ", ".join(COPIED)
            conn.execute(f"INSERT INTO tokens (id, parent_token_id, holder_company_id, energy_mj, tokenised_mtpd, "
                         f"created_at, {cols}) SELECT ?, id, ?, ?, ?, ?, {cols} FROM tokens WHERE id = ?",
                         (child, holder, energy, rate, _now_iso(), p["part"]))
            conn.execute("INSERT INTO token_split (delivery_id, parent_token_id, child_token_id, kg, holder_company_id, "
                         "event_hash) VALUES (?, ?, ?, ?, ?, ?)", (delivery_id, p["part"], child, kg, holder, ev["event_hash"]))
        conn.execute("UPDATE tokens SET lifecycle_state = 'SETTLED' WHERE id = ?", (p["to_buyer"],))
        conn.execute("UPDATE tokens SET lifecycle_state = 'SPLIT' WHERE id = ?", (p["part"],))
    return ev


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def acknowledge_documents(party, delivery_id: str, document_sha256: str) -> dict:
    """The buyer acknowledges the B/L or delivery order on file (ON_DOCUMENT_TRANSFER)."""
    from app.core import delivery_documents as docs

    company = dr._party_company(party)
    conn = dr._conn()
    try:
        def go():
            d = dr._delivery(conn, delivery_id, lock=True)
            if company not in (d["seller_company_id"], d["buyer_company_id"]):
                _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
            if company != d["buyer_company_id"]:
                _refuse(403, "DELIVERY_WRONG_PARTY", "The buyer acknowledges the documents.")
            doc = dr._row(conn, "SELECT * FROM delivery_document WHERE delivery_id = ? AND sha256 = ? AND kind IN "
                                "('BILL_OF_LADING', 'DELIVERY_ORDER')", (delivery_id, document_sha256))
            if doc is None:
                docs.on_file(conn, delivery_id, "BILL_OF_LADING", document_sha256)       # refuses, naming it
            v = record.current_version(conn, str(d["contract_id"]))
            ev = record.append_event(conn, str(d["contract_id"]), "DELIVERY_FACT_DOCUMENT_TRANSFERRED", party.user_id,
                                     company, version_id=str(v["id"]), delivery_id=delivery_id, note=dr._note(
                                         delivery=delivery_id, fact="DOCUMENT_TRANSFERRED", kind=doc["kind"],
                                         document_sha256=doc["sha256"].strip()))
            maybe_transfer(conn, delivery_id)
            return ev
        dr._commit(conn, go)
    finally:
        conn.close()
    return dr.get_delivery(party, delivery_id)


def title_view(conn, d: dict, events: list[dict]) -> dict:
    t = next((json.loads(e["note"]) for e in events if e["event_type"] == "DELIVERY_TITLE_TRANSFERRED"), None)
    if t:
        return {"transferred": True, "title_passes": t.get("title_passes"), "labels": t.get("labels", []),
                "transfers": t.get("transfers", [])}
    met, why = _trigger_met(conn, d)
    return {"transferred": False, "title_passes": d.get("title_passes"),
            "waiting_for": why or ("ACCEPTED" if d["status"] != "ACCEPTED" else None)}
