"""
Project Activity API
====================

Provides a project-scoped activity ledger for cross-functional handoffs.

This is a transitional trust layer:
- reads real signed commitments from CSS storage
- reads real bankability evidence and snapshot state from the platform DB
- adds project-truth-derived blocker events so the feed stays decision-first

It is not the final append-only event store, but it replaces the worst UX failure
mode where the frontend feed showed static seeded events unrelated to the project.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.css import get_commitments_for_project
from app.core.project_truth import get_project_truth

router = APIRouter(prefix="/project-activity", tags=["project-activity"])

DB_PATH = os.getenv("GEX_DB_PATH", "greenearth.db")
PROJECT_ID_ALIASES = {
    "proj_le_havre_eng": "proj_lehavre_eng",
    "proj_helios_emethanol": "proj_sansebastian_emethanol",
}


class ProjectActivityEventOut(BaseModel):
    id: str
    type: str
    status: str
    timestamp: str
    title: str
    actor: str
    actor_role: str
    target: str | None = None
    target_role: str | None = None
    project_id: str
    project_name: str
    details: str
    knowledge_loss_risk: str | None = None
    source: str


class ProjectActivityOut(BaseModel):
    project_id: str
    project_name: str
    total: int
    events: list[ProjectActivityEventOut]


def _normalize_project_id(project_id: str) -> str:
    return PROJECT_ID_ALIASES.get(project_id, project_id)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(
    *,
    event_id: str,
    event_type: str,
    status: str,
    timestamp: str,
    title: str,
    actor: str,
    actor_role: str,
    project_id: str,
    project_name: str,
    details: str,
    source: str,
    target: str | None = None,
    target_role: str | None = None,
    knowledge_loss_risk: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": event_type,
        "status": status,
        "timestamp": timestamp,
        "title": title,
        "actor": actor,
        "actor_role": actor_role,
        "target": target,
        "target_role": target_role,
        "project_id": project_id,
        "project_name": project_name,
        "details": details,
        "knowledge_loss_risk": knowledge_loss_risk,
        "source": source,
    }


def _load_commitment_events(project_id: str, project_name: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in get_commitments_for_project(project_id)[:5]:
        is_countersigned = row.get("status") == "COUNTERSIGNED"
        timestamp = (
            row.get("counterparty_timestamp")
            or row.get("initiator_timestamp")
            or row.get("created_at")
            or _now_iso()
        )
        details = (
            f"{row.get('action_type', 'Commitment')} recorded in the commitment ledger. "
            f"Status: {row.get('status', 'SIGNED_BY_INITIATOR')}."
        )
        if row.get("approvers"):
            details += f" Approval quorum snapshots attached: {len(row['approvers'])}."

        events.append(
            _event(
                event_id=f"commitment:{row.get('commitment_id')}",
                event_type="COMMITMENT_SIGNED",
                status="COMPLETED" if is_countersigned else "PENDING",
                timestamp=timestamp,
                title="Commitment countersigned" if is_countersigned else "Commitment signed",
                actor=row.get("initiator_user_id", "Unknown initiator"),
                actor_role=row.get("initiator_company_id", "Commitment initiator"),
                target=row.get("counterparty_user_id"),
                target_role=row.get("counterparty_company_id"),
                project_id=project_id,
                project_name=project_name,
                details=details,
                knowledge_loss_risk="LOW" if is_countersigned else "MEDIUM",
                source="commitment_signature",
            )
        )
    return events


def _load_evidence_event(project_id: str, project_name: str) -> list[dict[str, Any]]:
    if not Path(DB_PATH).exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "bankability_evidence"):
            return []

        rows = conn.execute(
            """
            SELECT evidence_key, status, submitted_by, verified_by, updated_at
            FROM bankability_evidence
            WHERE project_id = ?
            ORDER BY datetime(updated_at) DESC
            """,
            (project_id,),
        ).fetchall()
        if not rows:
            return []

        total = len(rows)
        confirmed_plus = sum(
            1 for row in rows if row["status"] in {"CONFIRMED", "AUDITED", "VERIFIED"}
        )
        latest = rows[0]
        pct = round((confirmed_plus / total) * 100)
        status = "COMPLETED" if pct >= 70 else "PENDING" if pct >= 40 else "BLOCKED"

        return [
            _event(
                event_id=f"evidence:{project_id}",
                event_type="EVIDENCE_UPDATE",
                status=status,
                timestamp=latest["updated_at"] or _now_iso(),
                title="Evidence ledger updated",
                actor=latest["verified_by"] or latest["submitted_by"] or "Project Team",
                actor_role="Evidence owner",
                project_id=project_id,
                project_name=project_name,
                details=(
                    f"{confirmed_plus}/{total} evidence items are CONFIRMED or above. "
                    f"Latest change: {latest['evidence_key']} -> {latest['status']}."
                ),
                knowledge_loss_risk="LOW" if pct >= 70 else "MEDIUM" if pct >= 40 else "HIGH",
                source="bankability_evidence",
            )
        ]
    finally:
        conn.close()


def _load_snapshot_event(project_id: str, project_name: str, truth: dict[str, Any]) -> list[dict[str, Any]]:
    if not Path(DB_PATH).exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "bankability_snapshots"):
            return []

        row = conn.execute(
            """
            SELECT current_state, evaluated_at
            FROM bankability_snapshots
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        if not row:
            return []

        confirmed_pct = truth.get("task_router", {}).get("evidence_confirmed_pct", 0)
        state = row["current_state"] or "UNKNOWN"
        status = "COMPLETED" if state in {"BUILDABLE", "BANKABLE", "OPERATING"} else "PENDING"

        return [
            _event(
                event_id=f"snapshot:{project_id}",
                event_type="WORKFLOW_ADVANCE",
                status=status,
                timestamp=row["evaluated_at"] or _now_iso(),
                title="Bankability snapshot refreshed",
                actor="GEX PF Engine",
                actor_role="Automated decision engine",
                project_id=project_id,
                project_name=project_name,
                details=(
                    f"Current state: {state}. "
                    f"Evidence at CONFIRMED or above: {confirmed_pct:.0f}%."
                ),
                knowledge_loss_risk="LOW",
                source="bankability_snapshot",
            )
        ]
    finally:
        conn.close()


def _load_truth_blocker_events(project_id: str, project_name: str, truth: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    task_router = truth.get("task_router", {})
    molecule = truth.get("molecule", "H2")
    timestamp = _now_iso()

    qualified_offers = int(task_router.get("qualified_offers_count", 0) or 0)
    pricing_reference_ready = bool(task_router.get("pricing_reference_ready", False))

    if qualified_offers > 0 and not pricing_reference_ready:
        events.append(
            _event(
                event_id=f"truth:{project_id}:pricing-reference",
                event_type="OFFTAKER_DECISION",
                status="BLOCKED",
                timestamp=timestamp,
                title="Reference price not yet defensible",
                actor="GEX Task Router",
                actor_role="Decision orchestrator",
                target="Commercial + Finance",
                target_role="Contract close owners",
                project_id=project_id,
                project_name=project_name,
                details=(
                    f"{qualified_offers} qualified offers are visible, but spot and forward reference pricing "
                    "is not yet ready. Contract close should pause until the price can be justified internally "
                    "and to external lenders."
                ),
                knowledge_loss_risk="HIGH",
                source="project_truth",
            )
        )

    if molecule == "NH3" and float(task_router.get("evidence_confirmed_pct", 0) or 0) < 70:
        events.append(
            _event(
                event_id=f"truth:{project_id}:nh3-hazard",
                event_type="HAZOP_EVENT",
                status="BLOCKED",
                timestamp=timestamp,
                title="NH3 hazard readiness still below lender threshold",
                actor="GEX Molecule Rules",
                actor_role="Molecule-specific gating",
                target="Engineering + Insurance",
                target_role="HAZOP / coverage owners",
                project_id=project_id,
                project_name=project_name,
                details=(
                    "Ammonia projects need signed HAZOP, Seveso, and terminal-interface readiness before "
                    "insurer and lender review can move cleanly."
                ),
                knowledge_loss_risk="HIGH",
                source="project_truth",
            )
        )

    return events


@router.get("/{project_id}", response_model=ProjectActivityOut)
async def list_project_activity(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=50),
) -> ProjectActivityOut:
    normalized_project_id = _normalize_project_id(project_id)
    truth = get_project_truth(normalized_project_id)
    project_name = truth.get("project_name", "Unknown Project")

    events = [
        *_load_truth_blocker_events(normalized_project_id, project_name, truth),
        *_load_snapshot_event(normalized_project_id, project_name, truth),
        *_load_evidence_event(normalized_project_id, project_name),
        *_load_commitment_events(normalized_project_id, project_name),
    ]

    events.sort(key=lambda item: _parse_timestamp(item["timestamp"]), reverse=True)
    trimmed = events[:limit]

    return ProjectActivityOut(
        project_id=normalized_project_id,
        project_name=project_name,
        total=len(trimmed),
        events=[ProjectActivityEventOut(**event) for event in trimmed],
    )
