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
            SELECT t.*, c.molecule, c.project_name, t.correlation_id 
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
        user_id = party.user_id
        if party.is_admin or me.seller_company(token['capacity_id']) != party.company_id:
            conn.close()
            raise HTTPException(status_code=403, detail={"code": "NOT_YOUR_TOKEN",
                                "message": "Only the company that owns the project can offer its token."})
        wants_open = (offer.listing_state or "DRAFT") == "OPEN"
        
        # INHERIT correlation_id from token (CHAIN OF CUSTODY!)
        correlation_id = token['correlation_id'] if 'correlation_id' in token.keys() else f"TOK-{offer.token_id[:8]}"
        
        # Check if offering too much volume
        cursor.execute("""
            SELECT COALESCE(SUM(volume_mtpd), 0) as total_offered 
            FROM offers 
            WHERE token_id = ? AND status = 'active'
        """, (offer.token_id,))
        result = cursor.fetchone()
        total_offered = result['total_offered']
        
        if total_offered + offer.volume_mtpd > token['tokenised_mtpd']:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Cannot offer {offer.volume_mtpd} MTPD. Available: {token['tokenised_mtpd'] - total_offered} MTPD"
            )
        
        # Generate UUID
        offer_id = str(uuid.uuid4())
        
        # 1. EMIT EVENT (with inherited correlation_id)
        append_event(
            event_type="offer.created",
            aggregate_type="offer",
            aggregate_id=offer_id,
            data={
                "token_id": offer.token_id,
                "molecule": token['molecule'],
                "volume_mtpd": offer.volume_mtpd,
                "price_eur_kg": offer.price_eur_kg,
                "delivery_start": offer.delivery_start,
                "delivery_end": offer.delivery_end,
                "location": offer.location,
                "offer_type": offer.offer_type,
                "status": "active"
            },
            user_id=user_id,
            correlation_id=correlation_id  # INHERITED - creates chain!
        )
        
        # Serialize certification_pathway_required
        cert_req_json = json.dumps(offer.certification_pathway_required) if offer.certification_pathway_required else None

        # 2. CREATE OFFER in database (v4.0 extended)
        cursor.execute("""
            INSERT INTO offers (
                id, token_id, molecule, volume_mtpd, price_eur_kg,
                delivery_start, delivery_end, location, status, offer_type, correlation_id,
                delivery_type, delivery_basis, price_basis,
                certification_pathway_required, min_order_kg, esg_tier, listing_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            offer_id,
            offer.token_id,
            token['molecule'],
            offer.volume_mtpd,
            offer.price_eur_kg,
            offer.delivery_start,
            offer.delivery_end,
            offer.location,
            'active',
            offer.offer_type,
            correlation_id,
            offer.delivery_type or "SPOT",
            offer.delivery_basis,
            offer.price_basis,
            cert_req_json,
            offer.min_order_kg,
            offer.esg_tier,
            "DRAFT",          # live only through the engine, which reserves the token
        ))

        conn.commit()

        # Get created offer
        cursor.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created offer")

        if wants_open:
            row = _market_call(me.open_offer, party, offer_id)

        cert_req = None
        if 'certification_pathway_required' in row.keys() and row['certification_pathway_required']:
            cert_req = json.loads(row['certification_pathway_required'])

        return {
            "id": row['id'],
            "token_id": row['token_id'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "location": row['location'],
            "status": row['status'],
            "offer_type": row['offer_type'],
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id'] if 'correlation_id' in row.keys() else correlation_id,
            "delivery_type": row['delivery_type'] if 'delivery_type' in row.keys() else "SPOT",
            "delivery_basis": row['delivery_basis'] if 'delivery_basis' in row.keys() else None,
            "price_basis": row['price_basis'] if 'price_basis' in row.keys() else None,
            "certification_pathway_required": cert_req,
            "min_order_kg": row['min_order_kg'] if 'min_order_kg' in row.keys() else None,
            "esg_tier": row['esg_tier'] if 'esg_tier' in row.keys() else None,
            "listing_state": row['listing_state'] if 'listing_state' in row.keys() else "DRAFT",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create offer: {str(e)}")


@router.get("/offers", response_model=dict)
async def list_offers(
    molecule: Optional[str] = None,
    status: Optional[str] = None,
    country_of_origin: Optional[str] = None,
    dfi_funded: Optional[bool] = None,
    sovereign_cert_scheme: Optional[str] = None,
    min_esg_score: Optional[float] = None,
    listing_state: Optional[str] = None,
):
    """
    List all offers with optional filtering
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT o.*, c.project_name 
            FROM offers o
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE 1=1
        """
        params = []
        
        if molecule:
            query += " AND o.molecule = ?"
            params.append(molecule)
        
        if status:
            query += " AND o.status = ?"
            params.append(status)

        # Sovereign provenance filters
        if country_of_origin:
            query += " AND o.country_of_origin = ?"
            params.append(country_of_origin)

        if dfi_funded is not None:
            query += " AND o.dfi_funded = ?"
            params.append(1 if dfi_funded else 0)

        if sovereign_cert_scheme:
            query += " AND o.sovereign_cert_scheme = ?"
            params.append(sovereign_cert_scheme)

        if min_esg_score is not None:
            query += " AND o.esg_score >= ?"
            params.append(min_esg_score)

        if listing_state:
            query += " AND o.listing_state = ?"
            params.append(listing_state)

        query += " ORDER BY o.created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        offers = []
        for row in rows:
            offers.append({
                "id": row['id'],
                "token_id": row['token_id'],
                "project_name": row['project_name'],
                "molecule": row['molecule'],
                "volume_mtpd": row['volume_mtpd'],
                "price_eur_kg": row['price_eur_kg'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
                "location": row['location'],
                "status": row['status'],
                "offer_type": row['offer_type'],
                "created_at": row['created_at'],
            })
        
        return {"offers": offers}
        
    except Exception as e:
        print(f"Error listing offers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list offers: {str(e)}")


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(offer_id: str):
    """
    Get a specific offer by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        return {
            "id": row['id'],
            "token_id": row['token_id'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "location": row['location'],
            "status": row['status'],
            "offer_type": row['offer_type'],
            "created_at": row['created_at'],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get offer: {str(e)}")


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
        row = _market_call(me.withdraw_offer, party, offer_id)
        if target == "EXPIRED":
            conn = me._conn()
            try:
                conn.execute("UPDATE offers SET listing_state = 'EXPIRED' WHERE id = ?", (offer_id,))
                conn.commit()
                row = me._row(conn, "SELECT * FROM offers WHERE id = ?", (offer_id,))
            finally:
                conn.close()
    else:
        raise HTTPException(status_code=409, detail={"code": "SET_BY_THE_MARKET",
                            "message": f"{target or 'That state'} is set by the market, not by hand."})
    return {"offer_id": offer_id, "new_state": row["listing_state"],
            "transitioned_at": datetime.now(timezone.utc).isoformat()}


@router.delete("/offers/{offer_id}", status_code=204)
async def delete_offer(offer_id: str, request: Request):
    """Only the owner's own DRAFT. A listing that was ever live is a record: withdraw it."""
    from app.core import market_engine as me
    party = _market_party(request)
    conn = me._conn()
    try:
        o = me._row(conn, "SELECT o.listing_state, t.capacity_id FROM offers o JOIN tokens t "
                          "ON t.id = o.token_id WHERE o.id = ?", (offer_id,))
        if o is None or party.is_admin or me.seller_company(o["capacity_id"]) != party.company_id:
            raise HTTPException(status_code=404, detail="Offer not found")
        if (o["listing_state"] or "DRAFT") != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "LISTING_IS_A_RECORD",
                                "message": "Only a draft can be deleted; withdraw a live listing."})
        conn.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
        conn.commit()
    finally:
        conn.close()
    return None
