"""
Tokenisation API Routes (SQLite)
Convert capacity into tradeable tokens
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import json
import os
import uuid
from datetime import date

# EVENT SYSTEM IMPORTS
from app.core.event_store import EventStore

router = APIRouter()

# Database path - 3 levels up from app/api/v1/ to backend/
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../gex_platform.db')

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Schemas
class TokenCreate(BaseModel):
    capacity_id: str
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_certifications: Optional[List[str]] = None

class TokenResponse(BaseModel):
    id: str
    capacity_id: str
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_certifications: Optional[List[str]] = None
    created_at: str
    correlation_id: Optional[str] = None  # NEW: Inherited from capacity


@router.post("/", response_model=TokenResponse, status_code=201)
async def create_token(token: TokenCreate, user_id: str = "system"):
    """
    Tokenise capacity - convert production capacity into tradeable tokens
    EVENT-DRIVEN: Inherits correlation_id from capacity for chain of custody
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify capacity exists and get correlation_id
        cursor.execute("SELECT *, correlation_id FROM capacities WHERE id = ?", (token.capacity_id,))
        capacity = cursor.fetchone()
        
        if not capacity:
            conn.close()
            raise HTTPException(status_code=404, detail="Capacity not found")
        
        # INHERIT correlation_id from capacity (CHAIN OF CUSTODY!)
        correlation_id = capacity['correlation_id'] if 'correlation_id' in capacity.keys() else f"CAP-{token.capacity_id[:8]}"
        
        # Check if tokenising too much
        cursor.execute("""
            SELECT COALESCE(SUM(tokenised_mtpd), 0) as total_tokenised 
            FROM tokens 
            WHERE capacity_id = ?
        """, (token.capacity_id,))
        result = cursor.fetchone()
        total_tokenised = result['total_tokenised']
        
        if total_tokenised + token.tokenised_mtpd > capacity['capacity_mtpd']:
            conn.close()
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot tokenise {token.tokenised_mtpd} MTPD. Available: {capacity['capacity_mtpd'] - total_tokenised} MTPD"
            )
        
        # Generate UUID
        token_id = str(uuid.uuid4())
        
        # Prepare compliance as JSON
        compliance_json = json.dumps(token.compliance_certifications) if token.compliance_certifications else None
        
        # 1. EMIT EVENT (with inherited correlation_id)
        EventStore.append_event(
            event_type="token.minted",
            aggregate_type="token",
            aggregate_id=token_id,
            data={
                "capacity_id": token.capacity_id,
                "tokenised_mtpd": token.tokenised_mtpd,
                "delivery_start": token.delivery_start,
                "delivery_end": token.delivery_end,
                "compliance_certifications": token.compliance_certifications,
                "molecule": capacity['molecule']
            },
            user_id=user_id,
            correlation_id=correlation_id  # INHERITED - creates chain!
        )
        
        # 2. CREATE TOKEN in database
        cursor.execute("""
            INSERT INTO tokens (
                id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, 
                compliance_certifications, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            token_id,
            token.capacity_id,
            token.tokenised_mtpd,
            token.delivery_start,
            token.delivery_end,
            compliance_json,
            correlation_id
        ))
        
        conn.commit()
        
        # Get created token
        cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created token")
        
        compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
        
        return {
            "id": row['id'],
            "capacity_id": row['capacity_id'],
            "tokenised_mtpd": row['tokenised_mtpd'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "compliance_certifications": compliance,
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id'] if 'correlation_id' in row.keys() else correlation_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create token: {str(e)}")


@router.get("/", response_model=dict)
async def list_tokens(capacity_id: Optional[str] = None):
    """
    List all tokens with optional filtering by capacity
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if capacity_id:
            cursor.execute("""
                SELECT t.*, c.project_name, c.molecule 
                FROM tokens t
                JOIN capacities c ON t.capacity_id = c.id
                WHERE t.capacity_id = ?
                ORDER BY t.created_at DESC
            """, (capacity_id,))
        else:
            cursor.execute("""
                SELECT t.*, c.project_name, c.molecule 
                FROM tokens t
                JOIN capacities c ON t.capacity_id = c.id
                ORDER BY t.created_at DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        tokens = []
        for row in rows:
            compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
            tokens.append({
                "id": row['id'],
                "capacity_id": row['capacity_id'],
                "project_name": row['project_name'],
                "molecule": row['molecule'],
                "tokenised_mtpd": row['tokenised_mtpd'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
                "compliance_certifications": compliance,
                "created_at": row['created_at'],
            })
        
        return {"tokens": tokens}
        
    except Exception as e:
        print(f"Error listing tokens: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tokens: {str(e)}")


@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(token_id: str):
    """
    Get a specific token by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Token not found")
        
        compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
        
        return {
            "id": row['id'],
            "capacity_id": row['capacity_id'],
            "tokenised_mtpd": row['tokenised_mtpd'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "compliance_certifications": compliance,
            "created_at": row['created_at'],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get token: {str(e)}")


@router.delete("/{token_id}", status_code=204)
async def delete_token(token_id: str):
    """
    Delete a token
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Token not found")
        
        conn.commit()
        conn.close()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete token: {str(e)}")
