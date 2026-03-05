"""
RFQ (Request for Quote) Management API
Trader/Buyer perspective - with state machines and events from day 1
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import os
import uuid
from datetime import datetime

# EVENT SYSTEM IMPORTS
from app.core.event_store import EventStore
from app.core.state_machine import transition_state, TransitionError, PreconditionError

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
    buyer_name: str
    buyer_contact: Optional[str] = None
    compliance_requirements: Optional[List[str]] = None

class RFQResponse(BaseModel):
    id: str
    molecule: str
    volume_mtpd: float
    max_price_eur_kg: Optional[float] = None
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    buyer_name: str
    buyer_contact: Optional[str] = None
    compliance_requirements: Optional[List[str]] = None
    status: str
    created_at: str
    correlation_id: str  # For chain of custody


@router.post("/", response_model=RFQResponse, status_code=201)
async def create_rfq(rfq: RFQCreate, user_id: str = "trader"):
    """
    Create RFQ (Request for Quote)
    EVENT-DRIVEN: Creates new correlation_id for buyer side
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate IDs
        rfq_id = str(uuid.uuid4())
        correlation_id = f"RFQ-{rfq_id[:8].upper()}"  # Buyer's correlation_id
        
        # Prepare compliance requirements as JSON
        import json
        compliance_json = json.dumps(rfq.compliance_requirements) if rfq.compliance_requirements else None
        
        # 1. EMIT EVENT
        EventStore.append_event(
            event_type="rfq.created",
            aggregate_type="rfq",
            aggregate_id=rfq_id,
            data={
                "molecule": rfq.molecule,
                "volume_mtpd": rfq.volume_mtpd,
                "max_price_eur_kg": rfq.max_price_eur_kg,
                "delivery_start": rfq.delivery_start,
                "delivery_end": rfq.delivery_end,
                "location": rfq.location,
                "buyer_name": rfq.buyer_name,
                "compliance_requirements": rfq.compliance_requirements,
                "status": "draft"
            },
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        # 2. CREATE RFQ in database
        cursor.execute("""
            INSERT INTO rfqs (
                id, molecule, volume_mtpd, max_price_eur_kg,
                delivery_start, delivery_end, location,
                buyer_name, buyer_contact, compliance_requirements,
                status, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rfq_id,
            rfq.molecule,
            rfq.volume_mtpd,
            rfq.max_price_eur_kg,
            rfq.delivery_start,
            rfq.delivery_end,
            rfq.location,
            rfq.buyer_name,
            rfq.buyer_contact,
            compliance_json,
            "draft",
            correlation_id
        ))
        
        conn.commit()
        
        # Get created RFQ
        cursor.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created RFQ")
        
        compliance = json.loads(row['compliance_requirements']) if row['compliance_requirements'] else None
        
        return {
            "id": row['id'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "max_price_eur_kg": row['max_price_eur_kg'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "location": row['location'],
            "buyer_name": row['buyer_name'],
            "buyer_contact": row['buyer_contact'],
            "compliance_requirements": compliance,
            "status": row['status'],
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id']
        }
        
    except Exception as e:
        print(f"Error creating RFQ: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create RFQ: {str(e)}")


@router.get("/", response_model=dict)
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
        
        import json
        rfqs = []
        for row in rows:
            compliance = json.loads(row['compliance_requirements']) if row['compliance_requirements'] else None
            rfqs.append({
                "id": row['id'],
                "molecule": row['molecule'],
                "volume_mtpd": row['volume_mtpd'],
                "max_price_eur_kg": row['max_price_eur_kg'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
                "location": row['location'],
                "buyer_name": row['buyer_name'],
                "status": row['status'],
                "created_at": row['created_at'],
                "compliance_requirements": compliance
            })
        
        return {"rfqs": rfqs}
        
    except Exception as e:
        print(f"Error listing RFQs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list RFQs: {str(e)}")


@router.get("/{rfq_id}", response_model=RFQResponse)
async def get_rfq(rfq_id: str):
    """
    Get a specific RFQ by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="RFQ not found")
        
        import json
        compliance = json.loads(row['compliance_requirements']) if row['compliance_requirements'] else None
        
        return {
            "id": row['id'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "max_price_eur_kg": row['max_price_eur_kg'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "location": row['location'],
            "buyer_name": row['buyer_name'],
            "buyer_contact": row['buyer_contact'],
            "compliance_requirements": compliance,
            "status": row['status'],
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting RFQ: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get RFQ: {str(e)}")


@router.patch("/{rfq_id}/status", status_code=200)
async def update_rfq_status(
    rfq_id: str,
    new_status: str,
    user_id: str = "trader",
    notes: Optional[str] = None
):
    """
    Update RFQ status using state machine
    Enforces valid transitions
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current RFQ
        cursor.execute("SELECT status, correlation_id FROM rfqs WHERE id = ?", (rfq_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="RFQ not found")
        
        current_status = row['status']
        correlation_id = row['correlation_id']
        
        # Valid transitions for RFQ
        valid_transitions = {
            "draft": ["open", "cancelled"],
            "open": ["matched", "expired", "withdrawn"],
            "matched": ["accepted", "rejected"],
            "accepted": ["contracted"],
            "contracted": ["fulfilled"],
            "fulfilled": [],
            "cancelled": [],
            "expired": [],
            "withdrawn": [],
            "rejected": []
        }
        
        if new_status not in valid_transitions.get(current_status, []):
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transition: {current_status} → {new_status}. Valid: {valid_transitions.get(current_status, [])}"
            )
        
        # Emit event
        EventStore.append_event(
            event_type="rfq.status_changed",
            aggregate_type="rfq",
            aggregate_id=rfq_id,
            data={
                "old_status": current_status,
                "new_status": new_status,
                "notes": notes
            },
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        # Update database
        cursor.execute("""
            UPDATE rfqs 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, rfq_id))
        
        conn.commit()
        conn.close()
        
        return {
            "message": "Status updated successfully",
            "rfq_id": rfq_id,
            "old_status": current_status,
            "new_status": new_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating RFQ status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@router.get("/{rfq_id}/transitions", status_code=200)
async def get_valid_rfq_transitions(rfq_id: str):
    """
    Get valid next states for an RFQ
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT status FROM rfqs WHERE id = ?", (rfq_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="RFQ not found")
        
        current_status = row['status']
        
        valid_transitions = {
            "draft": ["open", "cancelled"],
            "open": ["matched", "expired", "withdrawn"],
            "matched": ["accepted", "rejected"],
            "accepted": ["contracted"],
            "contracted": ["fulfilled"],
            "fulfilled": [],
            "cancelled": [],
            "expired": [],
            "withdrawn": [],
            "rejected": []
        }
        
        return {
            "rfq_id": rfq_id,
            "current_status": current_status,
            "valid_transitions": valid_transitions.get(current_status, [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting valid transitions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transitions: {str(e)}")
