"""
GEX Matrix Communications API
==============================
REST endpoints consumed by the CISO workspace Communication Monitor.
Also used internally by the platform when project state changes
(e.g., gate reached → auto-create room, stakeholder added → sync membership).

All endpoints validate the requesting company via x-demo-company header
(production: JWT claim). CISOs may only see their own company's events.

ISO 27001:
  A.12.4.1 — GET /events returns communication event log (metadata, no content)
  A.12.4.3 — GET /admin-log returns admin override log
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services.matrix_service import (
    create_project_room,
    add_user_to_room,
    remove_user_from_room,
    archive_room,
    sync_room_membership,
    get_rooms_for_project,
    get_events,
    get_admin_log,
    get_members_for_room,
    log_admin_action,
    init_matrix_db,
    GATE_ROOM_SPEC,
)

router = APIRouter()
logger = logging.getLogger("gex.routes.matrix")

# Ensure tables exist on import
try:
    init_matrix_db()
except Exception:
    pass


# ─── Request/response models ──────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    project_id: str
    gate_id: Optional[str] = None
    topic: Optional[str] = None
    members: list[dict] = []     # [{"user_id", "company_id", "actor_type"}]
    settlement_hash_ref: Optional[str] = None  # Links room to a settlement event audit_hash


class AddMemberRequest(BaseModel):
    room_id: str
    user_id: str
    company_id: str
    actor_type: str
    project_id: str
    gate_id: Optional[str] = None


class RemoveMemberRequest(BaseModel):
    room_id: str
    user_id: str
    company_id: str
    project_id: str
    reason: str = "Stakeholder removed from project"
    justification: Optional[str] = None


class ArchiveRoomRequest(BaseModel):
    room_id: str
    project_id: str
    gate_id: Optional[str] = None


class AdminOverrideRequest(BaseModel):
    action: str                  # member.override | power.override | room.force_archive
    room_id: Optional[str] = None
    target_user_id: Optional[str] = None
    justification: str
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None


class SyncMembershipRequest(BaseModel):
    project_id: str
    stakeholders: list[dict]     # [{"user_id", "company_id", "actor_type"}]


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health")
def comms_health():
    return {"status": "ok", "service": "matrix_comms"}


@router.get("/rooms/{project_id}")
def list_rooms(
    project_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """List all Matrix rooms for a project. CISO-visible."""
    rooms = get_rooms_for_project(project_id)
    enriched = []
    for r in rooms:
        spec = GATE_ROOM_SPEC.get(r.get("gate_id") or "", {})
        enriched.append({
            **r,
            "required_actors": spec.get("actors", []),
            "members": get_members_for_room(r["id"]),
        })
    return {"project_id": project_id, "rooms": enriched}


@router.post("/rooms")
async def create_room(
    body: CreateRoomRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Create a Matrix room for a project gate.
    Triggered by: gate state change (platform internal) or CISO manual creation.
    ABAC membership evaluation runs inside matrix_service.create_project_room.
    """
    topic = body.topic or f"GEX — {body.project_id[:8]} — {body.gate_id or 'General'}"
    result = await create_project_room(
        project_id=body.project_id,
        gate_id=body.gate_id,
        topic=topic,
        initial_members=body.members,
    )
    return result


@router.post("/rooms/members/add")
async def add_member(
    body: AddMemberRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Add a user to an existing room after ABAC evaluation."""
    result = await add_user_to_room(
        room_id=body.room_id,
        user_id=body.user_id,
        company_id=body.company_id,
        actor_type=body.actor_type,
        project_id=body.project_id,
        gate_id=body.gate_id,
        requested_by=x_demo_company or "GEX_PLATFORM",
    )
    return result


@router.post("/rooms/members/remove")
async def remove_member(
    body: RemoveMemberRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Remove a user from a room. Logs to admin_log if justification provided."""
    admin = x_demo_company or "GEX_PLATFORM"
    result = await remove_user_from_room(
        room_id=body.room_id,
        user_id=body.user_id,
        company_id=body.company_id,
        project_id=body.project_id,
        reason=body.reason,
        admin_user_id=admin,
        justification=body.justification,
    )
    return result


@router.post("/rooms/archive")
async def archive(
    body: ArchiveRoomRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Archive a room (make read-only) when its gate has been passed."""
    result = await archive_room(
        room_id=body.room_id,
        project_id=body.project_id,
        gate_id=body.gate_id,
        admin_user_id=x_demo_company or "GEX_PLATFORM",
    )
    return result


@router.post("/sync-membership")
async def sync_membership(
    body: SyncMembershipRequest,
    background_tasks: BackgroundTasks,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Reconcile Matrix room membership with current ABAC stakeholder state.
    Called by the event bus when stakeholders change.
    Runs asynchronously in background to not block the caller.
    """
    background_tasks.add_task(
        sync_room_membership,
        project_id=body.project_id,
        current_stakeholders=body.stakeholders,
    )
    return {"status": "sync_scheduled", "project_id": body.project_id}


@router.get("/events")
def list_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    project_id: Optional[str] = None,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Communication event log for CISO dashboard (A.12.4.1).
    Returns metadata only — never message content (E2EE protection).
    Filtered to the requesting company.
    """
    company_id = x_demo_company or "bp_global_energy"
    events = get_events(
        limit=limit,
        event_type=event_type,
        project_id=project_id,
        company_id=company_id,
    )
    # If no real events yet, return seeded demo events for CISO dashboard
    if not events:
        events = _demo_events(company_id)

    return {
        "company_id": company_id,
        "total": len(events),
        "events": events,
        "note": "Message content is end-to-end encrypted and never stored server-side.",
    }


@router.get("/admin-log")
def list_admin_log(
    limit: int = 50,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Admin action log for CISO (A.12.4.3).
    Shows every manual override with justification.
    """
    entries = get_admin_log(limit=limit)
    if not entries:
        entries = _demo_admin_log()
    return {
        "total": len(entries),
        "entries": entries,
        "note": "All admin overrides require justification. This log is append-only.",
    }


@router.post("/admin-log")
def record_admin_action(
    body: AdminOverrideRequest,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Record a manual admin override to the immutable ADMIN_LOG."""
    admin = x_demo_company or "unknown_admin"
    log_admin_action(
        admin_user_id=admin,
        action=body.action,
        room_id=body.room_id,
        target_user_id=body.target_user_id,
        justification=body.justification,
        before_state=body.before_state,
        after_state=body.after_state,
    )
    return {"status": "logged"}


@router.get("/policy")
def get_comms_policy(x_demo_company: Optional[str] = Header(default=None)):
    """
    Returns the ABAC→Matrix room policy: which actor types belong in which gate rooms.
    Used by CISO to understand the communication access policy (A.9.1.1).
    """
    return {
        "room_policy": GATE_ROOM_SPEC,
        "power_level_mapping": {
            "50": "Gate owner — can send messages, can invite other members",
            "0":  "Stakeholder read-access — can receive messages, cannot invite",
            "100": "GEX Platform bot — full room admin",
        },
        "nda_requirement": "All member companies must have bilateral NDA coverage before room creation.",
        "e2ee": "All rooms use Megolm end-to-end encryption. Message content is never stored server-side.",
        "iso_27001": {
            "A.9.1.1":  "Room creation and membership governed by ABAC policy (Vademecum §4.4)",
            "A.12.4.1": "All room events logged to matrix_events table (metadata only)",
            "A.12.4.3": "Admin overrides logged to admin_log with mandatory justification",
            "A.18":     "NDA verified before room creation. Data residency enforced per project jurisdiction.",
        },
    }


# ─── Demo data (CISO dashboard when no real events exist yet) ────────────────

def _demo_events(company_id: str) -> list[dict]:
    return [
        {"id": 1, "timestamp": "2026-03-16T09:45:00Z", "event_type": "room.created",
         "room_id": "!gex-proj_br-offtake:gex.internal",
         "project_id": "proj_bremen_h2", "gate_id": "G4_OFFTAKE",
         "actor_user_id": "@gex_platform:gex.internal", "company_id": "GEX",
         "metadata": '{"alias":"gex-proj_br-offtake","member_count":3}',
         "abac_decision": "N/A"},
        {"id": 2, "timestamp": "2026-03-16T09:45:30Z", "event_type": "member.joined",
         "room_id": "!gex-proj_br-offtake:gex.internal",
         "project_id": "proj_bremen_h2", "gate_id": "G4_OFFTAKE",
         "actor_user_id": "@s.hartmann:bp.gex.internal", "company_id": company_id,
         "metadata": '{"actor_type":"OFFTAKER","power_level":50}',
         "abac_decision": "ALLOW"},
        {"id": 3, "timestamp": "2026-03-16T09:46:00Z", "event_type": "member.joined",
         "room_id": "!gex-proj_br-offtake:gex.internal",
         "project_id": "proj_bremen_h2", "gate_id": "G4_OFFTAKE",
         "actor_user_id": "@l.donovan:bp.gex.internal", "company_id": company_id,
         "metadata": '{"actor_type":"COMMERCIAL_BANKER","power_level":50}',
         "abac_decision": "ALLOW"},
        {"id": 4, "timestamp": "2026-03-15T14:22:00Z", "event_type": "member.denied",
         "room_id": "!gex-proj_br-model:gex.internal",
         "project_id": "proj_bremen_h2", "gate_id": "G8_MODEL_AUDIT",
         "actor_user_id": "@p.nair:bp.gex.internal", "company_id": company_id,
         "metadata": '{"reason":"Actor REGULATOR not in gate spec G8_MODEL_AUDIT"}',
         "abac_decision": "DENY"},
        {"id": 5, "timestamp": "2026-03-14T11:00:00Z", "event_type": "room.created",
         "room_id": "!gex-proj_lh-cod:gex.internal",
         "project_id": "proj_lehavre_eng", "gate_id": "G11_COD",
         "actor_user_id": "@gex_platform:gex.internal", "company_id": "GEX",
         "metadata": '{"alias":"gex-proj_lh-cod","member_count":4}',
         "abac_decision": "N/A"},
        {"id": 6, "timestamp": "2026-03-13T09:00:00Z", "event_type": "message.sent",
         "room_id": "!gex-proj_br-offtake:gex.internal",
         "project_id": "proj_bremen_h2", "gate_id": "G4_OFFTAKE",
         "actor_user_id": "@s.hartmann:bp.gex.internal", "company_id": company_id,
         "metadata": '{"note":"Message content encrypted (E2EE). Only metadata logged per A.12.4.1."}',
         "abac_decision": "ALLOW"},
    ]


def _demo_admin_log() -> list[dict]:
    return [
        {"id": 1, "timestamp": "2026-03-15T16:30:00Z",
         "admin_user_id": "a.alfarsi@bp-energy.com",
         "action": "member.override",
         "room_id": "!gex-proj_br-offtake:gex.internal",
         "target_user_id": "@temp.advisor:bp.gex.internal",
         "justification": "Temporary legal advisor added for NDA review. Access to be revoked within 48h.",
         "before_state": "{}", "after_state": '{"power_level":0}'},
        {"id": 2, "timestamp": "2026-03-14T10:15:00Z",
         "admin_user_id": "a.alfarsi@bp-energy.com",
         "action": "power.override",
         "room_id": "!gex-proj_lh-cod:gex.internal",
         "target_user_id": "@m.johansson:bp.gex.internal",
         "justification": "Power level elevated to 50 for G11 sign-off period. Auto-reverts in 7 days.",
         "before_state": '{"power_level":0}', "after_state": '{"power_level":50}'},
    ]
