"""
Contracts API Routes (SQLite)
Manage supply contracts using the existing contracts table
EVENT-DRIVEN: Inherits correlation_id for full chain of custody
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
class ContractCreate(BaseModel):
    match_id: str
    counterparty: str
    delivery_terms: str
    payment_terms: str

class ContractResponse(BaseModel):
    id: str
    project_id: str
    contract_id_external: str
    counterparty: str
    molecule: str
    volume_mtpd: float
    price_eur_kg: float
    start_date: str
    end_date: str
    tenor_years: int
    pricing_basis: Optional[str] = None
    credit_rating: Optional[str] = None
    status: str
    created_at: str
    project_name: Optional[str] = None
    correlation_id: Optional[str] = None  # NEW: Complete chain of custody!


@router.post("/", response_model=ContractResponse, status_code=201)
async def create_contract(contract: ContractCreate, user_id: str = "system"):
    """
    Create contract from accepted match using existing contracts table
    EVENT-DRIVEN: Completes full chain of custody from capacity to contract!
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get match details with project info AND correlation_id
        cursor.execute("""
            SELECT 
                m.*,
                o.molecule,
                o.delivery_start,
                o.delivery_end,
                c.id as capacity_id,
                c.project_name,
                c.correlation_id
            FROM matches m
            JOIN offers o ON m.offer_id = o.id
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE m.id = ? AND m.status = 'accepted'
        """, (contract.match_id,))
        match = cursor.fetchone()
        
        if not match:
            conn.close()
            raise HTTPException(status_code=404, detail="Accepted match not found")
        
        # INHERIT correlation_id from capacity (COMPLETE CHAIN!)
        correlation_id = match['correlation_id'] if 'correlation_id' in match.keys() else f"CAP-{match['capacity_id'][:8]}"
        
        # Generate IDs
        contract_id = str(uuid.uuid4())
        external_id = f"CONT-{contract_id[:8].upper()}"
        
        # Calculate tenor
        from datetime import datetime
        start = datetime.strptime(match['delivery_start'], '%Y-%m-%d')
        end = datetime.strptime(match['delivery_end'], '%Y-%m-%d')
        tenor_years = int((end - start).days / 365.25)
        
        # 1. EMIT EVENT (with inherited correlation_id - COMPLETES CHAIN!)
        EventStore.append_event(
            event_type="contract.created",
            aggregate_type="contract",
            aggregate_id=contract_id,
            data={
                "match_id": contract.match_id,
                "contract_id_external": external_id,
                "counterparty": contract.counterparty,
                "molecule": match['molecule'],
                "volume_mtpd": match['volume_mtpd'],
                "price_eur_kg": match['price_eur_kg'],
                "start_date": match['delivery_start'],
                "end_date": match['delivery_end'],
                "tenor_years": tenor_years,
                "delivery_terms": contract.delivery_terms,
                "payment_terms": contract.payment_terms,
                "status": "active"
            },
            user_id=user_id,
            correlation_id=correlation_id  # INHERITED - COMPLETES CHAIN: capacity → token → offer → match → contract!
        )
        
        # 2. CREATE CONTRACT in database
        cursor.execute("""
            INSERT INTO contracts (
                id, project_id, contract_id_external, counterparty, molecule,
                volume_mtpd, price_eur_kg, pricing_basis,
                start_date, end_date, tenor_years, status, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            contract_id,
            match['capacity_id'],
            external_id,
            contract.counterparty,
            match['molecule'],
            match['volume_mtpd'],
            match['price_eur_kg'],
            f"{contract.delivery_terms} | {contract.payment_terms}",
            match['delivery_start'],
            match['delivery_end'],
            tenor_years,
            'active',
            correlation_id
        ))
        
        conn.commit()
        
        # Get created contract
        cursor.execute("""
            SELECT c.*, p.project_name
            FROM contracts c
            LEFT JOIN capacities p ON c.project_id = p.id
            WHERE c.id = ?
        """, (contract_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created contract")
        
        return {
            "id": row['id'],
            "project_id": row['project_id'],
            "contract_id_external": row['contract_id_external'],
            "counterparty": row['counterparty'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "start_date": row['start_date'],
            "end_date": row['end_date'],
            "tenor_years": row['tenor_years'],
            "pricing_basis": row['pricing_basis'],
            "credit_rating": row['credit_rating'],
            "status": row['status'],
            "created_at": row['created_at'],
            "project_name": row['project_name'],
            "correlation_id": row['correlation_id'] if 'correlation_id' in row.keys() else correlation_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating contract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create contract: {str(e)}")


@router.get("/", response_model=dict)
async def list_contracts(
    molecule: Optional[str] = None,
    status: Optional[str] = None
):
    """
    List all contracts with optional filtering
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT c.*, p.project_name
            FROM contracts c
            LEFT JOIN capacities p ON c.project_id = p.id
            WHERE 1=1
        """
        params = []
        
        if molecule:
            query += " AND c.molecule = ?"
            params.append(molecule)
        
        if status:
            query += " AND c.status = ?"
            params.append(status)
        
        query += " ORDER BY c.created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        contracts = []
        for row in rows:
            contracts.append({
                "id": row['id'],
                "project_id": row['project_id'],
                "contract_id_external": row['contract_id_external'],
                "counterparty": row['counterparty'],
                "molecule": row['molecule'],
                "volume_mtpd": row['volume_mtpd'],
                "price_eur_kg": row['price_eur_kg'],
                "start_date": row['start_date'],
                "end_date": row['end_date'],
                "tenor_years": row['tenor_years'],
                "pricing_basis": row['pricing_basis'],
                "credit_rating": row['credit_rating'],
                "status": row['status'],
                "created_at": row['created_at'],
                "project_name": row['project_name'],
            })
        
        return {"contracts": contracts}
        
    except Exception as e:
        print(f"Error listing contracts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list contracts: {str(e)}")


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(contract_id: str):
    """
    Get a specific contract by ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.*, p.project_name
            FROM contracts c
            LEFT JOIN capacities p ON c.project_id = p.id
            WHERE c.id = ?
        """, (contract_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        return {
            "id": row['id'],
            "project_id": row['project_id'],
            "contract_id_external": row['contract_id_external'],
            "counterparty": row['counterparty'],
            "molecule": row['molecule'],
            "volume_mtpd": row['volume_mtpd'],
            "price_eur_kg": row['price_eur_kg'],
            "start_date": row['start_date'],
            "end_date": row['end_date'],
            "tenor_years": row['tenor_years'],
            "pricing_basis": row['pricing_basis'],
            "credit_rating": row['credit_rating'],
            "status": row['status'],
            "created_at": row['created_at'],
            "project_name": row['project_name'],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting contract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get contract: {str(e)}")


@router.patch("/{contract_id}/status", status_code=200)
async def update_contract_status(
    contract_id: str,
    new_status: str,
    user_id: str = "system",
    notes: Optional[str] = None
):
    """
    Update contract status using state machine
    Enforces valid transitions and business rules
    """
    try:
        from app.core.state_machine import transition_state, TransitionError, PreconditionError
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current contract
        cursor.execute("SELECT status, correlation_id FROM contracts WHERE id = ?", (contract_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Contract not found")
        
        current_status = row['status'] if row['status'] else 'draft'
        correlation_id = row['correlation_id'] if 'correlation_id' in row.keys() else None
        
        try:
            # Use state machine to validate and emit event
            event_id = transition_state(
                aggregate_type="contract",
                aggregate_id=contract_id,
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
            UPDATE contracts 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, contract_id))
        
        conn.commit()
        conn.close()
        
        return {
            "message": "Status updated successfully",
            "contract_id": contract_id,
            "old_status": current_status,
            "new_status": new_status,
            "event_id": event_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating contract status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@router.get("/{contract_id}/transitions", status_code=200)
async def get_valid_contract_transitions(contract_id: str):
    """
    Get valid next states for a contract
    Helps UI show only valid actions
    """
    try:
        from app.core.state_machine import get_valid_next_states
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT status FROM contracts WHERE id = ?", (contract_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        current_status = row['status'] if row['status'] else 'draft'
        valid_transitions = get_valid_next_states("contract", current_status)
        
        return {
            "contract_id": contract_id,
            "current_status": current_status,
            "valid_transitions": valid_transitions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting valid transitions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transitions: {str(e)}")


@router.get("/accepted-matches/available", response_model=dict)
async def get_accepted_matches():
    """
    Get accepted matches that can be converted to contracts
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                m.id,
                m.match_score,
                m.volume_mtpd,
                m.price_eur_kg,
                o.molecule,
                o.delivery_start,
                o.delivery_end,
                c.project_name
            FROM matches m
            JOIN offers o ON m.offer_id = o.id
            JOIN tokens t ON o.token_id = t.id
            JOIN capacities c ON t.capacity_id = c.id
            WHERE m.status = 'accepted'
            ORDER BY m.created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        matches = []
        for row in rows:
            matches.append({
                "id": row['id'],
                "match_score": row['match_score'],
                "volume_mtpd": row['volume_mtpd'],
                "price_eur_kg": row['price_eur_kg'],
                "molecule": row['molecule'],
                "delivery_start": row['delivery_start'],
                "delivery_end": row['delivery_end'],
                "project_name": row['project_name'],
            })
        
        return {"matches": matches}
        
    except Exception as e:
        print(f"Error getting accepted matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get accepted matches: {str(e)}")


@router.delete("/{contract_id}", status_code=204)
async def delete_contract(contract_id: str):
    """
    Delete a contract
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Contract not found")
        
        conn.commit()
        conn.close()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting contract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete contract: {str(e)}")
