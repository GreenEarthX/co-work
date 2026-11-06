"""
Capacity Management API Routes (SQLite)
NOW WITH EVENT-DRIVEN ARCHITECTURE
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import json
import os
import uuid
from datetime import date

# Import event system
from app.core.event_store import append_event
from app.core.config import settings

router = APIRouter()

# Database path - 3 levels up from app/api/v1/ to backend/
DB_PATH = settings.SQLITE_DB_PATH

def get_db_connection():
    """
    PostgreSQL only (JML, 2026-10-23): no SQLite fallback. The shim sets the RLS
    tenant context from the bound caller.
    """
    from app.core.db_backend import market_connection, market_is_postgres, require_postgres

    require_postgres(market_is_postgres(), "Capacities", "MARKET_DB_BACKEND")
    return market_connection()

# Schemas
class CapacityCreate(BaseModel):
    project_id: str                       # alembic 084: the project this capacity is of
    project_name: str
    molecule: str
    capacity_mtpd: float
    location: Optional[str] = None
    production_start: Optional[str] = None
    production_end: Optional[str] = None
    compliance_certifications: Optional[List[str]] = None
    capex_eur: Optional[float] = None
    opex_eur_kg: Optional[float] = None

class CapacityResponse(BaseModel):
    id: str
    project_id: Optional[str] = None
    project_name: str
    molecule: str
    capacity_mtpd: float
    location: Optional[str] = None
    production_start: Optional[str] = None
    production_end: Optional[str] = None
    compliance_certifications: Optional[List[str]] = None
    capex_eur: Optional[float] = None
    opex_eur_kg: Optional[float] = None
    created_at: str
    status: Optional[str] = "draft"
    correlation_id: Optional[str] = None  # NEW: For chain of custody


@router.post("/", response_model=CapacityResponse, status_code=201)
async def create_capacity(capacity: CapacityCreate, request: Request):
    """Declare a production capacity of one of the caller's own projects.

    alembic 084 (Phase 0 §5): the capacity names its project. Before, the id was
    a random uuid read everywhere as a project id, so RLS refused every
    producer's insert and the market refused every producer offer. The actor is
    the token's user — it used to be a query parameter defaulting to "system".
    """
    from app.core.project_registry import get_project_profile

    payload = getattr(request.state, "user_payload", None) or {}
    user_id, company = payload.get("user_id"), payload.get("company_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail={"code": "GEX_DOES_NOT_TRADE",
                                                     "message": "A capacity is declared by the project's owner."})
    profile = get_project_profile(capacity.project_id)
    if profile is None or profile.owner_company_id != company:
        raise HTTPException(status_code=403, detail={"code": "NOT_YOUR_PROJECT",
                                                     "message": "Only the project's owner declares its capacity."})
    capacity_id = str(uuid.uuid4())
    correlation_id = f"CAP-{capacity_id[:8].upper()}"
    compliance_json = json.dumps(capacity.compliance_certifications) if capacity.compliance_certifications else None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Event first (immutable log), then the projection.
        append_event(
            event_type="capacity.created", aggregate_type="capacity", aggregate_id=capacity_id,
            data={"project_id": capacity.project_id, "project_name": capacity.project_name,
                  "molecule": capacity.molecule, "capacity_mtpd": capacity.capacity_mtpd,
                  "location": capacity.location, "production_start": capacity.production_start,
                  "production_end": capacity.production_end,
                  "compliance_certifications": capacity.compliance_certifications, "status": "draft"},
            user_id=user_id, correlation_id=correlation_id)
        cursor.execute("""
            INSERT INTO capacities (
                id, project_id, project_name, molecule, capacity_mtpd, location,
                production_start, production_end, compliance_certifications,
                capex_eur, opex_eur_kg, status, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (capacity_id, capacity.project_id, capacity.project_name, capacity.molecule,
              capacity.capacity_mtpd, capacity.location, capacity.production_start, capacity.production_end,
              compliance_json, capacity.capex_eur, capacity.opex_eur_kg, "draft", correlation_id))
        conn.commit()
        cursor.execute("SELECT * FROM capacities WHERE id = ?", (capacity_id,))
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve created capacity")
    return {
        "id": row['id'], "project_id": row['project_id'], "project_name": row['project_name'],
        "molecule": row['molecule'], "capacity_mtpd": row['capacity_mtpd'], "location": row['location'],
        "production_start": row['production_start'], "production_end": row['production_end'],
        "compliance_certifications": json.loads(row['compliance_certifications'])
        if row['compliance_certifications'] else None,
        "capex_eur": row['capex_eur'], "opex_eur_kg": row['opex_eur_kg'], "created_at": str(row['created_at']),
        "status": row['status'] or "draft", "correlation_id": row['correlation_id'] or correlation_id,
    }


@router.get("/", response_model=dict)
async def list_capacities(molecule: Optional[str] = None):
    """
    List all capacities with optional filtering
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if molecule:
            cursor.execute("""
                SELECT * FROM capacities 
                WHERE molecule = ?
                ORDER BY created_at DESC
            """, (molecule,))
        else:
            cursor.execute("""
                SELECT * FROM capacities 
                ORDER BY created_at DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        capacities = []
        for row in rows:
            compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
            capacities.append({
                "id": row['id'],
                "project_name": row['project_name'],
                "molecule": row['molecule'],
                "capacity_mtpd": row['capacity_mtpd'],
                "location": row['location'],
                "production_start": row['production_start'],
                "production_end": row['production_end'],
                "compliance_certifications": compliance,
                "capex_eur": row['capex_eur'],
                "opex_eur_kg": row['opex_eur_kg'],
                "created_at": row['created_at'],
            })
        
        return {"capacities": capacities}
        
    except Exception as e:
        print(f"Error listing capacities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list capacities: {str(e)}")


@router.patch("/{capacity_id}/status", status_code=200)
async def update_capacity_status(
    capacity_id: str,
    new_status: str,
    user_id: str = "system",
    notes: Optional[str] = None
):
    """
    Update capacity status using state machine
    Enforces valid transitions and business rules
    """
    try:
        from app.core.state_machine import transition_state, TransitionError, PreconditionError
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current capacity
        cursor.execute("SELECT status, correlation_id FROM capacities WHERE id = ?", (capacity_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Capacity not found")
        
        current_status = row['status'] if row['status'] else 'draft'
        correlation_id = row['correlation_id']
        
        try:
            # Use state machine to validate and emit event
            event_id = transition_state(
                aggregate_type="capacity",
                aggregate_id=capacity_id,
                from_state=current_status,
                to_state=new_status,
                data={
                    "notes": notes,
                    "changed_by": user_id
                },
                user_id=user_id,
                correlation_id=correlation_id
            )
            
        except TransitionError as e:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Invalid transition: {str(e)}")
        
        except PreconditionError as e:
            conn.close()
            raise HTTPException(status_code=422, detail=f"Precondition failed: {str(e)}")
        
        # Update database
        cursor.execute("""
            UPDATE capacities 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, capacity_id))
        
        conn.commit()
        conn.close()
        
        return {
            "message": "Status updated successfully",
            "capacity_id": capacity_id,
            "old_status": current_status,
            "new_status": new_status,
            "event_id": event_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating capacity status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@router.get("/{capacity_id}/transitions", status_code=200)
async def get_valid_transitions(capacity_id: str):
    """
    Get valid next states for a capacity
    Helps UI show only valid actions
    """
    try:
        from app.core.state_machine import get_valid_next_states
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT status FROM capacities WHERE id = ?", (capacity_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Capacity not found")
        
        current_status = row['status'] if row['status'] else 'draft'
        valid_transitions = get_valid_next_states("capacity", current_status)
        
        return {
            "capacity_id": capacity_id,
            "current_status": current_status,
            "valid_transitions": valid_transitions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting valid transitions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transitions: {str(e)}")


@router.get("/{capacity_id}", response_model=CapacityResponse)
async def get_capacity(capacity_id: str):
    """
    Get a specific capacity by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM capacities WHERE id = ?", (capacity_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Capacity not found")
        
        compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
        
        return {
            "id": row['id'],
            "project_name": row['project_name'],
            "molecule": row['molecule'],
            "capacity_mtpd": row['capacity_mtpd'],
            "location": row['location'],
            "production_start": row['production_start'],
            "production_end": row['production_end'],
            "compliance_certifications": compliance,
            "capex_eur": row['capex_eur'],
            "opex_eur_kg": row['opex_eur_kg'],
            "created_at": row['created_at'],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting capacity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get capacity: {str(e)}")


@router.delete("/{capacity_id}", status_code=204)
async def delete_capacity(capacity_id: str):
    """
    Delete a capacity
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM capacities WHERE id = ?", (capacity_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Capacity not found")
        
        conn.commit()
        conn.close()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting capacity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete capacity: {str(e)}")
