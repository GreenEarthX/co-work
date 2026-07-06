"""
Tokenisation API Routes (SQLite)
Convert capacity into tradeable tokens
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import json
import hashlib
import os
import uuid
from datetime import date, datetime, timezone

# EVENT SYSTEM IMPORTS
from app.core.event_store import append_event
from app.core.config import settings

router = APIRouter()

# Database path - 3 levels up from app/api/v1/ to backend/
DB_PATH = settings.SQLITE_DB_PATH

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ═══════════════════════════════════════════════════════════════
# ENUMS — v4.0 token extended schema
# ═══════════════════════════════════════════════════════════════

class MoleculeType(str, Enum):
    H2 = "H2"
    NH3 = "NH3"
    E_METHANOL = "E_METHANOL"
    SAF = "SAF"
    E_DIESEL = "E_DIESEL"


class CertificationPathway(str, Enum):
    STANDARD = "STANDARD"
    RFNBO = "RFNBO"
    CERTIFHY = "CERTIFHY"
    SOVEREIGN_ESG = "SOVEREIGN_ESG"
    VOLUNTARY = "VOLUNTARY"


class TokenLifecycleState(str, Enum):
    MINTED = "MINTED"
    RESERVED = "RESERVED"
    MATCHED = "MATCHED"
    SETTLED = "SETTLED"
    RETIRED = "RETIRED"
    VOIDED = "VOIDED"


class TokenVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    AUDITED = "AUDITED"


# Valid lifecycle state transitions
TOKEN_TRANSITIONS: dict[TokenLifecycleState, list[TokenLifecycleState]] = {
    TokenLifecycleState.MINTED:   [TokenLifecycleState.RESERVED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.RESERVED: [TokenLifecycleState.MATCHED, TokenLifecycleState.MINTED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.MATCHED:  [TokenLifecycleState.SETTLED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.SETTLED:  [TokenLifecycleState.RETIRED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.RETIRED:  [TokenLifecycleState.VOIDED],
    TokenLifecycleState.VOIDED:   [],
}


def _compute_provenance_hash(token_id: str, data: dict) -> str:
    """SHA-256 provenance hash for token chain of custody."""
    payload = {"token_id": token_id, **data, "ts": datetime.now(timezone.utc).isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# Schemas
class SovereignProvenance(BaseModel):
    """Sovereign / DFI provenance metadata for tokenised molecules"""
    sovereign_cert_scheme: Optional[str] = None      # e.g. "RED_III", "45V", "RFNBO"
    sovereign_cert_id: Optional[str] = None           # Certificate reference
    esg_score: Optional[float] = None                 # 0-100 ESG composite
    dfi_funded: Optional[bool] = None                 # DFI/concessional capital backing
    dfi_provider: Optional[str] = None                # e.g. "IFC", "EIB", "KfW"
    country_of_origin: Optional[str] = None           # ISO-3166-1 alpha-2
    ghg_intensity: Optional[float] = None             # kg CO2e/kg product
    additionality_verified: Optional[bool] = None     # DFI additionality confirmed


class TokenCreate(BaseModel):
    capacity_id: str
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_certifications: Optional[List[str]] = None
    sovereign_provenance: Optional[SovereignProvenance] = None  # NEW: sovereign metadata
    # v4.0 extended fields
    molecule: Optional[str] = None  # H2/NH3/E_METHANOL/SAF/E_DIESEL — derived from capacity if not set
    energy_mj: Optional[float] = None
    production_window_start: Optional[str] = None
    production_window_end: Optional[str] = None
    certification_pathway: Optional[str] = None
    carbon_intensity_gco2e_mj: Optional[float] = None
    mass_balance_lot_id: Optional[str] = None
    verification_state: Optional[str] = "UNVERIFIED"

class TokenResponse(BaseModel):
    id: str
    capacity_id: str
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_certifications: Optional[List[str]] = None
    sovereign_provenance: Optional[SovereignProvenance] = None  # NEW
    created_at: str
    correlation_id: Optional[str] = None  # NEW: Inherited from capacity
    # v4.0 extended fields
    molecule: Optional[str] = None
    energy_mj: Optional[float] = None
    production_window_start: Optional[str] = None
    production_window_end: Optional[str] = None
    certification_pathway: Optional[str] = None
    carbon_intensity_gco2e_mj: Optional[float] = None
    mass_balance_lot_id: Optional[str] = None
    lifecycle_state: Optional[str] = "MINTED"
    provenance_hash: Optional[str] = None
    retirement_event_id: Optional[str] = None
    carbon_attribution_event_id: Optional[str] = None
    verification_state: Optional[str] = "UNVERIFIED"


class TokenTransition(BaseModel):
    new_state: str
    changed_by: str = "system"
    justification: str = ""


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
        
        # Serialize sovereign provenance
        sovereign_json = None
        if token.sovereign_provenance:
            sovereign_json = json.dumps(token.sovereign_provenance.model_dump(exclude_none=True))

        # 1. EMIT EVENT (with inherited correlation_id)
        event_data = {
            "capacity_id": token.capacity_id,
            "tokenised_mtpd": token.tokenised_mtpd,
            "delivery_start": token.delivery_start,
            "delivery_end": token.delivery_end,
            "compliance_certifications": token.compliance_certifications,
            "molecule": capacity['molecule'],
        }
        if token.sovereign_provenance:
            event_data["sovereign_provenance"] = token.sovereign_provenance.model_dump(exclude_none=True)

        append_event(
            event_type="token.minted",
            aggregate_type="token",
            aggregate_id=token_id,
            data=event_data,
            user_id=user_id,
            correlation_id=correlation_id  # INHERITED - creates chain!
        )
        
        # Derive molecule from capacity if not provided
        token_molecule = token.molecule or (capacity['molecule'] if 'molecule' in capacity.keys() else None)

        # Compute provenance hash
        provenance_hash = _compute_provenance_hash(token_id, {
            "capacity_id": token.capacity_id,
            "tokenised_mtpd": token.tokenised_mtpd,
            "molecule": token_molecule,
        })

        # 2. CREATE TOKEN in database (v4.0 extended)
        cursor.execute("""
            INSERT INTO tokens (
                id, capacity_id, tokenised_mtpd, delivery_start, delivery_end,
                compliance_certifications, correlation_id, sovereign_provenance,
                molecule, energy_mj, production_window_start, production_window_end,
                certification_pathway, carbon_intensity_gco2e_mj, mass_balance_lot_id,
                lifecycle_state, provenance_hash, verification_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_id,
            token.capacity_id,
            token.tokenised_mtpd,
            token.delivery_start,
            token.delivery_end,
            compliance_json,
            correlation_id,
            sovereign_json,
            token_molecule,
            token.energy_mj,
            token.production_window_start,
            token.production_window_end,
            token.certification_pathway,
            token.carbon_intensity_gco2e_mj,
            token.mass_balance_lot_id,
            TokenLifecycleState.MINTED.value,
            provenance_hash,
            token.verification_state or TokenVerificationState.UNVERIFIED.value,
        ))

        conn.commit()

        # Get created token
        cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=500, detail="Failed to retrieve created token")

        compliance = json.loads(row['compliance_certifications']) if row['compliance_certifications'] else None
        sovereign = None
        if 'sovereign_provenance' in row.keys() and row['sovereign_provenance']:
            sovereign = json.loads(row['sovereign_provenance'])

        return {
            "id": row['id'],
            "capacity_id": row['capacity_id'],
            "tokenised_mtpd": row['tokenised_mtpd'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "compliance_certifications": compliance,
            "sovereign_provenance": sovereign,
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id'] if 'correlation_id' in row.keys() else correlation_id,
            "molecule": row['molecule'] if 'molecule' in row.keys() else token_molecule,
            "energy_mj": row['energy_mj'] if 'energy_mj' in row.keys() else None,
            "production_window_start": row['production_window_start'] if 'production_window_start' in row.keys() else None,
            "production_window_end": row['production_window_end'] if 'production_window_end' in row.keys() else None,
            "certification_pathway": row['certification_pathway'] if 'certification_pathway' in row.keys() else None,
            "carbon_intensity_gco2e_mj": row['carbon_intensity_gco2e_mj'] if 'carbon_intensity_gco2e_mj' in row.keys() else None,
            "mass_balance_lot_id": row['mass_balance_lot_id'] if 'mass_balance_lot_id' in row.keys() else None,
            "lifecycle_state": row['lifecycle_state'] if 'lifecycle_state' in row.keys() else "MINTED",
            "provenance_hash": row['provenance_hash'] if 'provenance_hash' in row.keys() else provenance_hash,
            "retirement_event_id": row['retirement_event_id'] if 'retirement_event_id' in row.keys() else None,
            "carbon_attribution_event_id": row['carbon_attribution_event_id'] if 'carbon_attribution_event_id' in row.keys() else None,
            "verification_state": row['verification_state'] if 'verification_state' in row.keys() else "UNVERIFIED",
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
        
        sovereign = None
        if 'sovereign_provenance' in row.keys() and row['sovereign_provenance']:
            sovereign = json.loads(row['sovereign_provenance'])

        return {
            "id": row['id'],
            "capacity_id": row['capacity_id'],
            "tokenised_mtpd": row['tokenised_mtpd'],
            "delivery_start": row['delivery_start'],
            "delivery_end": row['delivery_end'],
            "compliance_certifications": compliance,
            "sovereign_provenance": sovereign,
            "created_at": row['created_at'],
            "correlation_id": row['correlation_id'] if 'correlation_id' in row.keys() else None,
            "molecule": row['molecule'] if 'molecule' in row.keys() else None,
            "energy_mj": row['energy_mj'] if 'energy_mj' in row.keys() else None,
            "production_window_start": row['production_window_start'] if 'production_window_start' in row.keys() else None,
            "production_window_end": row['production_window_end'] if 'production_window_end' in row.keys() else None,
            "certification_pathway": row['certification_pathway'] if 'certification_pathway' in row.keys() else None,
            "carbon_intensity_gco2e_mj": row['carbon_intensity_gco2e_mj'] if 'carbon_intensity_gco2e_mj' in row.keys() else None,
            "mass_balance_lot_id": row['mass_balance_lot_id'] if 'mass_balance_lot_id' in row.keys() else None,
            "lifecycle_state": row['lifecycle_state'] if 'lifecycle_state' in row.keys() else "MINTED",
            "provenance_hash": row['provenance_hash'] if 'provenance_hash' in row.keys() else None,
            "retirement_event_id": row['retirement_event_id'] if 'retirement_event_id' in row.keys() else None,
            "carbon_attribution_event_id": row['carbon_attribution_event_id'] if 'carbon_attribution_event_id' in row.keys() else None,
            "verification_state": row['verification_state'] if 'verification_state' in row.keys() else "UNVERIFIED",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get token: {str(e)}")


@router.post("/{token_id}/transition", status_code=200)
async def transition_token(token_id: str, transition: TokenTransition, user_id: str = "system"):
    """
    Advance token lifecycle state.
    Valid transitions:
      MINTED -> RESERVED, VOIDED
      RESERVED -> MATCHED, MINTED (unlist), VOIDED
      MATCHED -> SETTLED, VOIDED
      SETTLED -> RETIRED, VOIDED
      RETIRED -> VOIDED
      VOIDED -> (terminal)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Token not found")

        current_state_str = row['lifecycle_state'] if 'lifecycle_state' in row.keys() else "MINTED"
        try:
            current_state = TokenLifecycleState(current_state_str)
        except ValueError:
            current_state = TokenLifecycleState.MINTED

        try:
            new_state = TokenLifecycleState(transition.new_state)
        except ValueError:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Invalid state: {transition.new_state}")

        valid_next = TOKEN_TRANSITIONS.get(current_state, [])
        if new_state not in valid_next:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transition: {current_state.value} -> {new_state.value}. "
                       f"Valid: {[s.value for s in valid_next]}"
            )

        now = datetime.now(timezone.utc).isoformat()

        # Update lifecycle state
        cursor.execute(
            "UPDATE tokens SET lifecycle_state = ? WHERE id = ?",
            (new_state.value, token_id)
        )

        # If retiring, store retirement event id
        if new_state == TokenLifecycleState.RETIRED:
            retirement_event_id = str(uuid.uuid4())
            cursor.execute(
                "UPDATE tokens SET retirement_event_id = ? WHERE id = ?",
                (retirement_event_id, token_id)
            )

        # Emit event
        correlation_id = row['correlation_id'] if 'correlation_id' in row.keys() else f"TOK-{token_id[:8]}"
        append_event(
            event_type=f"token.{new_state.value.lower()}",
            aggregate_type="token",
            aggregate_id=token_id,
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
            "token_id": token_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "transitioned_at": now,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error transitioning token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to transition token: {str(e)}")


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
