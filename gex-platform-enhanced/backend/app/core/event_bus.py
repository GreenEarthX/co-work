"""
GEX Event Bus — Redis Streams Implementation
Task 2.12 from Vademecum roadmap (v3.0+)

One action → N faces updated asynchronously.

Architecture:
    Producer (any route/service) → Redis Stream → Consumer Group → Handler

Streams:
    gex:events:gate         Gate status changes
    gex:events:evidence     Evidence uploaded/verified/revoked
    gex:events:offtake      Offtake signed/amended/terminated
    gex:events:workflow      Workflow state transitions
    gex:events:instrument    De-risking instrument eligibility changes
    gex:events:demand        Demand signals received/updated
    gex:events:risk          Risk pricing or political risk updates
    gex:events:comms         Matrix room lifecycle events
    gex:events:plant         OT plant data ingested

Consumer Groups:
    structuring-engine      Recomputes gap analysis + package on relevant events
    matrix-sync             Syncs room membership on gate/stakeholder changes
    notification-engine     Generates per-actor notifications
    trust-score             Recomputes Trust Score on evidence/gate changes
    ciso-monitor            Logs security-relevant events to CISO dashboard
    audit-trail             Appends to immutable event store
"""

import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, asdict, field
from hashlib import sha256

logger = logging.getLogger("gex.event_bus")

# ── Event Types ──

class EventStream(str, Enum):
    GATE = "gex:events:gate"
    EVIDENCE = "gex:events:evidence"
    OFFTAKE = "gex:events:offtake"
    WORKFLOW = "gex:events:workflow"
    INSTRUMENT = "gex:events:instrument"
    DEMAND = "gex:events:demand"
    RISK = "gex:events:risk"
    COMMS = "gex:events:comms"
    PLANT = "gex:events:plant"
    PRICING = "gex:events:pricing"


class EventType(str, Enum):
    # Gate events
    GATE_SCORE_CHANGED = "gate.score_changed"
    GATE_STATUS_CHANGED = "gate.status_changed"
    GATE_EVIDENCE_ADDED = "gate.evidence_added"
    GATE_EVIDENCE_REVOKED = "gate.evidence_revoked"
    BANKABILITY_STATE_CHANGED = "bankability.state_changed"

    # Evidence events
    EVIDENCE_UPLOADED = "evidence.uploaded"
    EVIDENCE_VERIFIED = "evidence.verified"
    EVIDENCE_EXPIRED = "evidence.expired"
    EVIDENCE_REVOKED = "evidence.revoked"

    # Offtake events
    OFFTAKE_LOI_RECEIVED = "offtake.loi_received"
    OFFTAKE_TERM_SHEET_SIGNED = "offtake.term_sheet_signed"
    OFFTAKE_CONTRACT_EXECUTED = "offtake.contract_executed"
    OFFTAKE_AMENDED = "offtake.amended"
    OFFTAKE_TERMINATED = "offtake.terminated"

    # Workflow events
    WORKFLOW_STATE_ADVANCED = "workflow.state_advanced"
    WORKFLOW_REJECTED = "workflow.rejected"
    WORKFLOW_EXPORT_REQUESTED = "workflow.export_requested"
    WORKFLOW_SHARED_EXTERNAL = "workflow.shared_external"

    # Instrument events
    INSTRUMENT_WINDOW_OPENING = "instrument.window_opening"
    INSTRUMENT_WINDOW_CLOSING = "instrument.window_closing"
    INSTRUMENT_ELIGIBLE = "instrument.eligible"
    INSTRUMENT_INELIGIBLE = "instrument.ineligible"
    INSTRUMENT_APPLIED = "instrument.applied"
    INSTRUMENT_APPROVED = "instrument.approved"
    INSTRUMENT_REJECTED = "instrument.rejected"

    # Demand events
    DEMAND_SIGNAL_RECEIVED = "demand.signal_received"
    DEMAND_SIGNAL_UPGRADED = "demand.signal_upgraded"
    DEMAND_COVERAGE_THRESHOLD = "demand.coverage_threshold"

    # Risk events
    RISK_PRICING_UPDATED = "risk.pricing_updated"
    RISK_POLITICAL_CHANGED = "risk.political_changed"
    RISK_REGULATORY_CHANGED = "risk.regulatory_changed"

    # Comms events
    ROOM_CREATED = "comms.room_created"
    ROOM_MEMBER_ADDED = "comms.member_added"
    ROOM_MEMBER_REMOVED = "comms.member_removed"
    ROOM_ARCHIVED = "comms.room_archived"

    # Plant events
    PLANT_DATA_INGESTED = "plant.data_ingested"
    PLANT_GATEWAY_OFFLINE = "plant.gateway_offline"
    PLANT_ANOMALY_DETECTED = "plant.anomaly_detected"

    # Pricing lineage events
    PRICING_CALIBRATION_COMPLETED = "pricing.calibration_completed"
    PRICING_SUBSIDY_INCORPORATED = "pricing.subsidy_incorporated"
    PRICING_DFI_STRUCTURE_UPDATED = "pricing.dfi_structure_updated"
    PRICING_INSURANCE_PREMIUM_SET = "pricing.insurance_premium_set"
    PRICING_FORWARD_CURVE_GENERATED = "pricing.forward_curve_generated"
    PRICING_FLOOR_UPDATED = "pricing.floor_updated"
    PRICING_DECOMPOSITION_REQUESTED = "pricing.decomposition_requested"


# ── Stream Routing ──

EVENT_STREAM_MAP: dict[str, EventStream] = {
    "gate.": EventStream.GATE,
    "bankability.": EventStream.GATE,
    "evidence.": EventStream.EVIDENCE,
    "offtake.": EventStream.OFFTAKE,
    "workflow.": EventStream.WORKFLOW,
    "instrument.": EventStream.INSTRUMENT,
    "demand.": EventStream.DEMAND,
    "risk.": EventStream.RISK,
    "comms.": EventStream.COMMS,
    "plant.": EventStream.PLANT,
    "pricing.": EventStream.PRICING,
}


def _resolve_stream(event_type: str) -> EventStream:
    for prefix, stream in EVENT_STREAM_MAP.items():
        if event_type.startswith(prefix):
            return stream
    return EventStream.GATE  # fallback


# ── Event Envelope ──

@dataclass
class GexEvent:
    event_id: str = ""
    event_type: str = ""
    stream: str = ""
    timestamp: str = ""
    project_id: str = ""
    company_id: str = ""
    actor_user_id: str = ""
    payload: dict = field(default_factory=dict)
    event_hash: str = ""

    def compute_hash(self) -> str:
        content = json.dumps({
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "company_id": self.company_id,
            "actor_user_id": self.actor_user_id,
            "payload": self.payload,
        }, sort_keys=True)
        return sha256(content.encode()).hexdigest()

    def to_redis(self) -> dict[str, str]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "company_id": self.company_id,
            "actor_user_id": self.actor_user_id,
            "payload": json.dumps(self.payload),
            "event_hash": self.event_hash,
        }

    @classmethod
    def from_redis(cls, event_id: str, data: dict) -> "GexEvent":
        payload = data.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            event_id=event_id,
            event_type=data.get("event_type", ""),
            stream=data.get("stream", ""),
            timestamp=data.get("timestamp", ""),
            project_id=data.get("project_id", ""),
            company_id=data.get("company_id", ""),
            actor_user_id=data.get("actor_user_id", ""),
            payload=payload,
            event_hash=data.get("event_hash", ""),
        )


# ── Consumer Group Definitions ──

CONSUMER_GROUPS = {
    "structuring-engine": {
        "streams": [
            EventStream.GATE,
            EventStream.OFFTAKE,
            EventStream.INSTRUMENT,
            EventStream.DEMAND,
            EventStream.RISK,
        ],
        "description": "Recomputes gap analysis and package recommendations",
    },
    "matrix-sync": {
        "streams": [
            EventStream.GATE,
            EventStream.COMMS,
        ],
        "description": "Syncs Matrix room membership on gate/stakeholder changes",
    },
    "notification-engine": {
        "streams": [
            EventStream.GATE,
            EventStream.EVIDENCE,
            EventStream.OFFTAKE,
            EventStream.WORKFLOW,
            EventStream.INSTRUMENT,
            EventStream.DEMAND,
        ],
        "description": "Generates per-actor role-filtered notifications",
    },
    "trust-score": {
        "streams": [
            EventStream.GATE,
            EventStream.EVIDENCE,
        ],
        "description": "Recomputes Trust Score on evidence and gate changes",
    },
    "ciso-monitor": {
        "streams": [
            EventStream.COMMS,
            EventStream.PLANT,
            EventStream.WORKFLOW,
        ],
        "description": "Logs security-relevant events to CISO access monitor",
    },
    "audit-trail": {
        "streams": [s for s in EventStream],
        "description": "Appends every event to immutable event store",
    },
    "price-lineage": {
        "streams": [
            EventStream.PRICING,
            EventStream.OFFTAKE,
            EventStream.INSTRUMENT,
            EventStream.RISK,
        ],
        "description": "Tracks pricing lineage: Gabillon calibrations, subsidy changes, DFI updates",
    },
}


# ── Event Bus ──

class EventBus:
    """
    Redis Streams event bus for GEX platform.

    Usage:
        bus = EventBus(redis_client)
        await bus.initialize()  # creates streams + consumer groups

        # Publish
        await bus.publish(
            event_type=EventType.GATE_SCORE_CHANGED,
            project_id="proj_bremen_h2",
            company_id="comp_gex",
            actor_user_id="user_analyst_1",
            payload={"gate": "G4", "old_score": 65, "new_score": 78}
        )

        # Consume (in Celery worker or async loop)
        events = await bus.consume("structuring-engine", "worker-1", count=10)
        for event in events:
            await handle_event(event)
            await bus.acknowledge("structuring-engine", event)
    """

    def __init__(self, redis_client):
        self._redis = redis_client
        self._initialized = False

    async def initialize(self):
        """Create all streams and consumer groups. Idempotent."""
        for stream in EventStream:
            try:
                await self._redis.xadd(stream.value, {"_init": "1"}, maxlen=10000)
            except Exception:
                pass

        for group_name, config in CONSUMER_GROUPS.items():
            for stream_enum in config["streams"]:
                try:
                    await self._redis.xgroup_create(
                        stream_enum.value, group_name, id="0", mkstream=True
                    )
                except Exception:
                    pass  # group already exists

        self._initialized = True
        logger.info("Event bus initialized: %d streams, %d consumer groups",
                     len(EventStream), len(CONSUMER_GROUPS))

    async def publish(
        self,
        event_type: str | EventType,
        project_id: str,
        company_id: str = "",
        actor_user_id: str = "",
        payload: dict | None = None,
    ) -> str:
        """
        Publish an event to the appropriate Redis Stream.
        Returns the Redis event ID.
        """
        if isinstance(event_type, EventType):
            event_type = event_type.value

        stream = _resolve_stream(event_type)
        event = GexEvent(
            event_type=event_type,
            stream=stream.value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_id=project_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            payload=payload or {},
        )
        event.event_hash = event.compute_hash()

        event_id = await self._redis.xadd(
            stream.value,
            event.to_redis(),
            maxlen=50000,  # retain last 50k events per stream
        )

        logger.info("Published %s to %s [%s] project=%s",
                     event_type, stream.value, event_id, project_id)
        return event_id

    async def consume(
        self,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[GexEvent]:
        """
        Read pending events for a consumer group.
        Returns list of GexEvent objects.
        """
        config = CONSUMER_GROUPS.get(group)
        if not config:
            raise ValueError(f"Unknown consumer group: {group}")

        streams = {s.value: ">" for s in config["streams"]}
        results = await self._redis.xreadgroup(
            group, consumer, streams,
            count=count, block=block_ms,
        )

        events = []
        if results:
            for stream_name, messages in results:
                for msg_id, data in messages:
                    if isinstance(msg_id, bytes):
                        msg_id = msg_id.decode()
                    decoded = {}
                    for k, v in data.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        decoded[key] = val
                    if decoded.get("_init"):
                        continue
                    event = GexEvent.from_redis(msg_id, decoded)
                    event.stream = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                    events.append(event)

        return events

    async def acknowledge(self, group: str, event: GexEvent) -> None:
        """Mark event as processed by this consumer group."""
        await self._redis.xack(event.stream, group, event.event_id)

    async def get_stream_info(self, stream: str | EventStream) -> dict:
        """Get stream length and consumer group info."""
        if isinstance(stream, EventStream):
            stream = stream.value
        try:
            length = await self._redis.xlen(stream)
            groups = await self._redis.xinfo_groups(stream)
            return {"stream": stream, "length": length, "groups": groups}
        except Exception as e:
            return {"stream": stream, "error": str(e)}

    async def get_recent_events(
        self,
        stream: str | EventStream,
        count: int = 50,
    ) -> list[GexEvent]:
        """Read the most recent events from a stream (no consumer group)."""
        if isinstance(stream, EventStream):
            stream = stream.value
        results = await self._redis.xrevrange(stream, count=count)
        events = []
        for msg_id, data in results:
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()
            decoded = {}
            for k, v in data.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                decoded[key] = val
            if decoded.get("_init"):
                continue
            event = GexEvent.from_redis(msg_id, decoded)
            event.stream = stream
            events.append(event)
        return events

    async def health(self) -> dict:
        """Health check for the event bus."""
        try:
            await self._redis.ping()
            streams = {}
            for s in EventStream:
                try:
                    streams[s.value] = await self._redis.xlen(s.value)
                except Exception:
                    streams[s.value] = 0
            return {
                "status": "healthy",
                "redis": "connected",
                "streams": streams,
                "consumer_groups": list(CONSUMER_GROUPS.keys()),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# ── Singleton accessor ──

_bus_instance: Optional[EventBus] = None


def get_event_bus() -> Optional[EventBus]:
    return _bus_instance


def set_event_bus(bus: EventBus) -> None:
    global _bus_instance
    _bus_instance = bus
