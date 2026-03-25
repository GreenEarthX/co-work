"""
GEX Event Bus — API Routes
Prefix: /api/v1/events

Provides:
    - Event bus health check
    - Stream monitoring (CISO/admin)
    - Manual event publishing (for testing and integration)
    - Recent events per project
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/api/v1/events", tags=["events"])


# ── Schemas ──

class PublishEventRequest(BaseModel):
    event_type: str = Field(..., description="e.g. gate.score_changed")
    project_id: str
    company_id: str = ""
    actor_user_id: str = ""
    payload: dict = Field(default_factory=dict)


class EventResponse(BaseModel):
    event_id: str
    event_type: str
    stream: str
    timestamp: str
    project_id: str
    company_id: str
    actor_user_id: str
    payload: dict
    event_hash: str


# ── Endpoints ──

@router.get("/health")
async def event_bus_health():
    """Health check for the event bus and all streams."""
    try:
        from app.core.event_bus import get_event_bus
        bus = get_event_bus()
        if not bus:
            return {"status": "unavailable", "reason": "Event bus not initialized"}
        return await bus.health()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/publish", response_model=dict)
async def publish_event(req: PublishEventRequest):
    """
    Publish an event to the event bus.
    Used by route handlers and services to emit events.
    Also available for manual testing.
    """
    from app.core.event_bus import get_event_bus
    bus = get_event_bus()
    if not bus:
        raise HTTPException(503, "Event bus not initialized")

    event_id = await bus.publish(
        event_type=req.event_type,
        project_id=req.project_id,
        company_id=req.company_id,
        actor_user_id=req.actor_user_id,
        payload=req.payload,
    )
    return {"event_id": event_id, "stream": req.event_type}


@router.get("/recent/{project_id}", response_model=list[EventResponse])
async def get_recent_events(
    project_id: str,
    stream: Optional[str] = Query(None, description="Filter by stream name"),
    count: int = Query(50, ge=1, le=200),
):
    """
    Get recent events for a project.
    Optionally filter by stream.
    Used by CISO monitor and analyst dashboards.
    """
    from app.core.event_bus import get_event_bus, EventStream
    bus = get_event_bus()
    if not bus:
        raise HTTPException(503, "Event bus not initialized")

    if stream:
        try:
            target_stream = EventStream(stream)
        except ValueError:
            raise HTTPException(400, f"Unknown stream: {stream}")
        events = await bus.get_recent_events(target_stream, count=count)
    else:
        events = []
        for s in EventStream:
            batch = await bus.get_recent_events(s, count=count)
            events.extend(batch)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        events = events[:count]

    return [
        EventResponse(
            event_id=e.event_id,
            event_type=e.event_type,
            stream=e.stream,
            timestamp=e.timestamp,
            project_id=e.project_id,
            company_id=e.company_id,
            actor_user_id=e.actor_user_id,
            payload=e.payload,
            event_hash=e.event_hash,
        )
        for e in events
        if e.project_id == project_id or not project_id
    ]


@router.get("/streams", response_model=dict)
async def get_stream_stats():
    """
    Get statistics for all event streams.
    CISO/admin only in production (ABAC-gated).
    """
    from app.core.event_bus import get_event_bus, EventStream
    bus = get_event_bus()
    if not bus:
        raise HTTPException(503, "Event bus not initialized")

    stats = {}
    for s in EventStream:
        info = await bus.get_stream_info(s)
        stats[s.value] = info
    return {"streams": stats}


@router.get("/consumer-groups", response_model=dict)
async def get_consumer_groups():
    """List all consumer groups and their stream subscriptions."""
    from app.core.event_bus import CONSUMER_GROUPS
    return {"groups": {
        name: {
            "streams": [s.value for s in config["streams"]],
            "description": config["description"],
        }
        for name, config in CONSUMER_GROUPS.items()
    }}
