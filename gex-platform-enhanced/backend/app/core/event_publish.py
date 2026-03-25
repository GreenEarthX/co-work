"""
GEX Event Bus — Safe Publish Helper
File: app/core/event_publish.py

Non-blocking, failure-safe event publishing.
Import this in any route module that needs to emit events.
Never raises exceptions — logs warnings on failure.

Usage:
    from app.core.event_publish import publish_event_safe
    from app.core.event_bus import EventType

    await publish_event_safe(
        EventType.GATE_SCORE_CHANGED,
        project_id="proj_bremen_h2",
        payload={"gate": "G4", "new_score": 78},
    )
"""

import logging
from typing import Optional

logger = logging.getLogger("gex.event_publish")


async def publish_event_safe(
    event_type,
    project_id: str,
    company_id: str = "",
    actor_user_id: str = "",
    payload: Optional[dict] = None,
) -> Optional[str]:
    """
    Safely publish an event to the event bus.
    Returns event_id if successful, None if bus unavailable.
    Never raises — the calling route handler always succeeds.
    """
    try:
        from app.core.event_bus import get_event_bus
        bus = get_event_bus()
        if not bus:
            return None
        return await bus.publish(
            event_type=event_type,
            project_id=project_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            payload=payload,
        )
    except Exception as e:
        logger.warning("Event publish failed (%s): %s", event_type, e)
        return None
