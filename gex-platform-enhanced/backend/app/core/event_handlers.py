"""
GEX Event Handlers — Consumer-side processing for each event type.

Each consumer group has a dispatch function that routes events to the
appropriate handler. Handlers are async functions that perform the
actual work (recompute, notify, log).

These handlers are called by Celery workers or the async event loop.
"""

import logging
from typing import Optional

logger = logging.getLogger("gex.event_handlers")


# ── Handler Registry ──

class EventHandlers:
    """
    Dispatch table for event handlers.
    Each consumer group calls its own process() method.
    """

    def __init__(self, app_context: dict):
        """
        app_context should contain references to:
            - bankability_client: HTTP client to PF Engine
            - matrix_service: Matrix room management
            - event_store: Immutable audit log
            - redis: Redis client (for publishing follow-on events)
        """
        self._ctx = app_context

    # ── STRUCTURING ENGINE CONSUMER ──

    async def process_structuring(self, event) -> None:
        """
        Consumer group: structuring-engine
        Recomputes gap analysis + package when relevant events occur.
        """
        handlers = {
            "gate.score_changed": self._on_gate_score_changed,
            "gate.status_changed": self._on_gate_status_changed,
            "bankability.state_changed": self._on_bankability_state_changed,
            "offtake.loi_received": self._on_offtake_signal,
            "offtake.term_sheet_signed": self._on_offtake_signal,
            "offtake.contract_executed": self._on_offtake_signal,
            "offtake.terminated": self._on_offtake_terminated,
            "instrument.window_opening": self._on_instrument_window,
            "instrument.window_closing": self._on_instrument_window,
            "instrument.eligible": self._on_instrument_eligibility,
            "demand.signal_received": self._on_demand_signal,
            "demand.signal_upgraded": self._on_demand_signal,
            "risk.pricing_updated": self._on_risk_pricing_updated,
            "risk.political_changed": self._on_risk_political_changed,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)
        else:
            logger.debug("Structuring engine: no handler for %s", event.event_type)

    async def _on_gate_score_changed(self, event) -> None:
        project_id = event.project_id
        gate = event.payload.get("gate", "")
        old_score = event.payload.get("old_score", 0)
        new_score = event.payload.get("new_score", 0)
        logger.info("Gate %s score changed %d → %d for project %s",
                     gate, old_score, new_score, project_id)
        # TODO: Call structuring_engine.analyze_gaps(project_id)
        # TODO: If active package exists, recompute impact
        # TODO: Publish notification event

    async def _on_gate_status_changed(self, event) -> None:
        project_id = event.project_id
        gate = event.payload.get("gate", "")
        new_status = event.payload.get("new_status", "")
        logger.info("Gate %s → %s for project %s", gate, new_status, project_id)
        # TODO: Re-filter eligible instruments (some require gate pass)
        # TODO: Recompute bankability state transition

    async def _on_bankability_state_changed(self, event) -> None:
        project_id = event.project_id
        old_state = event.payload.get("old_state", "")
        new_state = event.payload.get("new_state", "")
        logger.info("Bankability state %s → %s for project %s",
                     old_state, new_state, project_id)
        # TODO: Trigger full re-evaluation of eligible instruments
        # TODO: Check if new state unlocks DFI/ECA applications
        # TODO: Publish to notification-engine

    async def _on_offtake_signal(self, event) -> None:
        project_id = event.project_id
        buyer = event.payload.get("buyer_name", "")
        volume_pct = event.payload.get("volume_pct", 0)
        logger.info("Offtake signal from %s (%s%%) for project %s",
                     buyer, volume_pct, project_id)
        # TODO: Recompute demand coverage metrics
        # TODO: Recompute DSCR with updated contracted revenue
        # TODO: Re-run gap analysis (offtake gap may close)

    async def _on_offtake_terminated(self, event) -> None:
        project_id = event.project_id
        logger.warning("Offtake terminated for project %s", project_id)
        # TODO: Recompute coverage — may reopen offtake gap
        # TODO: Re-run structuring recommendation
        # TODO: Urgent notification to analyst + CFO

    async def _on_instrument_window(self, event) -> None:
        project_id = event.project_id
        instrument_id = event.payload.get("instrument_id", "")
        window_event = event.event_type.split(".")[-1]
        logger.info("Instrument %s window %s for project %s",
                     instrument_id, window_event, project_id)
        # TODO: If window_opening: notify analyst with eligibility check
        # TODO: If window_closing: urgent notification with deadline

    async def _on_instrument_eligibility(self, event) -> None:
        project_id = event.project_id
        instrument_id = event.payload.get("instrument_id", "")
        logger.info("Instrument %s now eligible for project %s",
                     instrument_id, project_id)
        # TODO: Add to project's eligible instruments list
        # TODO: If instrument is in active package, recompute impact
        # TODO: Notify analyst

    async def _on_demand_signal(self, event) -> None:
        project_id = event.project_id
        buyer = event.payload.get("buyer_name", "")
        volume = event.payload.get("volume_tonnes_year", 0)
        logger.info("Demand signal from %s (%dt/yr) for project %s",
                     buyer, volume, project_id)
        # TODO: Add to demand pipeline
        # TODO: Recompute aggregation suggestions
        # TODO: Check if coverage threshold crossed

    async def _on_risk_pricing_updated(self, event) -> None:
        project_id = event.project_id
        component = event.payload.get("component_type", "")
        old_spread = event.payload.get("old_spread_bps", 0)
        new_spread = event.payload.get("new_spread_bps", 0)
        logger.info("Risk pricing updated: %s %dbps → %dbps",
                     component, old_spread, new_spread)
        # TODO: Recompute all CAPEX layer WACCs for affected projects
        # TODO: Re-run sensitivity with new base rates

    async def _on_risk_political_changed(self, event) -> None:
        jurisdiction = event.payload.get("jurisdiction", "")
        old_rating = event.payload.get("old_rating", "")
        new_rating = event.payload.get("new_rating", "")
        logger.info("Political risk changed: %s %s → %s",
                     jurisdiction, old_rating, new_rating)
        # TODO: Recompute PRI pricing for all projects in jurisdiction
        # TODO: Update risk allocation matrices
        # TODO: Notify all CISOs of affected companies

    # ── MATRIX SYNC CONSUMER ──

    async def process_matrix_sync(self, event) -> None:
        handlers = {
            "gate.status_changed": self._on_gate_for_matrix,
            "bankability.state_changed": self._on_state_for_matrix,
            "comms.room_created": self._on_room_created,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_gate_for_matrix(self, event) -> None:
        project_id = event.project_id
        gate = event.payload.get("gate", "")
        new_status = event.payload.get("new_status", "")
        logger.info("Matrix sync: gate %s → %s, checking room creation for %s",
                     gate, new_status, project_id)
        # TODO: Call matrix_service.check_room_creation(project_id, gate)
        # TODO: Call matrix_service.sync_room_membership(project_id)

    async def _on_state_for_matrix(self, event) -> None:
        project_id = event.project_id
        new_state = event.payload.get("new_state", "")
        if new_state == "OPERATIONAL":
            logger.info("Matrix sync: project %s OPERATIONAL — archiving pre-FID rooms",
                         project_id)
            # TODO: Call matrix_service.archive_pre_fid_rooms(project_id)

    async def _on_room_created(self, event) -> None:
        logger.info("Matrix room created: %s", event.payload.get("room_alias", ""))

    # ── NOTIFICATION ENGINE CONSUMER ──

    async def process_notifications(self, event) -> None:
        """Generate per-actor notifications from events."""
        project_id = event.project_id
        event_type = event.event_type

        # TODO: Look up all stakeholders on this project
        # TODO: For each stakeholder, check GATE_VISIBILITY (ABAC R2)
        # TODO: If event is relevant to their visible gates, create notification
        # TODO: Store in notifications table
        # TODO: Optionally push to Matrix room

        logger.info("Notification: %s for project %s", event_type, project_id)

    # ── TRUST SCORE CONSUMER ──

    async def process_trust_score(self, event) -> None:
        """Recompute Trust Score when evidence or gates change."""
        project_id = event.project_id
        logger.info("Trust score recompute triggered for project %s", project_id)
        # TODO: Call PF Engine /bankability/evaluate
        # TODO: Recompute Trust Score from gate scores + evidence completeness
        # TODO: Store updated score
        # TODO: If score crossed threshold, publish bankability.state_changed

    # ── CISO MONITOR CONSUMER ──

    async def process_ciso_monitor(self, event) -> None:
        """Log security-relevant events to CISO dashboard."""
        logger.info("CISO monitor: %s [%s] project=%s company=%s",
                     event.event_type, event.event_hash[:12],
                     event.project_id, event.company_id)
        # TODO: Write to ciso_event_log table
        # TODO: If anomaly (e.g., plant gateway offline), flag as alert

    # ── AUDIT TRAIL CONSUMER ──

    async def process_audit_trail(self, event) -> None:
        """Append every event to the immutable event store."""
        event_store = self._ctx.get("event_store")
        if event_store:
            try:
                await event_store.append(
                    event_type=event.event_type,
                    project_id=event.project_id,
                    company_id=event.company_id,
                    actor_user_id=event.actor_user_id,
                    payload=event.payload,
                    event_hash=event.event_hash,
                )
            except Exception as e:
                logger.error("Audit trail write failed: %s", e)
        else:
            logger.debug("Audit trail: event_store not available, skipping")


# ── Consumer Group → Handler Mapping ──

CONSUMER_HANDLER_MAP = {
    "structuring-engine": "process_structuring",
    "matrix-sync": "process_matrix_sync",
    "notification-engine": "process_notifications",
    "trust-score": "process_trust_score",
    "ciso-monitor": "process_ciso_monitor",
    "audit-trail": "process_audit_trail",
}
