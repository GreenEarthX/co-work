"""
Enhanced Marketplace API - Add Event Tracking for Market Discovery
Tracks when buyers view offers (market intelligence)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.core.event_store import append_event, get_events
import sqlite3
import os
from app.core.config import settings

router = APIRouter()

DB_PATH = settings.SQLITE_DB_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/offers/{offer_id}/view", status_code=200)
async def track_offer_view(
    offer_id: str,
    user_id: str = "trader",
    buyer_name: Optional[str] = None
):
    """
    Track when a trader views an offer
    Provides market intelligence: which offers get most interest
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get offer details
        cursor.execute("""
            SELECT o.*, o.correlation_id
            FROM offers o
            WHERE o.id = ?
        """, (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        correlation_id = offer['correlation_id'] if 'correlation_id' in offer.keys() else None
        
        # Emit event (market intelligence!)
        append_event(
            event_type="offer.viewed",
            aggregate_type="offer",
            aggregate_id=offer_id,
            data={
                "molecule": offer['molecule'],
                "volume_mtpd": offer['volume_mtpd'],
                "price_eur_kg": offer['price_eur_kg'],
                "buyer_name": buyer_name,
                "viewer_id": user_id
            },
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return {
            "message": "View tracked",
            "offer_id": offer_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error tracking offer view: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track view: {str(e)}")


@router.get("/offers/{offer_id}/analytics", status_code=200)
async def get_offer_analytics(offer_id: str):
    """
    Get analytics for an offer
    How many times viewed, by whom, etc.
    """
    try:
        # Get all view events for this offer
        events = get_events(
            aggregate_type="offer",
            aggregate_id=offer_id,
            event_type="offer.viewed"
        )
        
        # Count unique viewers
        viewers = set()
        for event in events:
            if 'viewer_id' in event['data']:
                viewers.add(event['data']['viewer_id'])
        
        return {
            "offer_id": offer_id,
            "total_views": len(events),
            "unique_viewers": len(viewers),
            "recent_views": events[-10:] if len(events) > 10 else events
        }
        
    except Exception as e:
        print(f"Error getting offer analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")
