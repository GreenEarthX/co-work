"""
Marketplace API Routes (SQLite)
Create and manage offers from tokenized capacity
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from enum import Enum
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import json
import os
import uuid
from datetime import datetime, timezone

# EVENT SYSTEM IMPORTS
from app.core.event_store import append_event
from app.core.config import settings

router = APIRouter()

# Database path
DB_PATH = settings.SQLITE_DB_PATH

def get_db_connection():
    """
    PostgreSQL only (JML, 2026-10-23): no SQLite fallback. The shim sets the RLS
    tenant context from the bound caller.
    """
    from app.core.db_backend import market_connection, market_is_postgres, require_postgres

    require_postgres(market_is_postgres(), "The marketplace", "MARKET_DB_BACKEND")
    return market_connection()


# ═══════════════════════════════════════════════════════════════
# ENUMS — Marketplace v4.0 listing schema
# ═══════════════════════════════════════════════════════════════

class DeliveryType(str, Enum):
    SPOT = "SPOT"
    FORWARD = "FORWARD"

class DeliveryBasis(str, Enum):
    EXW = "EXW"
    FOB = "FOB"
    DAP = "DAP"
    CIF = "CIF"
    DELIVERED = "DELIVERED"

class PriceBasis(str, Enum):
    FIXED = "FIXED"
    INDEXED = "INDEXED"
    FORMULA = "FORMULA"

class ESGTier(str, Enum):
    STANDARD = "STANDARD"
    VERIFIED = "VERIFIED"
    SOVEREIGN = "SOVEREIGN"

class ListingState(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    RESERVED = "RESERVED"
    MATCHED = "MATCHED"
    SETTLED = "SETTLED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"

# Valid listing state transitions
LISTING_TRANSITIONS: dict[ListingState, list[ListingState]] = {
    ListingState.DRAFT:    [ListingState.OPEN, ListingState.WITHDRAWN],
    ListingState.OPEN:     [ListingState.RESERVED, ListingState.MATCHED, ListingState.EXPIRED, ListingState.WITHDRAWN],
    ListingState.RESERVED: [ListingState.MATCHED, ListingState.OPEN, ListingState.WITHDRAWN],
    ListingState.MATCHED:  [ListingState.SETTLED, ListingState.WITHDRAWN],
    ListingState.SETTLED:  [],
    ListingState.EXPIRED:  [],
    ListingState.WITHDRAWN: [],
}


# Schemas
class OfferCreate(BaseModel):
    token_id: str
    volume_mtpd: float
    price_eur_kg: float
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    offer_type: str = 'indicative'  # 'indicative' or 'firm'
    # Sovereign provenance (inherited from token or overridden)
    country_of_origin: Optional[str] = None     # ISO-3166-1 alpha-2
    dfi_funded: Optional[bool] = None           # DFI/concessional backed
    sovereign_cert_scheme: Optional[str] = None # RED_III, 45V, RFNBO, etc.
    esg_score: Optional[float] = None           # 0-100
    # v4.0 marketplace fields
    delivery_type: Optional[str] = "SPOT"
    delivery_basis: Optional[str] = None
    price_basis: Optional[str] = None
    certification_pathway_required: Optional[List[str]] = None
    min_order_kg: Optional[float] = None
    esg_tier: Optional[str] = None
    listing_state: Optional[str] = "DRAFT"

class OfferResponse(BaseModel):
    id: str
    token_id: str
    molecule: str
    volume_mtpd: float
    price_eur_kg: float
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    status: str
    offer_type: str
    country_of_origin: Optional[str] = None
    dfi_funded: Optional[bool] = None
    sovereign_cert_scheme: Optional[str] = None
    esg_score: Optional[float] = None
    created_at: str
    correlation_id: Optional[str] = None  # NEW: Inherited from token
    # v4.0 marketplace fields
    delivery_type: Optional[str] = "SPOT"
    delivery_basis: Optional[str] = None
    price_basis: Optional[str] = None
    certification_pathway_required: Optional[List[str]] = None
    min_order_kg: Optional[float] = None
    esg_tier: Optional[str] = None
    listing_state: Optional[str] = "DRAFT"


class ListingTransition(BaseModel):
    new_state: str
    changed_by: str = "system"
    justification: str = ""


def _market_party(request: Request):
    from app.core import market_engine as me
    try:
        return me.Party.from_payload(getattr(request.state, "user_payload", None) or {})
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _market_call(fn, *args, **kwargs):
    from app.core import market_engine as me
    try:
        return fn(*args, **kwargs)
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


@router.post("/offers", response_model=OfferResponse, status_code=201)
async def create_offer(offer: OfferCreate, request: Request):
    """
    Create marketplace offer from token
    EVENT-DRIVEN: Inherits correlation_id from token for chain of custody
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify token exists and get details WITH correlation_id
        cursor.execute("""
            SELECT t.*, c.molecule, c.project_name, c.project_id AS capacity_project_id, t.correlation_id
            FROM tokens t
            JOIN capacities c ON t.capacity_id = c.id
            WHERE t.id = ?
        """, (offer.token_id,))
        token = cursor.fetchone()
        
        if not token:
            conn.close()
            raise HTTPException(status_code=404, detail="Token not found")

        # Only the project's owner offers its token; GEX trades nothing (2026-10-23).
        from app.core import market_engine as me
        party = _market_party(request)
        if party.is_admin or me.seller_company(token['capacity_project_id']) != party.company_id:
            conn.close()
            raise HTTPException(status_code=403, detail={"code": "NOT_YOUR_TOKEN",
                                "message": "Only the company that owns the project can offer its token."})
        conn.close()
        if offer.volume_mtpd > (token['tokenised_mtpd'] or 0):
            raise HTTPException(status_code=400, detail=f"Cannot offer {offer.volume_mtpd} MTPD. "
                                                        f"Available: {token['tokenised_mtpd']} MTPD")
        # Phase 3 (alembic 087): a listing is a firm SELL order of the one contract model.
        return _market_call(me.create_listing, party, dict(token), volume_mtpd=offer.volume_mtpd,
                            price_eur_kg=offer.price_eur_kg, delivery_start=offer.delivery_start,
                            delivery_end=offer.delivery_end, location=offer.location, offer_type=offer.offer_type,
                            delivery_type=offer.delivery_type, delivery_basis=offer.delivery_basis,
                            price_basis=offer.price_basis,
                            certification_pathway_required=offer.certification_pathway_required,
                            min_order_kg=offer.min_order_kg, esg_tier=offer.esg_tier,
                            open_now=(offer.listing_state or "DRAFT").upper() == "OPEN")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create offer: {str(e)}")


@router.get("/offers", response_model=dict)
async def list_offers(request: Request, molecule: Optional[str] = None, status: Optional[str] = None,
                      listing_state: Optional[str] = None):
    """The caller's own listings (GEX: all), from the order model (alembic 087). The
    open market is GET /api/v1/market/listings/offers, anonymised."""
    from app.core import market_engine as me
    rows = _market_call(me.my_listings, _market_party(request))
    rows = [r for r in rows if (not molecule or r["molecule"] == molecule) and (not status or r["status"] == status)
            and (not listing_state or r["listing_state"] == listing_state)]
    return {"offers": rows}


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(offer_id: str, request: Request):
    from app.core import market_engine as me
    return _market_call(me.my_listing, _market_party(request), offer_id)


@router.patch("/offers/{offer_id}/status", status_code=409)
async def update_offer_status(offer_id: str, status: str):
    """Retired 2026-10-23: it set 'matched' or 'active' with no token moving and no
    record. Listing state changes go through POST /offers/{id}/transition."""
    raise HTTPException(status_code=409, detail={"code": "USE_TRANSITION",
                        "message": "Change a listing through POST /offers/{id}/transition."})


@router.post("/offers/{offer_id}/transition", status_code=200)
async def transition_listing(offer_id: str, transition: ListingTransition, request: Request):
    """
    The seller opens or withdraws its listing; the market engine does the rest.
      DRAFT -> OPEN               reserves the token (MINTED -> RESERVED)
      DRAFT|OPEN -> WITHDRAWN     releases it, cancels pending matches
      DRAFT|OPEN -> EXPIRED       the same, recorded as expiry
    RESERVED, MATCHED and SETTLED are set by the market (both parties accepting a
    match, a confirmed settlement), never by hand — that was how a listing could
    say MATCHED while its token stayed MINTED (gap register G-02).
    """
    from app.core import market_engine as me
    party = _market_party(request)
    target = (transition.new_state or "").upper()
    if target == "OPEN":
        row = _market_call(me.open_offer, party, offer_id)
    elif target in ("WITHDRAWN", "EXPIRED"):
        row = _market_call(me.withdraw_offer, party, offer_id, expire=target == "EXPIRED")
    else:
        raise HTTPException(status_code=409, detail={"code": "SET_BY_THE_MARKET",
                            "message": f"{target or 'That state'} is set by the market, not by hand."})
    return {"offer_id": offer_id, "new_state": row["listing_state"],
            "transitioned_at": datetime.now(timezone.utc).isoformat()}


@router.delete("/offers/{offer_id}", status_code=204)
async def delete_offer(offer_id: str, request: Request):
    """Only the owner's own DRAFT, and it is withdrawn rather than erased: an order is a
    record (its events reference it). A listing that was ever live: withdraw it."""
    from app.core import market_engine as me
    party = _market_party(request)
    if party.is_admin:
        raise HTTPException(status_code=404, detail="Offer not found")
    try:
        row = me.my_listing(party, offer_id)
    except me.MarketRefused:
        raise HTTPException(status_code=404, detail="Offer not found")
    if row["listing_state"] != "DRAFT":
        raise HTTPException(status_code=409, detail={"code": "LISTING_IS_A_RECORD",
                            "message": "Only a draft can be deleted; withdraw a live listing."})
    _market_call(me.withdraw_offer, party, offer_id)
    return None
