"""
EXAMPLE: Capacity Endpoint with Event Integration
This shows the before/after of integrating events into existing API
"""

# ============================================
# BEFORE: No Events
# ============================================

@router.post("/", response_model=CapacityResponse, status_code=201)
async def create_capacity_OLD(capacity: CapacityCreate):
    """OLD VERSION - No event tracking"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Generate ID
    capacity_id = str(uuid.uuid4())
    
    # Insert into database
    cursor.execute("""
        INSERT INTO capacities (
            id, project_name, molecule, capacity_mtpd, location
        ) VALUES (?, ?, ?, ?, ?)
    """, (capacity_id, capacity.project_name, capacity.molecule, 
          capacity.capacity_mtpd, capacity.location))
    
    conn.commit()
    conn.close()
    
    return {"id": capacity_id, ...}


# ============================================
# AFTER: With Events
# ============================================

from app.core.event_store import EventStore

@router.post("/", response_model=CapacityResponse, status_code=201)
async def create_capacity_NEW(
    capacity: CapacityCreate,
    user_id: str = "system"  # In production, get from JWT token
):
    """NEW VERSION - Full event tracking"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Generate IDs
    capacity_id = str(uuid.uuid4())
    correlation_id = f"CAP-{capacity_id[:8].upper()}"  # Chain of custody ID
    
    # 1. EMIT EVENT (immutable log)
    EventStore.append_event(
        event_type="capacity.created",
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        data={
            "project_name": capacity.project_name,
            "molecule": capacity.molecule,
            "capacity_mtpd": capacity.capacity_mtpd,
            "location": capacity.location,
            "status": "draft"
        },
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    # 2. UPDATE PROJECTION (database - read model)
    cursor.execute("""
        INSERT INTO capacities (
            id, project_name, molecule, capacity_mtpd, location,
            status, correlation_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (capacity_id, capacity.project_name, capacity.molecule, 
          capacity.capacity_mtpd, capacity.location, 
          "draft", correlation_id))
    
    conn.commit()
    conn.close()
    
    return {
        "id": capacity_id,
        "correlation_id": correlation_id,  # Return for tracking
        "status": "draft",
        ...
    }


# ============================================
# BENEFITS OF EVENT VERSION
# ============================================

"""
1. Complete Audit Trail
   - Who created capacity? user_id logged
   - When? timestamp automatic
   - What data? Full payload in event

2. Chain of Custody
   - correlation_id links capacity → token → contract
   - Can track molecule lifecycle

3. Immutable Log
   - Events can't be changed
   - Cryptographically chained
   - Tamper-evident

4. Event Sourcing
   - Can rebuild capacity state from events
   - Time-travel queries
   - Disaster recovery

5. Compliance
   - Regulator can audit any transaction
   - Provable history
   - No disputes about "who did what when"
"""


# ============================================
# EXAMPLE: Status Update with State Machine
# ============================================

from app.core.state_machine import transition_state, TransitionError

@router.patch("/{capacity_id}/verify", status_code=200)
async def verify_capacity(
    capacity_id: str,
    user_id: str = "regulator@eu.gov"
):
    """Verify capacity - uses state machine"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current status
    cursor.execute("SELECT status, correlation_id FROM capacities WHERE id = ?", 
                  (capacity_id,))
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(404, "Capacity not found")
    
    current_status = row['status']
    correlation_id = row['correlation_id']
    
    try:
        # Use state machine to transition
        # This will:
        # - Validate transition is allowed
        # - Check preconditions
        # - Emit status_changed event
        # - Execute postconditions
        event_id = transition_state(
            aggregate_type="capacity",
            aggregate_id=capacity_id,
            from_state=current_status,
            to_state="verified",
            data={
                "verified_by": user_id,
                "verification_date": datetime.now().isoformat()
            },
            user_id=user_id,
            correlation_id=correlation_id
        )
        
    except TransitionError as e:
        # Invalid transition attempted
        raise HTTPException(400, str(e))
    
    except PreconditionError as e:
        # Precondition not met (e.g., missing certificates)
        raise HTTPException(422, str(e))
    
    # Update projection
    cursor.execute("""
        UPDATE capacities 
        SET status = 'verified', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (capacity_id,))
    
    conn.commit()
    conn.close()
    
    return {
        "message": "Capacity verified",
        "event_id": event_id,
        "new_status": "verified"
    }


# ============================================
# EXAMPLE: Query Audit Trail
# ============================================

from app.core.event_store import get_entity_history

@router.get("/{capacity_id}/audit-trail")
async def get_capacity_audit_trail(capacity_id: str):
    """Get complete audit history for capacity"""
    
    events = get_entity_history("capacity", capacity_id)
    
    if not events:
        raise HTTPException(404, "Capacity not found")
    
    audit_trail = []
    for event in events:
        audit_trail.append({
            "timestamp": event['timestamp'],
            "event": event['event_type'],
            "user": event['metadata'].get('user_id'),
            "changes": event['data'],
            "event_hash": event['event_hash']  # Tamper-proof
        })
    
    return {
        "capacity_id": capacity_id,
        "total_events": len(events),
        "audit_trail": audit_trail
    }


# ============================================
# MIGRATION CHECKLIST
# ============================================

"""
For each existing endpoint, follow these steps:

1. Add correlation_id parameter to response model
2. Generate correlation_id on creation (or inherit from parent)
3. Emit event before database insert
4. Store correlation_id in database
5. Return correlation_id in response

For status updates:
1. Use transition_state() instead of direct UPDATE
2. Handle TransitionError and PreconditionError
3. Update projection after successful transition

Benefits:
- Complete audit trail
- Business rules enforced
- Chain of custody
- Compliance-ready
- No breaking changes to frontend (correlation_id is optional)
"""
