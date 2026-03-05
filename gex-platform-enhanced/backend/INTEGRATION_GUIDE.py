"""
GreenEarthX Event-Driven Architecture Integration Guide
How to integrate Event Store and State Machines into existing APIs
"""

# ============================================
# EXAMPLE 1: Creating Capacity with Events
# ============================================

from app.core.event_store import EventStore, log_event
from app.core.state_machine import CAPACITY_STATE_MACHINE, transition_state
import uuid

def create_capacity_with_events(capacity_data: dict, user_id: str):
    """
    Create capacity with event emission and state machine
    
    OLD WAY (without events):
        cursor.execute("INSERT INTO capacities (...) VALUES (...)")
        return capacity_id
    
    NEW WAY (with events):
        1. Generate UUID and correlation ID
        2. Emit capacity.created event
        3. Set initial state to 'draft'
        4. Insert into capacities table (projection)
    """
    
    # 1. Generate IDs
    capacity_id = str(uuid.uuid4())
    correlation_id = f"CAPACITY-{capacity_id[:8]}"
    
    # 2. Emit capacity.created event
    event_id = EventStore.append_event(
        event_type="capacity.created",
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        data={
            "project_name": capacity_data['project_name'],
            "molecule": capacity_data['molecule'],
            "capacity_mtpd": capacity_data['capacity_mtpd'],
            "location": capacity_data['location'],
            "status": "draft"  # Initial state
        },
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    # 3. Insert into capacities table (read model/projection)
    # This is the current state, rebuilt from events
    cursor.execute("""
        INSERT INTO capacities (
            id, project_name, molecule, capacity_mtpd, location, created_at
        ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (capacity_id, capacity_data['project_name'], ...))
    
    return {
        "capacity_id": capacity_id,
        "correlation_id": correlation_id,
        "event_id": event_id
    }


# ============================================
# EXAMPLE 2: Updating Capacity Status
# ============================================

def submit_capacity_for_verification(capacity_id: str, user_id: str):
    """
    Submit capacity for verification - uses state machine
    
    OLD WAY:
        UPDATE capacities SET status = 'pending_verification' WHERE id = ?
    
    NEW WAY:
        1. Get current status
        2. Use state machine to validate transition
        3. Emit status_changed event
        4. Update projection
    """
    
    # 1. Get current status from database
    cursor.execute("SELECT status FROM capacities WHERE id = ?", (capacity_id,))
    row = cursor.fetchone()
    current_status = row['status']
    
    # 2. Use state machine to transition
    try:
        event_id = transition_state(
            aggregate_type="capacity",
            aggregate_id=capacity_id,
            from_state=current_status,
            to_state="pending_verification",
            data={"submitted_at": datetime.now().isoformat()},
            user_id=user_id
        )
    except TransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PreconditionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    # 3. Update projection (read model)
    cursor.execute("""
        UPDATE capacities 
        SET status = 'pending_verification', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (capacity_id,))
    
    return {"message": "Submitted for verification", "event_id": event_id}


# ============================================
# EXAMPLE 3: Tokenizing Capacity
# ============================================

def tokenize_capacity(capacity_id: str, tokenized_mtpd: float, user_id: str, correlation_id: str):
    """
    Tokenize capacity - creates token with chain of custody
    
    This shows how correlation_id links capacity → token
    """
    
    # 1. Verify capacity status
    cursor.execute("SELECT status, capacity_mtpd FROM capacities WHERE id = ?", (capacity_id,))
    capacity = cursor.fetchone()
    
    if capacity['status'] != 'verified':
        raise HTTPException(400, "Capacity must be verified before tokenizing")
    
    # 2. Transition capacity to 'tokenizing'
    transition_state(
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        from_state="verified",
        to_state="tokenizing",
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    # 3. Create token with same correlation_id (chain of custody)
    token_id = str(uuid.uuid4())
    
    EventStore.append_event(
        event_type="token.minted",
        aggregate_type="token",
        aggregate_id=token_id,
        data={
            "capacity_id": capacity_id,
            "tokenised_mtpd": tokenized_mtpd,
            "molecule": capacity['molecule']
        },
        user_id=user_id,
        correlation_id=correlation_id  # SAME correlation_id!
    )
    
    # 4. Transition capacity to 'tokenized'
    transition_state(
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        from_state="tokenizing",
        to_state="tokenized",
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    # 5. Insert token into tokens table
    cursor.execute("""
        INSERT INTO tokens (id, capacity_id, tokenised_mtpd, ...)
        VALUES (?, ?, ?, ...)
    """, (token_id, capacity_id, tokenized_mtpd, ...))
    
    return {
        "token_id": token_id,
        "correlation_id": correlation_id,
        "message": "Token minted"
    }


# ============================================
# EXAMPLE 4: Creating Contract from Match
# ============================================

def create_contract_from_match(match_id: str, counterparty: str, user_id: str):
    """
    Create contract from accepted match
    Shows full chain: capacity → token → offer → match → contract
    """
    
    # 1. Get match details
    cursor.execute("""
        SELECT m.*, o.molecule, t.capacity_id, c.correlation_id
        FROM matches m
        JOIN offers o ON m.offer_id = o.id
        JOIN tokens t ON o.token_id = t.id
        JOIN capacities c ON t.capacity_id = c.id
        WHERE m.id = ?
    """, (match_id,))
    match = cursor.fetchone()
    
    # Get correlation_id from original capacity (chain of custody!)
    correlation_id = match['correlation_id']
    
    # 2. Create contract with same correlation_id
    contract_id = str(uuid.uuid4())
    
    EventStore.append_event(
        event_type="contract.created",
        aggregate_type="contract",
        aggregate_id=contract_id,
        data={
            "match_id": match_id,
            "counterparty": counterparty,
            "molecule": match['molecule'],
            "volume_mtpd": match['volume_mtpd'],
            "price_eur_kg": match['price_eur_kg'],
            "status": "draft"
        },
        user_id=user_id,
        correlation_id=correlation_id  # CHAIN OF CUSTODY!
    )
    
    # 3. Insert into contracts table
    cursor.execute("""
        INSERT INTO contracts (id, match_id, counterparty, ...)
        VALUES (?, ?, ?, ...)
    """, (contract_id, match_id, counterparty, ...))
    
    return {
        "contract_id": contract_id,
        "correlation_id": correlation_id,
        "message": "Contract created"
    }


# ============================================
# EXAMPLE 5: Querying Chain of Custody
# ============================================

def get_compliance_thread(correlation_id: str):
    """
    Get complete chain of custody for a molecule
    
    Shows: Capacity → Token → Offer → Match → Contract → Delivery
    """
    
    from app.core.event_store import get_compliance_thread
    
    # Get all events with this correlation_id
    events = get_compliance_thread(correlation_id)
    
    # Format as compliance report
    report = {
        "correlation_id": correlation_id,
        "status": "complete",
        "events": events,
        "summary": {
            "capacity_created": None,
            "capacity_verified": None,
            "token_minted": None,
            "offer_created": None,
            "match_accepted": None,
            "contract_signed": None,
            "delivery_confirmed": None
        }
    }
    
    # Extract key milestones
    for event in events:
        if event['event_type'] == 'capacity.created':
            report['summary']['capacity_created'] = event['timestamp']
        elif event['event_type'] == 'capacity.status_changed' and event['data']['new_status'] == 'verified':
            report['summary']['capacity_verified'] = event['timestamp']
        elif event['event_type'] == 'token.minted':
            report['summary']['token_minted'] = event['timestamp']
        # ... etc
    
    return report


# ============================================
# EXAMPLE 6: Verifying Chain Integrity
# ============================================

def verify_compliance_integrity():
    """
    Verify that event chain has not been tampered with
    Used for regulatory audits
    """
    from app.core.event_store import verify_integrity
    
    try:
        verify_integrity()
        return {
            "status": "verified",
            "message": "Event chain integrity verified. No tampering detected."
        }
    except Exception as e:
        return {
            "status": "tampered",
            "message": str(e),
            "action_required": "IMMEDIATE INVESTIGATION REQUIRED"
        }


# ============================================
# EXAMPLE 7: Getting Entity History
# ============================================

def get_capacity_audit_trail(capacity_id: str):
    """
    Get complete audit trail for a capacity
    Who did what when?
    """
    from app.core.event_store import get_entity_history
    
    events = get_entity_history("capacity", capacity_id)
    
    audit_trail = []
    for event in events:
        audit_trail.append({
            "timestamp": event['timestamp'],
            "event": event['event_type'],
            "user": event['metadata'].get('user_id'),
            "changes": event['data'],
            "event_hash": event['event_hash']
        })
    
    return audit_trail


# ============================================
# EXAMPLE 8: Rebuilding State from Events
# ============================================

def rebuild_capacity_state(capacity_id: str):
    """
    Rebuild capacity state from events (Event Sourcing)
    Useful if projection (database) gets corrupted
    """
    from app.core.event_store import EventStore
    
    state = EventStore.rebuild_projection("capacity", capacity_id)
    
    # Now update database to match
    cursor.execute("""
        UPDATE capacities SET
            project_name = ?,
            molecule = ?,
            status = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        state['project_name'],
        state['molecule'],
        state['status'],
        state['updated_at'],
        capacity_id
    ))
    
    return state


# ============================================
# MIGRATION STRATEGY
# ============================================

"""
STEP 1: Add Event Store to Database
    Run: python backend/app/core/event_store.py
    Creates: event_store table

STEP 2: Update API Endpoints Gradually
    Start with high-value endpoints:
    1. POST /capacities → emit capacity.created event
    2. PATCH /capacities/{id}/status → use state machine
    3. POST /tokens → emit token.minted event
    4. POST /contracts → emit contract.created event

STEP 3: Add correlation_id Tracking
    1. Add correlation_id column to all tables
    2. Generate on capacity creation
    3. Pass through all downstream operations

STEP 4: Add Event Handlers
    Subscribe to events for notifications, analytics, etc.

STEP 5: Enable Audit Features
    1. Add GET /audit/entity/{type}/{id} endpoint
    2. Add GET /compliance/chain/{correlation_id} endpoint
    3. Add POST /audit/verify-integrity endpoint
"""


# ============================================
# PRACTICAL INTEGRATION EXAMPLE
# ============================================

# BEFORE: Simple capacity creation
@router.post("/capacities/")
async def create_capacity_old(data: CapacityCreate):
    cursor.execute("INSERT INTO capacities (...) VALUES (...)")
    return {"id": capacity_id}


# AFTER: Event-driven capacity creation
@router.post("/capacities/")
async def create_capacity_new(data: CapacityCreate, user_id: str = "system"):
    # Generate IDs
    capacity_id = str(uuid.uuid4())
    correlation_id = f"CAP-{capacity_id[:8]}"
    
    # Emit event
    EventStore.append_event(
        event_type="capacity.created",
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        data=data.dict(),
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    # Update projection (database)
    cursor.execute("INSERT INTO capacities (...) VALUES (...)")
    
    return {
        "id": capacity_id,
        "correlation_id": correlation_id,
        "status": "draft"
    }
