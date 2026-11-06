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


class AcceptIn(BaseModel):
    quantity: Optional[Decimal] = Field(default=None, gt=0)


class RFQIn(BaseModel):
    terms: TermsIn
    side: Literal["buy", "sell"]
    valid_until: datetime


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
                 valid_until=body.valid_until, visibility=body.visibility, invitees=body.invitees)


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


@router.post("/records/{contract_id}/confirm", status_code=201)
def request_confirmation(contract_id: str, request: Request):
    return _call(ob.request_confirmation, _party(request), contract_id)


@router.post("/records/{contract_id}/confirm/{request_id}/approve")
def approve_confirmation(contract_id: str, request_id: str, request: Request):
    return _call(ob.approve_confirmation, _party(request), contract_id, request_id)


@router.get("/records/{contract_id}/confirmations")
def confirmations(contract_id: str, request: Request):
    return {"confirmations": _call(ob.confirmations, _party(request), contract_id)}
