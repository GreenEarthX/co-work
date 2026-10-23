"""
Market routes — /api/v1/market. Policy and every check: core/market_engine.py.

    GET  /listings/offers            anonymised open offers (every signed-in company)
    GET  /listings/rfqs              anonymised open RFQs
    POST /rfqs                       create an RFQ (buyer)
    GET  /rfqs/mine                  my RFQs
    POST /rfqs/{id}/status           draft->open|cancelled, open->withdrawn|expired
    POST /offers/{id}/open           list an offer; reserves its token
    POST /offers/{id}/withdraw       withdraw it; releases the token
    POST /matching/run               SUSPENDED (409) unless MARKET_AUTO_MATCHING — spec 2B
    POST /matches                    propose a match: my RFQ to a listing, or my listing to an RFQ
    POST /matches                    match one offer with one RFQ explicitly
    GET  /matches/mine               my matches, counterparty revealed
    POST /matches/{id}/accept        my side accepts; both sides -> agreed, token MATCHED
    POST /matches/{id}/decline
    POST /contracts                  contract from an agreed match
    GET  /contracts/mine
    POST /settlements                settlement for a contract (quantity only; the rest is derived)
    POST /settlements/{id}/confirm   seller confirms payment; token SETTLED, title to buyer
    GET  /trail/{correlation_id}     the event trail of one chain, for a party to it

The acting party is always the signed-in user and company from the token;
nothing in a request body says who acted. ABAC maps no resource for /market/*
(abac_middleware._extract_resource), so it authenticates and passes the request
on, and the engine authorises every call itself.
"""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core import market_engine as me

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


class RFQIn(BaseModel):
    molecule: str
    volume_mtpd: float = Field(..., gt=0)
    delivery_start: str
    delivery_end: str
    max_price_eur_kg: Optional[float] = None
    location: Optional[str] = None
    buyer_contact: Optional[str] = None
    compliance_requirements: Optional[list[str]] = None
    status: str = "open"


class RFQStatusIn(BaseModel):
    status: str


class MatchIn(BaseModel):
    offer_id: str
    rfq_id: str


class ContractIn(BaseModel):
    match_id: str
    delivery_terms: str = Field(..., min_length=1)
    payment_terms: str = Field(..., min_length=1)


class SettlementIn(BaseModel):
    contract_id: str
    settlement_type: str
    volume_kg: float = Field(..., gt=0)
    settlement_date: Optional[str] = None
    currency: str = "EUR"


class ConfirmIn(BaseModel):
    payment_reference: str = Field(..., min_length=1)


@router.get("/commodities")
def commodities(request: Request):
    _party(request)
    return {"commodities": _call(me.commodities)}


@router.get("/project-economics")
def project_economics(request: Request):
    """Marketplace records for the projects the caller may see (UNVERIFIED until confirmed)."""
    return _call(me.project_economics, _party(request))


@router.get("/listings/offers")
def offer_listings(request: Request, molecule: Optional[str] = Query(None)):
    return {"offers": _call(me.offer_listings, _party(request), molecule)}


@router.get("/listings/rfqs")
def rfq_listings(request: Request, molecule: Optional[str] = Query(None)):
    return {"rfqs": _call(me.rfq_listings, _party(request), molecule)}


@router.post("/rfqs", status_code=201)
def create_rfq(body: RFQIn, request: Request):
    return _call(me.create_rfq, _party(request), **body.model_dump())


@router.get("/rfqs/mine")
def my_rfqs(request: Request):
    return {"rfqs": _call(me.my_rfqs, _party(request))}


@router.post("/rfqs/{rfq_id}/status")
def rfq_status(rfq_id: str, body: RFQStatusIn, request: Request):
    return _call(me.transition_rfq, _party(request), rfq_id, body.status)


@router.post("/offers/{offer_id}/open")
def open_offer(offer_id: str, request: Request):
    return _call(me.open_offer, _party(request), offer_id)


@router.post("/offers/{offer_id}/withdraw")
def withdraw_offer(offer_id: str, request: Request):
    return _call(me.withdraw_offer, _party(request), offer_id)


@router.post("/matching/run")
def run_matching(request: Request):
    return _call(me.run_matching, _party(request))


@router.post("/matches", status_code=201)
def create_match(body: MatchIn, request: Request):
    return _call(me.create_match, _party(request), body.offer_id, body.rfq_id)


@router.get("/matches/mine")
def my_matches(request: Request):
    return {"matches": _call(me.my_matches, _party(request))}


@router.post("/matches/{match_id}/accept")
def accept_match(match_id: str, request: Request):
    return _call(me.accept_match, _party(request), match_id)


@router.post("/matches/{match_id}/decline")
def decline_match(match_id: str, request: Request):
    return _call(me.decline_match, _party(request), match_id)


@router.post("/contracts", status_code=201)
def create_contract(body: ContractIn, request: Request):
    return _call(me.create_contract, _party(request), body.match_id,
                 delivery_terms=body.delivery_terms, payment_terms=body.payment_terms)


@router.get("/contracts/mine")
def my_contracts(request: Request):
    return {"contracts": _call(me.my_contracts, _party(request))}


@router.post("/settlements", status_code=201)
def create_settlement(body: SettlementIn, request: Request):
    return _call(me.create_settlement, _party(request), body.contract_id,
                 settlement_type=body.settlement_type, volume_kg=body.volume_kg,
                 settlement_date=body.settlement_date, currency=body.currency)


@router.post("/settlements/{settlement_id}/confirm")
def confirm_settlement(settlement_id: str, body: ConfirmIn, request: Request):
    return _call(me.confirm_settlement, _party(request), settlement_id,
                 payment_reference=body.payment_reference)


@router.get("/trail/{correlation_id}")
def trail(correlation_id: str, request: Request):
    return {"correlation_id": correlation_id,
            "events": _call(me.trail_for, _party(request), correlation_id)}
