"""
Tokenisation API Routes (SQLite)
Convert capacity into tradeable tokens
EVENT-DRIVEN: Inherits correlation_id for chain of custody
"""
from typing import List, Optional
from enum import Enum
from fastapi import APIRouter, HTTPException, Request
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
    """
    Token lifecycle. The green attribute is NOT separable from the molecule
    token — it travels as an attribute of the token, and it is *claimed* exactly
    once, at retirement. Every state below is defined in terms of that claim.

    MINTED    — capacity tokenised. Claim exists, unallocated.
    RESERVED  — held against a prospective buyer. Claim intact, not committed.
    MATCHED   — bound to a contract. Claim committed but not delivered.
    SETTLED   — molecule delivered. Claim live and claimable by the holder.
    RETIRED   — molecule consumed, claim MADE. The green attribute is spent.
                Terminal for claim purposes: no path leaves RETIRED for any
                claimable state (see CLAIMABLE_STATES / the guardrail test).
    ANNULLED  — the token WAS valid and its claim is now annulled with cause
                (erroneous retirement, disputed delivery). Terminal, and NOT
                claimable: annulment corrects the record, it never returns the
                claim to circulation. Remedy for a genuinely undelivered
                molecule is a compensating issuance, not resurrection.
    VOIDED    — issued in error, NEVER valid. Available only before delivery
                (pre-SETTLED). Once a molecule has settled, the delivery is a
                fact and the remedy is ANNULLED, not VOIDED.
    """
    MINTED = "MINTED"
    RESERVED = "RESERVED"
    MATCHED = "MATCHED"
    SETTLED = "SETTLED"
    RETIRED = "RETIRED"
    ANNULLED = "ANNULLED"
    VOIDED = "VOIDED"


class TokenVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    AUDITED = "AUDITED"


# ── The claim invariant ─────────────────────────────────────────────────────
# States in which the token still carries a live, claimable green attribute.
# The whole anti-double-count guarantee reduces to one property:
#   no path out of RETIRED reaches any of these.
# tests/test_token_lifecycle.py proves it by graph reachability, so the property
# survives future edits to the table below.
CLAIMABLE_STATES: frozenset[TokenLifecycleState] = frozenset({
    TokenLifecycleState.MINTED,
    TokenLifecycleState.RESERVED,
    TokenLifecycleState.MATCHED,
    TokenLifecycleState.SETTLED,
})

# Terminal — no exit at all. Mirrors ClaimState.SUPERSEDED in the truth stack.
TERMINAL_STATES: frozenset[TokenLifecycleState] = frozenset({
    TokenLifecycleState.ANNULLED,
    TokenLifecycleState.VOIDED,
})

# Valid lifecycle state transitions.
# RETIRED keeps exactly one exit — to ANNULLED — so a genuine error stays
# correctable. ANNULLED is terminal and not claimable, so correcting the record
# never puts the green claim back in circulation.
TOKEN_TRANSITIONS: dict[TokenLifecycleState, list[TokenLifecycleState]] = {
    TokenLifecycleState.MINTED:   [TokenLifecycleState.RESERVED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.RESERVED: [TokenLifecycleState.MATCHED, TokenLifecycleState.MINTED, TokenLifecycleState.VOIDED],
    TokenLifecycleState.MATCHED:  [TokenLifecycleState.SETTLED, TokenLifecycleState.VOIDED],
    # SETTLED: delivery is a fact — it cannot be "never valid", so no VOIDED.
    TokenLifecycleState.SETTLED:  [TokenLifecycleState.RETIRED, TokenLifecycleState.ANNULLED],
    TokenLifecycleState.RETIRED:  [TokenLifecycleState.ANNULLED],
    TokenLifecycleState.ANNULLED: [],
    TokenLifecycleState.VOIDED:   [],
}

# ── Authority for the two claim-touching operations ─────────────────────────
# Annulment of a made claim is the highest-scrutiny action in the platform: it
# is the only operation that reaches a spent green attribute. Treated as a
# waiver-class action — named authority, mandatory rationale, segregation of
# duties, and a durable record.
#
# NOTE: /api/v1/tokens maps to the "finance" domain, whose write policy admits
# business functions {FINANCE_TREASURY, EXECUTIVE} and service types
# {BANK, DFI, INSURER}. Annulment authority is deliberately NARROWER than that
# outer gate, and both must pass. REGISTRY is listed here as the intended
# registry-operator authority but does not currently satisfy the finance domain
# policy — flagged rather than silently widened in core/domain_authorization.py.
ANNULMENT_AUTHORITY_FUNCTIONS: frozenset[str] = frozenset({"EXECUTIVE"})
ANNULMENT_AUTHORITY_SERVICE_TYPES: frozenset[str] = frozenset({"REGISTRY"})
MIN_ANNULMENT_RATIONALE_CHARS = 20


# Accountability columns for the two claim-touching operations. Additive and
# idempotent — the tokens table predates them and carries no rows to migrate.
_LIFECYCLE_COLUMNS = {
    # Pre-existing gap: the shipped tokens table never had these two, so the
    # retire path would have failed on "no such column: retirement_event_id".
    "retirement_event_id": "TEXT",
    "carbon_attribution_event_id": "TEXT",
    "retired_by": "TEXT",
    "retired_at": "TEXT",
    "retirement_evidence_ref": "TEXT",
    "annulment_event_id": "TEXT",
    "annulled_by": "TEXT",
    "annulled_at": "TEXT",
    "annulment_reason": "TEXT",
    "annulment_authority_ref": "TEXT",
    "supersedes_retirement_event_id": "TEXT",
}


def _ensure_lifecycle_columns(conn) -> None:
    """
    Add the retirement/annulment accountability columns if absent.

    SQLite only — PRAGMA is not PostgreSQL, and on PostgreSQL the schema is
    owned by alembic (migration 036), which also declares the lifecycle CHECK
    constraint and the RLS policy. Running DDL from here would bypass both.
    """
    from app.core.db_backend import market_is_postgres

    if market_is_postgres():
        return
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(tokens)").fetchall()}
    if not existing:
        return  # table not created yet — creator owns the schema
    for col, coltype in _LIFECYCLE_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE tokens ADD COLUMN {col} {coltype}")
    conn.commit()


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
    # Retirement / annulment accountability. Annulment fields are populated on
    # the SAME row as the retirement it corrects — the retirement is never
    # erased, so a consumption certificate issued against retirement_event_id
    # is discoverable as superseded by whoever relied on it.
    retired_by: Optional[str] = None
    retired_at: Optional[str] = None
    retirement_evidence_ref: Optional[str] = None
    annulment_event_id: Optional[str] = None
    annulled_by: Optional[str] = None
    annulled_at: Optional[str] = None
    annulment_reason: Optional[str] = None
    annulment_authority_ref: Optional[str] = None
    supersedes_retirement_event_id: Optional[str] = None


class TokenTransition(BaseModel):
    new_state: str
    justification: str = ""
    # Required to reach RETIRED: retirement asserts the molecule was consumed,
    # so it must name the evidence for that consumption. Same discipline as
    # development packages refusing EVIDENCED without evidence_refs.
    consumption_evidence_ref: Optional[str] = None
    # Required to reach ANNULLED: who authorised it and on what grounds.
    annulment_authority_ref: Optional[str] = None


def _actor_identity(request) -> tuple[str, dict]:
    """
    The acting identity for a lifecycle change. There is no anonymous actor:
    a state change on the object that carries the green claim is attributable
    or it does not happen. `require_authenticated` (global dependency) has
    already populated request.state.user_payload.
    """
    payload = getattr(request.state, "user_payload", None) or {}
    actor = payload.get("sub") or payload.get("user_id") or payload.get("email")
    if not actor:
        raise HTTPException(
            status_code=401,
            detail="An attributable identity is required to change token lifecycle state",
        )
    return str(actor), payload


def _guard_retirement(transition: "TokenTransition") -> None:
    """Retirement is the moment the green claim is made — it must be evidenced."""
    ref = (transition.consumption_evidence_ref or "").strip()
    if not ref:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "retirement_evidence_required",
                "reason": "Retirement asserts the molecule was consumed and claims the "
                          "green attribute. It requires consumption_evidence_ref.",
            },
        )


def _guard_annulment(transition: "TokenTransition", payload: dict,
                     actor: str, retired_by: Optional[str]) -> None:
    """
    Waiver-class guard: authority + rationale + segregation of duties.
    Annulment does not restore the claim; it records that a made claim is void.
    """
    fn = payload.get("business_function")
    st = payload.get("service_type")
    if fn not in ANNULMENT_AUTHORITY_FUNCTIONS and st not in ANNULMENT_AUTHORITY_SERVICE_TYPES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "annulment_authority_required",
                "reason": f"business function {fn!r} / service type {st!r} may not annul a "
                          f"token claim (allowed functions: {sorted(ANNULMENT_AUTHORITY_FUNCTIONS)}, "
                          f"service types: {sorted(ANNULMENT_AUTHORITY_SERVICE_TYPES)})",
            },
        )

    rationale = (transition.justification or "").strip()
    if len(rationale) < MIN_ANNULMENT_RATIONALE_CHARS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "annulment_rationale_required",
                "reason": f"Annulling a claim requires a written rationale of at least "
                          f"{MIN_ANNULMENT_RATIONALE_CHARS} characters.",
            },
        )

    if not (transition.annulment_authority_ref or "").strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "annulment_authority_ref_required",
                "reason": "Annulment requires annulment_authority_ref naming the approval "
                          "under which it is made.",
            },
        )

    # Segregation of duties — the party that made the claim cannot unmake it.
    if retired_by and retired_by == actor:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "annulment_segregation_of_duties",
                "reason": "The actor who retired this token may not annul the retirement.",
            },
        )


@router.post("/", response_model=TokenResponse, status_code=201)
async def create_token(token: TokenCreate, request: Request):
    """
    Tokenise capacity - convert production capacity into tradeable tokens
    EVENT-DRIVEN: Inherits correlation_id from capacity for chain of custody

    Minting is where the green claim enters circulation, so it is attributable
    for the same reason retirement is — an anonymous origin breaks the chain
    the retirement guards protect.
    """
    try:
        user_id, _ = _actor_identity(request)
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
            **{c: (row[c] if c in row.keys() else None) for c in _LIFECYCLE_COLUMNS},
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
            **{c: (row[c] if c in row.keys() else None) for c in _LIFECYCLE_COLUMNS},
            "carbon_attribution_event_id": row['carbon_attribution_event_id'] if 'carbon_attribution_event_id' in row.keys() else None,
            "verification_state": row['verification_state'] if 'verification_state' in row.keys() else "UNVERIFIED",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get token: {str(e)}")


@router.post("/{token_id}/transition", status_code=200)
async def transition_token(token_id: str, transition: TokenTransition, request: Request):
    """
    Advance token lifecycle state. See TokenLifecycleState for what each state
    asserts about the green claim; TOKEN_TRANSITIONS is the authoritative table
    (this docstring deliberately does not restate it — it drifted before).

    Two operations touch the green claim and carry extra guards:
      · RETIRED  — makes the claim. Requires consumption_evidence_ref.
      · ANNULLED — annuls a made claim. Requires named authority, a written
                   rationale, an authority reference, and an actor other than
                   the one who retired the token. Does NOT restore the claim.
    """
    try:
        actor, payload = _actor_identity(request)

        conn = get_db_connection()
        _ensure_lifecycle_columns(conn)
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
            reason = (
                f"Invalid transition: {current_state.value} -> {new_state.value}. "
                f"Valid: {[s.value for s in valid_next]}"
            )
            if current_state == TokenLifecycleState.RETIRED:
                reason += (
                    " — the green claim on this token has been made and is spent. "
                    "An erroneous retirement is corrected by ANNULLED (which does not "
                    "restore the claim); an undelivered molecule is remedied by a "
                    "compensating issuance."
                )
            raise HTTPException(status_code=400, detail=reason)

        # ── Claim-touching guards ───────────────────────────────────────────
        retired_by = row["retired_by"] if "retired_by" in row.keys() else None
        try:
            if new_state == TokenLifecycleState.RETIRED:
                _guard_retirement(transition)
            elif new_state == TokenLifecycleState.ANNULLED:
                _guard_annulment(transition, payload, actor, retired_by)
        except HTTPException:
            conn.close()
            raise

        now = datetime.now(timezone.utc).isoformat()
        prior_retirement_event_id = (
            row["retirement_event_id"] if "retirement_event_id" in row.keys() else None
        )

        # ── Event FIRST, projection second ──────────────────────────────────
        # This module is event-sourced: the event is the fact, the tokens row is
        # a read model. append_event() opens its OWN connection, so it must not
        # run inside an open write transaction on `conn` — SQLite permits one
        # writer, and the append fails with "database is locked". create_token
        # already orders it this way; transition_token did not, which meant no
        # transition that reached the UPDATE could ever complete.
        retirement_event_id = (
            str(uuid.uuid4()) if new_state == TokenLifecycleState.RETIRED else None
        )
        annulment_event_id = (
            str(uuid.uuid4()) if new_state == TokenLifecycleState.ANNULLED else None
        )

        correlation_id = row['correlation_id'] if 'correlation_id' in row.keys() else f"TOK-{token_id[:8]}"
        event_data = {
            "from_state": current_state.value,
            "to_state": new_state.value,
            # append_event() promotes exactly these two payload keys into the
            # dedicated platform_events.previous_state / .new_state columns
            # (note the asymmetric names it looks for), so a lifecycle audit
            # does not have to parse payload JSON. from_state/to_state above
            # are kept for existing consumers.
            "previous_state": current_state.value,
            "new_status": new_state.value,
            "changed_by": actor,
            "justification": transition.justification,
        }
        if new_state == TokenLifecycleState.RETIRED:
            # The retirement event id IS the consumption certificate reference.
            event_data["retirement_event_id"] = retirement_event_id
            event_data["consumption_evidence_ref"] = transition.consumption_evidence_ref
        elif new_state == TokenLifecycleState.ANNULLED:
            # Append-only correction: the retirement record is NOT erased. The
            # annulment supersedes it, so anything issued at retirement (the
            # consumption certificate) is discoverable as no longer relied upon.
            event_data.update({
                "annulment_event_id": annulment_event_id,
                "annulment_authority_ref": transition.annulment_authority_ref,
                "supersedes_retirement_event_id": prior_retirement_event_id,
                "claim_restored": False,
            })
        append_event(
            event_type=f"token.{new_state.value.lower()}",
            aggregate_type="token",
            aggregate_id=token_id,
            data=event_data,
            user_id=actor,
            correlation_id=correlation_id,
        )

        # ── Projection ──────────────────────────────────────────────────────
        cursor.execute(
            "UPDATE tokens SET lifecycle_state = ? WHERE id = ?",
            (new_state.value, token_id)
        )
        if new_state == TokenLifecycleState.RETIRED:
            cursor.execute(
                "UPDATE tokens SET retirement_event_id = ?, retired_by = ?, "
                "retired_at = ?, retirement_evidence_ref = ? WHERE id = ?",
                (retirement_event_id, actor, now,
                 (transition.consumption_evidence_ref or "").strip(), token_id)
            )
        elif new_state == TokenLifecycleState.ANNULLED:
            cursor.execute(
                "UPDATE tokens SET annulment_event_id = ?, annulled_by = ?, "
                "annulled_at = ?, annulment_reason = ?, annulment_authority_ref = ?, "
                "supersedes_retirement_event_id = ? WHERE id = ?",
                (annulment_event_id, actor, now, transition.justification.strip(),
                 (transition.annulment_authority_ref or "").strip(),
                 prior_retirement_event_id, token_id)
            )

        conn.commit()
        conn.close()

        result = {
            "token_id": token_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "transitioned_at": now,
            "changed_by": actor,
            "claim_claimable": new_state in CLAIMABLE_STATES,
        }
        if annulment_event_id:
            result["annulment_event_id"] = annulment_event_id
            result["claim_restored"] = False
        return result

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
