"""
Order book routes — /api/v1/trading-book (spec §9; M3). Policy: core/order_book.py.

    POST /terms/validate                         run V01–V14 on a terms payload; no write
    POST /orders                                 a draft one-sided order (no counterparty, D3)
    POST /orders/{id}/open                       freeze its terms; it can now be accepted
    POST /orders/{id}/cancel
    POST /orders/{id}/accept                     fill + draft contract, one locked transaction
    GET  /orders                                 mine, offered to me, open platform orders (anonymised)
    POST /rfqs, /rfqs/{id}/publish, GET /rfqs
    POST /rfqs/{id}/quotes                       an invited firm quote — the quoting party's acceptance (Q6)
    POST /rfqs/{id}/quotes/{order_id}/accept     the requester accepts: fill + draft contract, RFQ closed
    GET  /records/{id}                           the contract record: versions, chain, chain_intact, terms
    GET  /records/{id}/cashflows?as_party=       every flow priced, payer/receiver, signed for a party (M4)
    POST /records/{id}/confirm                   TRADE_CONFIRM, first pair of eyes
    POST /records/{id}/confirm/{request_id}/approve
    GET  /records/{id}/confirmations

Where the names differ from the spec: the record is served at /records/{id},
not /contracts/{id}, because /contracts/{id} still serves the JTI book on this
prefix until M6 drops it (trading_book/api.py).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import market_engine as me
from app.core import order_book as ob
from app.trading_book.terms import TermsIn

router = APIRouter()


def _party(request: Request) -> me.Party:
    try:
        return me.Party.from_payload(getattr(request.state, "user_payload", None) or {})
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _call(fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


class ValidateIn(BaseModel):
    terms: TermsIn
    kind: Literal["order", "contract"] = "order"


class OrderIn(BaseModel):
    terms: TermsIn
    side: Literal["buy", "sell"]
    order_type: Literal["firm", "indicative"] = "firm"
    all_or_nothing: bool = False
    min_fill_quantity: Optional[Decimal] = Field(default=None, gt=0)
    valid_until: datetime
    visibility: Literal["private", "invited", "platform"] = "platform"
    invitees: list[str] = Field(default_factory=list)       # company ids
    token_id: Optional[str] = None                          # G-25: a firm all-or-nothing SELL of one own token


class AcceptIn(BaseModel):
    quantity: Optional[Decimal] = Field(default=None, gt=0)


class RFQIn(BaseModel):
    terms: TermsIn
    side: Literal["buy", "sell"]
    valid_until: datetime


class PartySignature(BaseModel):
    """The party's own signature over a prepared event (Phase 5): ed25519 over
    "GEX-CONTRACT-EVENT-v1:" + event_hash, by an ACTIVE key of the party's company."""
    scheme: Literal["ed25519"] = "ed25519"
    signer_key_ref: str
    signature: str                                  # base64
    at: str                                         # the prepared event's time, as returned
    event_hash: str                                 # the prepared event's hash, as signed


class SignedAct(BaseModel):
    """Optional on a confirmation or dispute. `signature_intent: true` prepares the
    event and returns its hash to sign, writing nothing; `signature` then signs it."""
    signature_intent: bool = False
    signature: Optional[PartySignature] = None


class KeyIn(BaseModel):
    public_key: str                                 # ed25519, 32 bytes, base64
    label: Optional[str] = None


class RevokeIn(BaseModel):
    reason: str


class QuoteIn(BaseModel):
    terms: TermsIn
    valid_until: datetime


@router.post("/terms/validate")
def validate_terms(body: ValidateIn, request: Request):
    _party(request)
    failed = ob.validate_terms(body.terms, body.kind)
    return {"valid": not failed, "failed_rules": failed}


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, request: Request):
    return _call(ob.create_order, _party(request), body.terms, side=body.side, order_type=body.order_type,
                 all_or_nothing=body.all_or_nothing, min_fill_quantity=body.min_fill_quantity,
                 valid_until=body.valid_until, visibility=body.visibility, invitees=body.invitees,
                 token_id=body.token_id)


@router.post("/orders/{order_id}/open")
def open_order(order_id: str, request: Request):
    return _call(ob.open_order, _party(request), order_id)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, request: Request):
    return _call(ob.cancel_order, _party(request), order_id)


@router.post("/orders/{order_id}/accept", status_code=201)
def accept_order(order_id: str, request: Request, body: Optional[AcceptIn] = None):
    return _call(ob.accept_order, _party(request), order_id, (body or AcceptIn()).quantity)


@router.get("/orders")
def list_orders(request: Request):
    return {"orders": _call(ob.list_orders, _party(request))}


@router.post("/rfqs", status_code=201)
def create_rfq(body: RFQIn, request: Request):
    return _call(ob.create_rfq, _party(request), body.terms, side=body.side, valid_until=body.valid_until)


@router.post("/rfqs/{rfq_id}/publish")
def publish_rfq(rfq_id: str, request: Request):
    return _call(ob.publish_rfq, _party(request), rfq_id)


@router.get("/rfqs")
def list_rfqs(request: Request):
    return {"rfqs": _call(ob.list_rfqs, _party(request))}


@router.post("/rfqs/{rfq_id}/quotes", status_code=201)
def quote(rfq_id: str, body: QuoteIn, request: Request):
    return _call(ob.quote, _party(request), rfq_id, body.terms, valid_until=body.valid_until)


@router.post("/rfqs/{rfq_id}/quotes/{order_id}/accept", status_code=201)
def accept_quote(rfq_id: str, order_id: str, request: Request):
    return _call(ob.accept_quote, _party(request), rfq_id, order_id)


@router.get("/records/{contract_id}")
def get_record(contract_id: str, request: Request):
    return _call(ob.get_contract, _party(request), contract_id)


@router.get("/records/{contract_id}/cashflows")
def record_cashflows(contract_id: str, request: Request, as_party: Optional[str] = None):
    return _call(ob.contract_cashflows, _party(request), contract_id, as_party)


@router.post("/records/{contract_id}/confirm", status_code=201)
def request_confirmation(contract_id: str, request: Request):
    return _call(ob.request_confirmation, _party(request), contract_id)


@router.post("/records/{contract_id}/confirm/{request_id}/approve")
def approve_confirmation(contract_id: str, request_id: str, request: Request, body: Optional[SignedAct] = None):
    from app.trading_book import record

    party, body = _party(request), body or SignedAct()
    with record.party_act(party.company_id, signature=body.signature.model_dump() if body.signature else None,
                          prepare=body.signature_intent):
        try:
            return _call(ob.approve_confirmation, party, contract_id, request_id, prepare=body.signature_intent)
        except record.SigningIntent as intent:
            return {"signature_intent": intent.intent}


# ── a company's signing keys (Phase 5) ──────────────────────────────────────

def _keys(fn, *args):
    from app.core import party_keys as pk

    try:
        return fn(*args)
    except pk.KeyRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _payload(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(401, {"code": "AUTHENTICATION_REQUIRED", "message": "Sign in first."})
    return {**payload, "user_id": payload.get("user_id") or payload.get("sub")}


@router.get("/party-keys")
def list_party_keys(request: Request):
    from app.core import party_keys as pk

    return {"keys": _keys(pk.list_keys, _payload(request))}


@router.post("/party-keys", status_code=201)
def propose_party_key(body: KeyIn, request: Request):
    from app.core import party_keys as pk

    return _keys(pk.propose, _payload(request), body.public_key, body.label)


@router.post("/party-keys/{key_ref}/activate")
def activate_party_key(key_ref: str, request: Request):
    from app.core import party_keys as pk

    return _keys(pk.activate, _payload(request), key_ref)


@router.post("/party-keys/{key_ref}/reject")
def reject_party_key(key_ref: str, request: Request):
    from app.core import party_keys as pk

    return _keys(pk.reject, _payload(request), key_ref)


@router.post("/party-keys/{key_ref}/revoke")
def revoke_party_key(key_ref: str, body: RevokeIn, request: Request):
    from app.core import party_keys as pk

    return _keys(pk.revoke, _payload(request), key_ref, body.reason)


@router.get("/records/{contract_id}/anchors")
def record_anchors(contract_id: str, request: Request):
    """The contract's chain with its ledger anchors (Phase 4): hashes, types, times and
    ledger references; a buyer also gets the Merkle proof of its own sub-leg."""
    from app.core import ledger_anchor

    party = _party(request)
    return _call(ledger_anchor.chain_for, party.company_id, party.is_admin, contract_id)


@router.get("/records/{contract_id}/confirmations")
def confirmations(contract_id: str, request: Request):
    return {"confirmations": _call(ob.confirmations, _party(request), contract_id)}


# ── deliveries (GreenMesh Phase 2, Step 2; alembic 103; core/delivery_record.py) ──
#
#   POST /records/{id}/deliveries            the seller schedules (flow, draws, window, mode, route)
#   GET  /records/{id}/deliveries            the deliveries the caller may read
#   GET  /deliveries/{id}                    one delivery, its draws and its events
#   POST /deliveries/{id}/dispatch           the seller: dispatched kg and time  -> IN_TRANSIT
#   POST /deliveries/{id}/receipt            the buyer: received kg and time     -> ARRIVED
#   POST /deliveries/{id}/inspection         either party                        -> QUALITY_VERIFICATION
#   POST /deliveries/{id}/dispute            either party, with a reason         -> DISPUTED
#   POST /deliveries/{id}/documents          a party files a document (multipart); GEX hashes it
#   POST /deliveries/{id}/unloading          the buyer, DPU, naming its unloading record (risk passes)
# Acceptance, title and settlement come with Step 3 (quality before title).

class PlaceIn(BaseModel):
    locode: Optional[str] = None
    facility_id: Optional[str] = None


class FlowRefIn(BaseModel):
    leg_seq: int = Field(ge=1)
    flow_seq: int = Field(ge=1)


class DrawIn(BaseModel):
    token_id: str
    kg: Decimal = Field(gt=0)


class ScheduleIn(BaseModel):
    flow: FlowRefIn
    draws: list[DrawIn] = Field(min_length=1)
    window_start: datetime
    window_end: datetime
    transport_mode: str
    origin: PlaceIn
    destination: PlaceIn


class DispatchIn(BaseModel):
    dispatched_kg: Decimal
    dispatched_at: datetime


class ReceiptIn(BaseModel):
    delivered_kg: Decimal
    arrived_at: datetime


class InspectionIn(BaseModel):
    note: Optional[str] = None


class DisputeIn(BaseModel):
    reason: str


class UnloadingIn(BaseModel):
    document_sha256: str
    unloaded_at: datetime


class InspectorIn(BaseModel):
    inspector_company_id: str
    document_sha256: str


class ConfirmIn(BaseModel):
    act: Literal["INSPECTOR_AGREED", "WAIVER_CONFIRMED", "RESOLUTION_CONFIRMED"]


class ResolutionIn(BaseModel):
    outcome: Literal["ACCEPTED", "REJECTED"]
    document_sha256: str


class CertifyIn(BaseModel):
    document_sha256: str
    measured: dict[str, str]


class WaiverIn(BaseModel):
    document_sha256: str


class RejectIn(BaseModel):
    reason: str


class DocumentsIn(BaseModel):
    document_sha256: str


@router.post("/records/{contract_id}/deliveries", status_code=201)
def schedule_delivery(contract_id: str, body: ScheduleIn, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.schedule, _party(request), contract_id, body.model_dump())


@router.get("/records/{contract_id}/deliveries")
def list_deliveries(contract_id: str, request: Request):
    from app.core import delivery_record as dr

    return {"deliveries": _call(dr.deliveries_for, _party(request), contract_id)}


@router.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: str, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.get_delivery, _party(request), delivery_id)


@router.post("/deliveries/{delivery_id}/dispatch")
def dispatch_delivery(delivery_id: str, body: DispatchIn, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.dispatch, _party(request), delivery_id, body.dispatched_kg, body.dispatched_at)


@router.post("/deliveries/{delivery_id}/receipt")
def receive_delivery(delivery_id: str, body: ReceiptIn, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.receive, _party(request), delivery_id, body.delivered_kg, body.arrived_at)


@router.post("/deliveries/{delivery_id}/inspection")
def request_inspection(delivery_id: str, request: Request, body: Optional[InspectionIn] = None):
    from app.core import delivery_record as dr

    return _call(dr.request_inspection, _party(request), delivery_id, (body or InspectionIn()).note)


@router.post("/deliveries/{delivery_id}/dispute")
def dispute_delivery(delivery_id: str, body: DisputeIn, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.dispute, _party(request), delivery_id, body.reason)


@router.post("/deliveries/{delivery_id}/documents", status_code=201)
async def file_delivery_document(delivery_id: str, request: Request):
    """Multipart: `kind` and `file`. GEX computes the sha256 (Step 3; alembic 106)."""
    from app.core import delivery_documents as docs

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(422, {"code": "DELIVERY_DOCUMENT_EMPTY", "message": "Send the document as `file`."})
    content = await upload.read()
    return _call(docs.file_document, _party(request), delivery_id, str(form.get("kind") or ""),
                 getattr(upload, "filename", None) or "document", content)


@router.post("/deliveries/{delivery_id}/unloading")
def record_unloading(delivery_id: str, body: UnloadingIn, request: Request):
    from app.core import delivery_record as dr

    return _call(dr.record_unloading, _party(request), delivery_id, body.document_sha256, body.unloaded_at)


# Quality before title (Step 3, sub-step 3; alembic 107; core/delivery_inspection.py)
#   POST /deliveries/{id}/inspector                       a party proposes an inspector (appointment on file)
#   POST /deliveries/{id}/confirmations                   the other party's first pair of eyes (act)
#   POST /deliveries/{id}/confirmations/{request}/approve its second pair of eyes; on quorum the act is written
#   POST /deliveries/{id}/certificate                     the agreed inspector: certificate + measured values
#   POST /deliveries/{id}/waiver                          a party proposes accepting a FAIL certificate
#   POST /deliveries/{id}/rejection                       the buyer rejects on a FAIL certificate

@router.post("/deliveries/{delivery_id}/inspector")
def propose_inspector(delivery_id: str, body: InspectorIn, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.propose_inspector, _party(request), delivery_id, body.inspector_company_id, body.document_sha256)


@router.post("/deliveries/{delivery_id}/confirmations", status_code=201)
def request_delivery_confirmation(delivery_id: str, body: ConfirmIn, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.request_confirmation, _party(request), delivery_id, body.act)


@router.post("/deliveries/{delivery_id}/confirmations/{request_id}/approve")
def approve_delivery_confirmation(delivery_id: str, request_id: str, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.approve_confirmation, _party(request), delivery_id, request_id)


@router.post("/deliveries/{delivery_id}/certificate")
def certify_delivery(delivery_id: str, body: CertifyIn, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.certify, _party(request), delivery_id, body.document_sha256, body.measured)


@router.post("/deliveries/{delivery_id}/waiver")
def propose_waiver(delivery_id: str, body: WaiverIn, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.propose_waiver, _party(request), delivery_id, body.document_sha256)


@router.post("/deliveries/{delivery_id}/rejection")
def reject_delivery(delivery_id: str, body: RejectIn, request: Request):
    from app.core import delivery_inspection as di

    return _call(di.reject, _party(request), delivery_id, body.reason)


@router.post("/deliveries/{delivery_id}/resolution")
def propose_resolution(delivery_id: str, body: ResolutionIn, request: Request):
    """A party proposes how a dispute ends (108); the other confirms via /confirmations."""
    from app.core import delivery_inspection as di

    return _call(di.propose_resolution, _party(request), delivery_id, body.outcome, body.document_sha256)


@router.post("/deliveries/{delivery_id}/documents-acknowledged")
def acknowledge_documents(delivery_id: str, body: DocumentsIn, request: Request):
    """The buyer acknowledges the B/L or delivery order on file (109); title may then pass."""
    from app.core import delivery_title as dt

    return _call(dt.acknowledge_documents, _party(request), delivery_id, body.document_sha256)


@router.get("/records/{contract_id}/take-or-pay")
def take_or_pay(contract_id: str, request: Request, as_of: Optional[str] = None):
    """Take-or-pay shortfall per contract year from the confirmed terms (Phase 2 Step 4).
    GEX computes; it does not invoice. A missing term gives no figure."""
    from datetime import date as _date

    from app.core import take_or_pay as top

    when = _date.fromisoformat(as_of) if as_of else None
    return _call(top.for_party, _party(request), contract_id, when)


@router.post("/deliveries/{delivery_id}/g11-evidence", status_code=201)
def attach_g11_evidence(delivery_id: str, request: Request):
    """The seller files the delivery's acceptance record as G11 `first_deliveries_accepted`
    evidence for the reviewer. GEX verifies nothing (Attack A)."""
    from app.core import take_or_pay as top

    return _call(top.attach_g11_evidence, _party(request), delivery_id)
