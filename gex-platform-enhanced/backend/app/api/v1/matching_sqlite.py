"""
Matching Engine API Routes (SQLite)
Match offers with RFQs and manage buyer requests + mandate-based matching
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import json
import os
import uuid
from datetime import datetime
from app.core.config import settings

router = APIRouter()

# Database path
DB_PATH = settings.SQLITE_DB_PATH

def get_db_connection():
    """
    Slice-6 connection — SQLite or PostgreSQL by configuration
    (MARKET_DB_BACKEND). The SQL is unchanged; the shim translates
    placeholders and sets the RLS tenant context.
    """
    from app.core.db_backend import market_connection, market_is_postgres

    if market_is_postgres():
        return market_connection()
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


# ═══════════════════════════════════════════════════════════════
# BUYER MANDATE — structured demand-side matching
# ═══════════════════════════════════════════════════════════════

class BuyerMandateCreate(BaseModel):
    buyer_id: str
    esg_compliance_level: str = "STANDARD"  # STANDARD/VERIFIED/SOVEREIGN
    certification_acceptable: List[str] = []
    delivery_basis_acceptable: List[str] = []
    price_band_min: float = 0.0
    price_band_max: float = 999999.0
    volume_band_min_kg: float = 0.0
    volume_band_max_kg: float = 999999999.0

class BuyerMandateResponse(BaseModel):
    mandate_id: str
    buyer_id: str
    esg_compliance_level: str
    certification_acceptable: List[str]
    delivery_basis_acceptable: List[str]
    price_band_min: float
    price_band_max: float
    volume_band_min_kg: float
    volume_band_max_kg: float
    created_at: str

class MandateMatchResult(BaseModel):
    offer_id: str
    molecule: Optional[str] = None
    volume_mtpd: float
    price_eur_kg: float
    esg_tier: Optional[str] = None
    certification_pathway: Optional[str] = None
    delivery_basis: Optional[str] = None
    alignment_score: float  # 0-100 weighted composite
    dimension_scores: dict  # per-dimension breakdown


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


# ═══════════════════════════════════════════════════════════════
# MANDATE ENDPOINTS — Buyer-side structured demand matching
# ═══════════════════════════════════════════════════════════════

def _init_mandates_table():
    """Create buyer_mandates table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS buyer_mandates (
            mandate_id               TEXT PRIMARY KEY,
            buyer_id                 TEXT NOT NULL,
            esg_compliance_level     TEXT NOT NULL DEFAULT 'STANDARD',
            certification_acceptable TEXT NOT NULL DEFAULT '[]',
            delivery_basis_acceptable TEXT NOT NULL DEFAULT '[]',
            price_band_min           REAL NOT NULL DEFAULT 0.0,
            price_band_max           REAL NOT NULL DEFAULT 999999.0,
            volume_band_min_kg       REAL NOT NULL DEFAULT 0.0,
            volume_band_max_kg       REAL NOT NULL DEFAULT 999999999.0,
            created_at               TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mandate_buyer ON buyer_mandates(buyer_id)")
    conn.commit()
    conn.close()

# Ensure table exists on module load
_init_mandates_table()


@router.post("/mandates", response_model=BuyerMandateResponse, status_code=201)
async def create_mandate(mandate: BuyerMandateCreate):
    """Create a structured buyer mandate for ranked matching."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        mandate_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO buyer_mandates (
                mandate_id, buyer_id, esg_compliance_level,
                certification_acceptable, delivery_basis_acceptable,
                price_band_min, price_band_max,
                volume_band_min_kg, volume_band_max_kg, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mandate_id,
            mandate.buyer_id,
            mandate.esg_compliance_level,
            json.dumps(mandate.certification_acceptable),
            json.dumps(mandate.delivery_basis_acceptable),
            mandate.price_band_min,
            mandate.price_band_max,
            mandate.volume_band_min_kg,
            mandate.volume_band_max_kg,
            now,
        ))
        conn.commit()
        conn.close()

        return {
            "mandate_id": mandate_id,
            "buyer_id": mandate.buyer_id,
            "esg_compliance_level": mandate.esg_compliance_level,
            "certification_acceptable": mandate.certification_acceptable,
            "delivery_basis_acceptable": mandate.delivery_basis_acceptable,
            "price_band_min": mandate.price_band_min,
            "price_band_max": mandate.price_band_max,
            "volume_band_min_kg": mandate.volume_band_min_kg,
            "volume_band_max_kg": mandate.volume_band_max_kg,
            "created_at": now,
        }

    except Exception as e:
        print(f"Error creating mandate: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mandate: {str(e)}")


@router.get("/mandates/{buyer_id}", response_model=dict)
async def list_mandates(buyer_id: str):
    """List all mandates for a buyer."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM buyer_mandates WHERE buyer_id = ? ORDER BY created_at DESC", (buyer_id,))
        rows = cursor.fetchall()
        conn.close()

        mandates = []
        for row in rows:
            mandates.append({
                "mandate_id": row['mandate_id'],
                "buyer_id": row['buyer_id'],
                "esg_compliance_level": row['esg_compliance_level'],
                "certification_acceptable": json.loads(row['certification_acceptable']),
                "delivery_basis_acceptable": json.loads(row['delivery_basis_acceptable']),
                "price_band_min": row['price_band_min'],
                "price_band_max": row['price_band_max'],
                "volume_band_min_kg": row['volume_band_min_kg'],
                "volume_band_max_kg": row['volume_band_max_kg'],
                "created_at": row['created_at'],
            })

        return {"mandates": mandates}

    except Exception as e:
        print(f"Error listing mandates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list mandates: {str(e)}")


@router.post("/mandates/{mandate_id}/match", response_model=dict)
async def run_mandate_matching(mandate_id: str):
    """
    Run 6-dimension ranked matching against a buyer mandate.
    Filters: ESG tier, certification, delivery basis, volume, price.
    Ranks by weighted alignment score. Never auto-selects.

    Dimensions (weights):
      1. ESG tier (20)
      2. Certification pathway (20)
      3. Delivery basis (15)
      4. Volume fit (15)
      5. Price fit (20)
      6. Delivery period overlap (10)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Load mandate
        cursor.execute("SELECT * FROM buyer_mandates WHERE mandate_id = ?", (mandate_id,))
        mandate_row = cursor.fetchone()
        if not mandate_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Mandate not found")

        esg_level = mandate_row['esg_compliance_level']
        cert_acceptable = json.loads(mandate_row['certification_acceptable'])
        delivery_acceptable = json.loads(mandate_row['delivery_basis_acceptable'])
        price_min = mandate_row['price_band_min']
        price_max = mandate_row['price_band_max']
        vol_min_kg = mandate_row['volume_band_min_kg']
        vol_max_kg = mandate_row['volume_band_max_kg']

        # ESG tier hierarchy for filtering
        esg_hierarchy = {"STANDARD": 0, "VERIFIED": 1, "SOVEREIGN": 2}
        min_esg = esg_hierarchy.get(esg_level, 0)

        # Load active offers
        cursor.execute("""
            SELECT o.*, c.project_name
            FROM offers o
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE o.status = 'active'
        """)
        offers = cursor.fetchall()
        conn.close()

        results: list[dict] = []

        for offer in offers:
            offer_dict = dict(offer)
            dim_scores: dict[str, float] = {}

            # 1. ESG tier filter + score (20 pts)
            offer_esg = offer_dict.get('esg_tier') or 'STANDARD'
            offer_esg_level = esg_hierarchy.get(offer_esg, 0)
            if offer_esg_level < min_esg:
                continue  # filtered out
            dim_scores["esg_tier"] = min(20.0, 20.0 * (offer_esg_level + 1) / 3.0)

            # 2. Certification filter + score (20 pts)
            offer_cert = offer_dict.get('certification_pathway') or offer_dict.get('sovereign_cert_scheme') or ''
            if cert_acceptable and offer_cert and offer_cert not in cert_acceptable:
                continue  # filtered out
            dim_scores["certification"] = 20.0 if (not cert_acceptable or offer_cert in cert_acceptable) else 0.0

            # 3. Delivery basis filter + score (15 pts)
            offer_delivery = offer_dict.get('delivery_basis') or ''
            if delivery_acceptable and offer_delivery and offer_delivery not in delivery_acceptable:
                continue  # filtered out
            dim_scores["delivery_basis"] = 15.0 if (not delivery_acceptable or offer_delivery in delivery_acceptable) else 0.0

            # 4. Volume fit (15 pts)
            offer_vol_kg = offer_dict['volume_mtpd'] * 1000.0  # MTPD -> kg/day approx
            if offer_vol_kg < vol_min_kg * 0.5:
                continue  # too small even for partial
            vol_score = 0.0
            if vol_min_kg <= offer_vol_kg <= vol_max_kg:
                vol_score = 15.0
            elif offer_vol_kg > vol_max_kg:
                vol_score = 10.0  # oversized but acceptable
            elif offer_vol_kg >= vol_min_kg * 0.7:
                vol_score = 10.0
            dim_scores["volume"] = vol_score

            # 5. Price fit (20 pts)
            offer_price = offer_dict['price_eur_kg']
            if offer_price > price_max * 1.2:
                continue  # too expensive
            price_score = 0.0
            if price_min <= offer_price <= price_max:
                price_score = 20.0
            elif offer_price < price_min:
                price_score = 15.0  # below band = good for buyer
            elif offer_price <= price_max * 1.1:
                price_score = 10.0  # slightly above
            dim_scores["price"] = price_score

            # 6. Delivery period overlap (10 pts)
            dim_scores["delivery_period"] = 10.0  # default pass (full validation requires RFQ dates)

            alignment = sum(dim_scores.values())

            results.append({
                "offer_id": offer_dict['id'],
                "molecule": offer_dict.get('molecule'),
                "volume_mtpd": offer_dict['volume_mtpd'],
                "price_eur_kg": offer_dict['price_eur_kg'],
                "esg_tier": offer_esg,
                "certification_pathway": offer_cert or None,
                "delivery_basis": offer_delivery or None,
                "alignment_score": round(alignment, 1),
                "dimension_scores": dim_scores,
            })

        # Rank by alignment score descending
        results.sort(key=lambda x: x["alignment_score"], reverse=True)

        return {
            "mandate_id": mandate_id,
            "matches": results,
            "total_candidates": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error running mandate matching: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run mandate matching: {str(e)}")
