"""
Matching Engine API Routes (SQLite)
Match offers with RFQs and manage buyer requests
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import os
import uuid
from datetime import datetime

router = APIRouter()

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../gex_platform.db')

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Schemas
class RFQCreate(BaseModel):
    molecule: str
    volume_mtpd: float
    max_price_eur_kg: Optional[float] = None
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None

class RFQResponse(BaseModel):
    id: str
    molecule: str
    volume_mtpd: float
    max_price_eur_kg: Optional[float] = None
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    status: str
    created_at: str

class MatchResponse(BaseModel):
    id: str
    offer_id: str
    rfq_id: str
    match_score: int
    volume_mtpd: float
    price_eur_kg: float
    status: str
    created_at: str
    offer_project: Optional[str] = None
    offer_molecule: Optional[str] = None


# ============================================
# RFQ ENDPOINTS
# ============================================

@router.post("/rfqs", response_model=RFQResponse, status_code=201)
async def create_rfq(rfq: RFQCreate):
    """
    Create Request for Quote (RFQ)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate UUID
        rfq_id = str(uuid.uuid4())
        
        # Create RFQ
        cursor.execute("""
            INSERT INTO rfqs (
                id, molecule, volume_mtpd, max_price_eur_kg,
                delivery_start, delivery_end, location, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rfq_id,
            rfq.molecule,
            rfq.volume_mtpd,
            rfq.max_price_eur_kg,
            rfq.delivery_start,
            rfq.delivery_end,
            rfq.location,
            'open'
        ))
        
        conn.commit()
        
        # Get created RFQ
        cursor.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created RFQ")
        
        return {
            "id": row['id'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "max_price_eur_kg": row['max_price_eur_kg'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "location": row['location'],
            "status": row['status'],
            "created_at": row['created_at'],
        }
        
    except Exception as e:
        print(f"Error creating RFQ: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create RFQ: {str(e)}")


@router.get("/rfqs", response_model=dict)
async def list_rfqs(
    molecule: Optional[str] = None,
    status: Optional[str] = None
):
    """
    List all RFQs with optional filtering
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM rfqs WHERE 1=1"
        params = []
        
        if molecule:
            query += " AND molecule = ?"
            params.append(molecule)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        rfqs = []
        for row in rows:
            rfqs.append({
                "id": row['id'],
                "molecule": row['molecule'],
                "volume_mtpd": row['volume_mtpd'],
                "max_price_eur_kg": row['max_price_eur_kg'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
                "location": row['location'],
                "status": row['status'],
                "created_at": row['created_at'],
            })
        
        return {"rfqs": rfqs}
        
    except Exception as e:
        print(f"Error listing RFQs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list RFQs: {str(e)}")


# ============================================
# MATCHING ENGINE ENDPOINTS
# ============================================

def calculate_match_score(offer: dict, rfq: dict) -> int:
    """
    Calculate match score (0-100) based on compatibility
    """
    score = 0
    
    # Molecule match (40 points)
    if offer['molecule'] == rfq['molecule']:
        score += 40
    
    # Price compatibility (30 points)
    if rfq['max_price_eur_kg'] is None or offer['price_eur_kg'] <= rfq['max_price_eur_kg']:
        score += 30
        # Bonus for good price
        if rfq['max_price_eur_kg'] and offer['price_eur_kg'] <= rfq['max_price_eur_kg'] * 0.9:
            score += 10
    
    # Volume compatibility (20 points)
    if offer['volume_mtpd'] >= rfq['volume_mtpd']:
        score += 20
    elif offer['volume_mtpd'] >= rfq['volume_mtpd'] * 0.7:
        score += 15
    
    # Delivery period overlap (10 points)
    # Simplified: just check if dates overlap
    offer_start = offer['delivery_start']
    offer_end = offer['delivery_end']
    rfq_start = rfq['delivery_start']
    rfq_end = rfq['delivery_end']
    
    if (offer_start <= rfq_end and offer_end >= rfq_start):
        score += 10
    
    return min(score, 100)


@router.post("/run", response_model=dict)
async def run_matching():
    """
    Run matching engine to find offer-RFQ matches
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get active offers
        cursor.execute("""
            SELECT o.*, c.project_name
            FROM offers o
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE o.status = 'active'
        """)
        offers = cursor.fetchall()
        
        # Get open RFQs
        cursor.execute("SELECT * FROM rfqs WHERE status = 'open'")
        rfqs = cursor.fetchall()
        
        matches_created = 0
        
        # Find matches
        for offer in offers:
            for rfq in rfqs:
                score = calculate_match_score(dict(offer), dict(rfq))
                
                # Only create match if score is good enough
                if score >= 60:
                    # Check if match already exists
                    cursor.execute("""
                        SELECT id FROM matches 
                        WHERE offer_id = ? AND rfq_id = ?
                    """, (offer['id'], rfq['id']))
                    
                    if not cursor.fetchone():
                        # Create new match
                        match_id = str(uuid.uuid4())
                        match_volume = min(offer['volume_mtpd'], rfq['volume_mtpd'])
                        
                        cursor.execute("""
                            INSERT INTO matches (
                                id, offer_id, rfq_id, match_score, 
                                volume_mtpd, price_eur_kg, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            match_id,
                            offer['id'],
                            rfq['id'],
                            score,
                            match_volume,
                            offer['price_eur_kg'],
                            'pending'
                        ))
                        matches_created += 1
        
        conn.commit()
        conn.close()
        
        return {
            "message": "Matching complete",
            "matches_created": matches_created,
            "offers_processed": len(offers),
            "rfqs_processed": len(rfqs)
        }
        
    except Exception as e:
        print(f"Error running matching: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run matching: {str(e)}")


@router.get("/", response_model=dict)
async def list_matches(molecule: Optional[str] = None):
    """
    List all matches with optional filtering
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                m.*,
                o.molecule as offer_molecule,
                c.project_name as offer_project,
                o.delivery_start,
                o.delivery_end
            FROM matches m
            JOIN offers o ON m.offer_id = o.id
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE 1=1
        """
        params = []
        
        if molecule:
            query += " AND o.molecule = ?"
            params.append(molecule)
        
        query += " ORDER BY m.match_score DESC, m.created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        matches = []
        for row in rows:
            matches.append({
                "id": row['id'],
                "offer_id": row['offer_id'],
                "rfq_id": row['rfq_id'],
                "match_score": row['match_score'],
                "volume_mtpd": row['volume_mtpd'],
                "price_eur_kg": row['price_eur_kg'],
                "status": row['status'],
                "created_at": row['created_at'],
                "offer_project": row['offer_project'],
                "offer_molecule": row['offer_molecule'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
            })
        
        return {"matches": matches}
        
    except Exception as e:
        print(f"Error listing matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list matches: {str(e)}")


@router.get("/{match_id}", response_model=MatchResponse)
async def get_match(match_id: str):
    """
    Get a specific match by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                m.*,
                o.molecule as offer_molecule,
                c.project_name as offer_project
            FROM matches m
            JOIN offers o ON m.offer_id = o.id
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE m.id = ?
        """, (match_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")
        
        return {
            "id": row['id'],
            "offer_id": row['offer_id'],
            "rfq_id": row['rfq_id'],
            "match_score": row['match_score'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "status": row['status'],
            "created_at": row['created_at'],
            "offer_project": row['offer_project'],
            "offer_molecule": row['offer_molecule'],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting match: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get match: {str(e)}")


@router.post("/{match_id}/accept", status_code=200)
async def accept_match(match_id: str):
    """
    Accept a match
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE matches SET status = 'accepted' WHERE id = ?", (match_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Match not found")
        
        conn.commit()
        conn.close()
        
        return {"message": "Match accepted", "match_id": match_id}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error accepting match: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to accept match: {str(e)}")
