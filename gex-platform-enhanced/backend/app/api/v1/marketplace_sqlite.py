"""
Marketplace API Routes (SQLite)
Create and manage offers from tokenized capacity
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import os
import uuid

# EVENT SYSTEM IMPORTS
from app.core.event_store import EventStore

router = APIRouter()

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../gex_platform.db')

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Schemas
class OfferCreate(BaseModel):
    token_id: str
    volume_mtpd: float
    price_eur_kg: float
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    offer_type: str = 'indicative'  # 'indicative' or 'firm'

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
    created_at: str
    correlation_id: Optional[str] = None  # NEW: Inherited from token


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
        EventStore.append_event(
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
        
        # 2. CREATE OFFER in database
        cursor.execute("""
            INSERT INTO offers (
                id, token_id, molecule, volume_mtpd, price_eur_kg,
                delivery_start, delivery_end, location, status, offer_type, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            correlation_id
        ))
        
        conn.commit()
        
        # Get created offer
        cursor.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created offer")
        
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
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create offer: {str(e)}")


@router.get("/offers", response_model=dict)
async def list_offers(
    molecule: Optional[str] = None,
    status: Optional[str] = None
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
