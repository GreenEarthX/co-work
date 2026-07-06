"""
Marketplace API Routes (SQLite)
Create and manage offers from tokenized capacity
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
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
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


@router.post("/offers", response_model=OfferResponse, status_code=201)
async def create_offer(offer: OfferCreate, user_id: str = "system"):
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
            offer.listing_state or "DRAFT",
        ))

        conn.commit()

        # Get created offer
        cursor.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created offer")

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


@router.patch("/offers/{offer_id}/status", status_code=200)
async def update_offer_status(offer_id: str, status: str):
    """
    Update offer status (active, matched, expired)
    """
    try:
        if status not in ['active', 'matched', 'expired']:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE offers SET status = ? WHERE id = ?", (status, offer_id))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Offer not found")
        
        conn.commit()
        conn.close()
        
        return {"message": "Status updated", "offer_id": offer_id, "status": status}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating offer status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@router.post("/offers/{offer_id}/transition", status_code=200)
async def transition_listing(offer_id: str, transition: ListingTransition, user_id: str = "system"):
    """
    Advance listing state machine.
    Valid transitions:
      DRAFT -> OPEN, WITHDRAWN
      OPEN -> RESERVED, MATCHED, EXPIRED, WITHDRAWN
      RESERVED -> MATCHED, OPEN, WITHDRAWN
      MATCHED -> SETTLED, WITHDRAWN
      SETTLED -> (terminal)
      EXPIRED -> (terminal)
      WITHDRAWN -> (terminal)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Offer not found")

        current_str = row['listing_state'] if 'listing_state' in row.keys() else "DRAFT"
        try:
            current_state = ListingState(current_str)
        except ValueError:
            current_state = ListingState.DRAFT

        try:
            new_state = ListingState(transition.new_state)
        except ValueError:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Invalid state: {transition.new_state}")

        valid_next = LISTING_TRANSITIONS.get(current_state, [])
        if new_state not in valid_next:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transition: {current_state.value} -> {new_state.value}. "
                       f"Valid: {[s.value for s in valid_next]}"
            )

        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE offers SET listing_state = ? WHERE id = ?",
            (new_state.value, offer_id)
        )

        # Sync legacy status field
        status_map = {
            ListingState.OPEN: "active",
            ListingState.MATCHED: "matched",
            ListingState.EXPIRED: "expired",
            ListingState.WITHDRAWN: "expired",
            ListingState.SETTLED: "matched",
        }
        if new_state in status_map:
            cursor.execute(
                "UPDATE offers SET status = ? WHERE id = ?",
                (status_map[new_state], offer_id)
            )

        correlation_id = row['correlation_id'] if 'correlation_id' in row.keys() else f"OFF-{offer_id[:8]}"
        append_event(
            event_type=f"offer.{new_state.value.lower()}",
            aggregate_type="offer",
            aggregate_id=offer_id,
            data={
                "from_state": current_state.value,
                "to_state": new_state.value,
                "changed_by": transition.changed_by,
                "justification": transition.justification,
            },
            user_id=transition.changed_by,
            correlation_id=correlation_id,
        )

        conn.commit()
        conn.close()

        return {
            "offer_id": offer_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "transitioned_at": now,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error transitioning offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to transition offer: {str(e)}")


@router.delete("/offers/{offer_id}", status_code=204)
async def delete_offer(offer_id: str):
    """
    Delete an offer
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM offers WHERE id = ?", (offer_id,))

        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Offer not found")

        conn.commit()
        conn.close()

        return None

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete offer: {str(e)}")
