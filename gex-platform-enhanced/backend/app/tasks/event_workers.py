"""
GEX Event Bus — Celery Worker Tasks
Run with: celery -A app.tasks.event_workers worker -l info -Q events

Each task runs a consumer loop for one consumer group.
Celery Beat schedules periodic tasks (instrument window checks, stale detection).
"""

import asyncio
import logging
from celery import shared_task

logger = logging.getLogger("gex.event_workers")


def _get_redis_client():
    """Create an async Redis client for the event bus."""
    import redis.asyncio as aioredis
    return aioredis.from_url(
        "redis://redis:6379/0",
        decode_responses=False,  # event_bus handles decoding
    )


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _consume_loop(group_name: str, consumer_name: str, max_events: int = 100):
    """
    Consume up to max_events from a consumer group, process each, acknowledge.
    Called by Celery tasks on a schedule.
    """
    from app.core.event_bus import EventBus, CONSUMER_GROUPS
    from app.core.event_handlers import EventHandlers, CONSUMER_HANDLER_MAP

    redis_client = _get_redis_client()
    bus = EventBus(redis_client)
    await bus.initialize()

    handlers = EventHandlers(app_context={
        "redis": redis_client,
    })

    handler_method = getattr(handlers, CONSUMER_HANDLER_MAP[group_name], None)
    if not handler_method:
        logger.error("No handler method for group %s", group_name)
        return 0

    processed = 0
    try:
        events = await bus.consume(group_name, consumer_name, count=max_events, block_ms=2000)
        for event in events:
            try:
                await handler_method(event)
                await bus.acknowledge(group_name, event)
                processed += 1
            except Exception as e:
                logger.error("Handler error for %s in %s: %s",
                             event.event_type, group_name, e)
    except Exception as e:
        logger.error("Consume error for group %s: %s", group_name, e)
    finally:
        await redis_client.aclose()

    return processed


# ── Celery Tasks — one per consumer group ──

@shared_task(name="events.process_structuring", queue="events")
def process_structuring_events():
    """Process events for the structuring engine consumer group."""
    count = _run_async(_consume_loop("structuring-engine", "celery-structuring"))
    return {"group": "structuring-engine", "processed": count}


@shared_task(name="events.process_matrix_sync", queue="events")
def process_matrix_sync_events():
    """Process events for Matrix room synchronization."""
    count = _run_async(_consume_loop("matrix-sync", "celery-matrix"))
    return {"group": "matrix-sync", "processed": count}


@shared_task(name="events.process_notifications", queue="events")
def process_notification_events():
    """Process events for the notification engine."""
    count = _run_async(_consume_loop("notification-engine", "celery-notifications"))
    return {"group": "notification-engine", "processed": count}


@shared_task(name="events.process_trust_score", queue="events")
def process_trust_score_events():
    """Process events for Trust Score recomputation."""
    count = _run_async(_consume_loop("trust-score", "celery-trust"))
    return {"group": "trust-score", "processed": count}


@shared_task(name="events.process_ciso_monitor", queue="events")
def process_ciso_monitor_events():
    """Process events for CISO security monitoring."""
    count = _run_async(_consume_loop("ciso-monitor", "celery-ciso"))
    return {"group": "ciso-monitor", "processed": count}


@shared_task(name="events.process_audit_trail", queue="events")
def process_audit_trail_events():
    """Process events for the immutable audit trail."""
    count = _run_async(_consume_loop("audit-trail", "celery-audit"))
    return {"group": "audit-trail", "processed": count}


# ── Celery Beat Periodic Tasks ──

@shared_task(name="events.check_instrument_windows", queue="events")
def check_instrument_windows():
    """
    Periodic: check for instrument application windows opening/closing.
    Run daily via Celery Beat.
    Publishes instrument.window_opening / instrument.window_closing events.
    """
    logger.info("Checking instrument application windows...")
    # TODO: Query instrument_registry for windows opening in next 14 days
    # TODO: Query for windows closing in next 14 days
    # TODO: For each, check which projects are eligible
    # TODO: Publish instrument.window_opening / instrument.window_closing events
    return {"checked": True}


@shared_task(name="events.detect_stale_artefacts", queue="events")
def detect_stale_artefacts():
    """
    Periodic: detect workflow artefacts older than 7 days since computation.
    Run daily via Celery Beat.
    """
    logger.info("Detecting stale bankability artefacts...")
    # TODO: Query workflow_states for COMPUTED artefacts where computed_at > 7 days
    # TODO: Mark as stale in workflow state
    # TODO: Publish workflow.stale event for notification engine
    return {"checked": True}


# ── Celery Beat Schedule (add to celery_beat_schedule in config) ──

BEAT_SCHEDULE = {
    "process-structuring-events": {
        "task": "events.process_structuring",
        "schedule": 10.0,  # every 10 seconds
    },
    "process-matrix-sync-events": {
        "task": "events.process_matrix_sync",
        "schedule": 10.0,
    },
    "process-notification-events": {
        "task": "events.process_notifications",
        "schedule": 10.0,
    },
    "process-trust-score-events": {
        "task": "events.process_trust_score",
        "schedule": 15.0,  # slightly less frequent
    },
    "process-ciso-monitor-events": {
        "task": "events.process_ciso_monitor",
        "schedule": 10.0,
    },
    "process-audit-trail-events": {
        "task": "events.process_audit_trail",
        "schedule": 5.0,  # most frequent — every event must be logged
    },
    "check-instrument-windows": {
        "task": "events.check_instrument_windows",
        "schedule": 86400.0,  # daily
    },
    "detect-stale-artefacts": {
        "task": "events.detect_stale_artefacts",
        "schedule": 86400.0,  # daily
    },
}
