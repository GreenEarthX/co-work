"""
Approval Notifier — Matrix room notifications for WAE events.
Posts structured metadata (no content) to project approval rooms.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("gex.approval_notifier")

# Lazy import to avoid circular
def _get_matrix_service():
    try:
        from app.services import matrix_service
        return matrix_service
    except Exception:
        return None


def notify_approval_requested(
    project_id: str,
    request_id: str,
    action_type: str,
    initiator_user_id: str,
    required_roles: list[str],
) -> None:
    """Post to #project-{id}-approvals that a new approval is needed."""
    ms = _get_matrix_service()
    if not ms:
        return
    try:
        import asyncio
        asyncio.create_task(
            ms._matrix_post(
                f"/_matrix/client/v3/rooms/!gex-{project_id}-approvals:gex.internal/send/m.room.message/{request_id}",
                {
                    "msgtype": "m.notice",
                    "body": f"[WAE] Approval required: {action_type} — request_id={request_id}",
                    "gex_metadata": {
                        "event": "approval.requested",
                        "request_id": request_id,
                        "action_type": action_type,
                        "initiator": initiator_user_id,
                        "required_roles": required_roles,
                    },
                }
            )
        )
    except Exception as exc:
        logger.debug("notify_approval_requested: %s", exc)


def notify_approval_decided(
    project_id: str,
    request_id: str,
    decision: str,
    approver_user_id: str,
    new_status: str,
) -> None:
    """Post to approval room that a decision was made."""
    ms = _get_matrix_service()
    if not ms:
        return
    try:
        import asyncio
        asyncio.create_task(
            ms._matrix_post(
                f"/_matrix/client/v3/rooms/!gex-{project_id}-approvals:gex.internal/send/m.room.message/{request_id}-decision",
                {
                    "msgtype": "m.notice",
                    "body": f"[WAE] Decision: {decision} by {approver_user_id} — status now {new_status}",
                    "gex_metadata": {
                        "event": "approval.decided",
                        "request_id": request_id,
                        "decision": decision,
                        "approver": approver_user_id,
                        "new_status": new_status,
                    },
                }
            )
        )
    except Exception as exc:
        logger.debug("notify_approval_decided: %s", exc)
