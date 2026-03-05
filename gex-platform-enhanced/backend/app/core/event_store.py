"""
GreenEarthX Event Store
Immutable, cryptographically-chained event log for full audit trail
"""
import sqlite3
import json
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

# Database path
import os
DB_PATH = os.path.join(os.path.dirname(__file__), '../../gex_platform.db')


class EventStore:
    """
    Immutable event store with cryptographic chaining (blockchain-like)
    """
    
    @staticmethod
    @contextmanager
    def get_connection():
        """Get database connection"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    @staticmethod
    def initialize_schema():
        """Create event_store table if it doesn't exist"""
        with EventStore.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_store (
                    id TEXT PRIMARY KEY,
                    event_number INTEGER,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    causation_id TEXT,
                    correlation_id TEXT
                )
            """)
            
            # Indexes for fast queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_aggregate ON event_store(aggregate_type, aggregate_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON event_store(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_correlation ON event_store(correlation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON event_store(timestamp)")
            
            conn.commit()
    
    @staticmethod
    def _calculate_hash(event_data: Dict[str, Any]) -> str:
        """
        Calculate SHA-256 hash of event
        Includes: id, event_type, aggregate_id, data, previous_hash
        """
        hash_input = (
            str(event_data['id']) +
            event_data['event_type'] +
            event_data['aggregate_type'] +
            event_data['aggregate_id'] +
            event_data['data'] +
            str(event_data['previous_event_hash'])
        )
        
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    @staticmethod
    def _get_last_event() -> Optional[Dict]:
        """Get the most recent event for chain linking"""
        with EventStore.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT event_hash, event_number 
                FROM event_store 
                ORDER BY event_number DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                return {
                    'event_hash': row['event_hash'],
                    'event_number': row['event_number']
                }
            return None
    
    @staticmethod
    def append_event(
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Append event to immutable log with cryptographic chaining
        
        Args:
            event_type: Type of event (e.g., 'capacity.created')
            aggregate_type: Entity type (e.g., 'capacity')
            aggregate_id: Entity ID
            data: Event payload
            user_id: User who triggered event
            causation_id: Event that caused this event
            correlation_id: Business transaction ID
            metadata: Additional metadata
        
        Returns:
            event_id: UUID of created event
        """
        with EventStore.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get previous event for chaining
            last_event = EventStore._get_last_event()
            previous_hash = last_event['event_hash'] if last_event else "GENESIS"
            event_number = (last_event['event_number'] + 1) if last_event else 1
            
            # Generate event ID
            event_id = str(uuid.uuid4())
            
            # Build metadata
            event_metadata = {
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "ip_address": None,  # Would come from request context
            }
            if metadata:
                event_metadata.update(metadata)
            
            # Prepare event
            event = {
                "id": event_id,
                "event_number": event_number,
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "data": json.dumps(data, default=str),
                "metadata": json.dumps(event_metadata),
                "previous_event_hash": previous_hash,
                "causation_id": causation_id,
                "correlation_id": correlation_id or event_id,  # Default to event_id
            }
            
            # Calculate hash
            event["event_hash"] = EventStore._calculate_hash(event)
            
            # Append to event store (immutable)
            cursor.execute("""
                INSERT INTO event_store (
                    id, event_number, event_type, aggregate_type, aggregate_id,
                    data, metadata, previous_event_hash, event_hash,
                    causation_id, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["id"],
                event["event_number"],
                event["event_type"],
                event["aggregate_type"],
                event["aggregate_id"],
                event["data"],
                event["metadata"],
                event["previous_event_hash"],
                event["event_hash"],
                event["causation_id"],
                event["correlation_id"]
            ))
            
            conn.commit()
            
            print(f"✅ Event {event_number}: {event_type} for {aggregate_type}:{aggregate_id}")
            
            return event_id
    
    @staticmethod
    def get_events(
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Query events with filters
        """
        with EventStore.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM event_store WHERE 1=1"
            params = []
            
            if aggregate_type:
                query += " AND aggregate_type = ?"
                params.append(aggregate_type)
            
            if aggregate_id:
                query += " AND aggregate_id = ?"
                params.append(aggregate_id)
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            if correlation_id:
                query += " AND correlation_id = ?"
                params.append(correlation_id)
            
            query += " ORDER BY event_number ASC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            events = []
            for row in rows:
                events.append({
                    "id": row['id'],
                    "event_number": row['event_number'],
                    "event_type": row['event_type'],
                    "aggregate_type": row['aggregate_type'],
                    "aggregate_id": row['aggregate_id'],
                    "data": json.loads(row['data']),
                    "metadata": json.loads(row['metadata']),
                    "previous_event_hash": row['previous_event_hash'],
                    "event_hash": row['event_hash'],
                    "timestamp": row['timestamp'],
                    "causation_id": row['causation_id'],
                    "correlation_id": row['correlation_id'],
                })
            
            return events
    
    @staticmethod
    def verify_chain_integrity() -> bool:
        """
        Verify cryptographic chain integrity (detect tampering)
        Returns True if chain is valid, raises Exception if tampered
        """
        with EventStore.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM event_store ORDER BY event_number ASC")
            events = cursor.fetchall()
            
            if not events:
                return True  # Empty chain is valid
            
            previous_hash = None
            
            for event in events:
                # Recalculate hash
                event_dict = {
                    "id": event['id'],
                    "event_type": event['event_type'],
                    "aggregate_type": event['aggregate_type'],
                    "aggregate_id": event['aggregate_id'],
                    "data": event['data'],
                    "previous_event_hash": event['previous_event_hash'],
                }
                
                calculated_hash = EventStore._calculate_hash(event_dict)
                
                # Verify hash
                if calculated_hash != event['event_hash']:
                    raise Exception(f"❌ TAMPER DETECTED! Event {event['event_number']} hash mismatch")
                
                # Verify chain
                if previous_hash and event['previous_event_hash'] != previous_hash:
                    raise Exception(f"❌ CHAIN BROKEN! Event {event['event_number']} previous_hash mismatch")
                
                previous_hash = event['event_hash']
            
            print(f"✅ Chain integrity verified: {len(events)} events")
            return True
    
    @staticmethod
    def get_chain_of_custody(correlation_id: str) -> List[Dict]:
        """
        Get complete chain of custody for a business transaction
        Example: Track molecule from certification to delivery
        """
        events = EventStore.get_events(correlation_id=correlation_id)
        
        return [{
            "event_number": e['event_number'],
            "timestamp": e['timestamp'],
            "event_type": e['event_type'],
            "entity": f"{e['aggregate_type']}:{e['aggregate_id']}",
            "data": e['data'],
            "user": e['metadata'].get('user_id'),
        } for e in events]
    
    @staticmethod
    def rebuild_projection(aggregate_type: str, aggregate_id: str) -> Dict:
        """
        Rebuild current state from events (Event Sourcing)
        """
        events = EventStore.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id
        )
        
        # Start with empty state
        state = {
            "id": aggregate_id,
            "type": aggregate_type,
            "created_at": None,
            "updated_at": None,
            "status": None,
            "history": []
        }
        
        # Apply each event
        for event in events:
            if event['event_type'] == f"{aggregate_type}.created":
                state.update(event['data'])
                state['created_at'] = event['timestamp']
                state['status'] = 'created'
            
            elif event['event_type'] == f"{aggregate_type}.updated":
                state.update(event['data'])
                state['updated_at'] = event['timestamp']
            
            elif 'status_changed' in event['event_type']:
                state['status'] = event['data'].get('new_status')
                state['updated_at'] = event['timestamp']
            
            # Track history
            state['history'].append({
                "event": event['event_type'],
                "timestamp": event['timestamp'],
                "data": event['data']
            })
        
        return state


# Convenience functions
def log_event(event_type: str, aggregate_type: str, aggregate_id: str, 
              data: Dict, user_id: str = None, correlation_id: str = None) -> str:
    """Convenience function to log event"""
    return EventStore.append_event(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        data=data,
        user_id=user_id,
        correlation_id=correlation_id
    )


def get_entity_history(aggregate_type: str, aggregate_id: str) -> List[Dict]:
    """Get full event history for an entity"""
    return EventStore.get_events(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id
    )


def verify_integrity() -> bool:
    """Verify event chain integrity"""
    return EventStore.verify_chain_integrity()


def get_compliance_thread(correlation_id: str) -> List[Dict]:
    """Get compliance chain of custody"""
    return EventStore.get_chain_of_custody(correlation_id)


# Initialize on import
EventStore.initialize_schema()
