"""
Durable append-only event store for workflow and security events.

Redis Streams are useful for fan-out, but they are not the durable source of
truth for institutional auditability. This module provides a SQLite-backed,
hash-chained append-only event ledger.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

DB_PATH = os.getenv("GEX_PLATFORM_DB_PATH", "gex_platform.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_event_store() -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                stream TEXT NOT NULL,
                event_type TEXT NOT NULL,
                object_type TEXT,
                object_id TEXT,
                project_id TEXT,
                company_id TEXT,
                actor_user_id TEXT,
                previous_state TEXT,
                new_state TEXT,
                payload_json TEXT NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_project ON platform_events(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_stream ON platform_events(stream)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_object ON platform_events(object_type, object_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_created_at ON platform_events(created_at)")
        conn.commit()
    finally:
        conn.close()


def append_platform_event(
    *,
    stream: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
    company_id: str | None = None,
    actor_user_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    init_event_store()
    payload = payload or {}
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    event_id = str(uuid4())

    conn = _get_conn()
    try:
        last_row = conn.execute(
            "SELECT event_hash FROM platform_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = last_row["event_hash"] if last_row else None
        content = json.dumps(
            {
                "event_id": event_id,
                "stream": stream,
                "event_type": event_type,
                "object_type": object_type,
                "object_id": object_id,
                "project_id": project_id,
                "company_id": company_id,
                "actor_user_id": actor_user_id,
                "previous_state": previous_state,
                "new_state": new_state,
                "payload": payload,
                "created_at": created_at,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        event_hash = sha256(content.encode()).hexdigest()

        conn.execute(
            """
            INSERT INTO platform_events (
                event_id, stream, event_type, object_type, object_id, project_id,
                company_id, actor_user_id, previous_state, new_state, payload_json,
                previous_hash, event_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                stream,
                event_type,
                object_type,
                object_id,
                project_id,
                company_id,
                actor_user_id,
                previous_state,
                new_state,
                json.dumps(payload, sort_keys=True),
                previous_hash,
                event_hash,
                created_at,
            ),
        )
        conn.commit()
        return {
            "event_id": event_id,
            "event_hash": event_hash,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
    finally:
        conn.close()


def get_latest_workflow_event(object_type: str, object_id: str) -> sqlite3.Row | None:
    init_event_store()
    conn = _get_conn()
    try:
        return conn.execute(
            """
            SELECT *
            FROM platform_events
            WHERE stream = 'workflow'
              AND object_type = ?
              AND object_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (object_type, object_id),
        ).fetchone()
    finally:
        conn.close()


def list_latest_workflow_events_by_state(state: str) -> list[sqlite3.Row]:
    init_event_store()
    conn = _get_conn()
    try:
        return conn.execute(
            """
            SELECT e.*
            FROM platform_events e
            JOIN (
                SELECT object_type, object_id, MAX(id) AS max_id
                FROM platform_events
                WHERE stream = 'workflow'
                GROUP BY object_type, object_id
            ) latest
              ON e.id = latest.max_id
            WHERE e.stream = 'workflow'
              AND e.new_state = ?
            ORDER BY datetime(e.created_at) ASC
            """,
            (state,),
        ).fetchall()
    finally:
        conn.close()


def list_recent_project_events(project_id: str, limit: int = 50) -> list[sqlite3.Row]:
    init_event_store()
    conn = _get_conn()
    try:
        return conn.execute(
            """
            SELECT *
            FROM platform_events
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    finally:
        conn.close()


def append_workflow_transition(
    *,
    object_type: str,
    object_id: str,
    project_id: str | None,
    previous_state: str,
    new_state: str,
    actor_role: str,
    actor_user_id: str,
    payload: dict[str, Any] | None = None,
    company_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    transition_payload = {
        "actor_role": actor_role,
        **(payload or {}),
    }
    return append_platform_event(
        stream="workflow",
        event_type="workflow.state_advanced",
        project_id=project_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        object_type=object_type,
        object_id=object_id,
        previous_state=previous_state,
        new_state=new_state,
        payload=transition_payload,
        created_at=created_at,
    )


def log_access_decision(
    *,
    project_id: str | None,
    company_id: str,
    actor_user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return append_platform_event(
        stream="access",
        event_type="access.decision",
        project_id=project_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def seed_demo_workflow_events() -> None:
    init_event_store()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM platform_events WHERE stream = 'workflow'"
        ).fetchone()
        if row and row["count"] > 0:
            return
    finally:
        conn.close()

    seeds = [
        {
            "object_type": "BankabilitySnapshot",
            "object_id": "snap-le-havre-001",
            "project_id": "proj_lehavre_eng",
            "previous_state": "DRAFT",
            "new_state": "COMPUTED",
            "actor_role": "system",
            "actor_user_id": "system",
            "company_id": "greenearthx_admin",
            "created_at": "2026-03-27T06:00:00+00:00",
            "payload": {
                "project_name": "Le Havre e-NG",
                "submitted_by": "system",
            },
        },
        {
            "object_type": "SensitivityRun",
            "object_id": "sens-bremen-001",
            "project_id": "proj_bremen_h2",
            "previous_state": "DRAFT",
            "new_state": "COMPUTED",
            "actor_role": "system",
            "actor_user_id": "system",
            "company_id": "greenearthx_admin",
            "created_at": "2026-03-26T15:00:00+00:00",
            "payload": {
                "project_name": "Bremen Green Hydrogen Plant",
                "submitted_by": "system",
            },
        },
        {
            "object_type": "OfftakeAssessment",
            "object_id": "offtake-helios-001",
            "project_id": "proj_sansebastian_emethanol",
            "previous_state": "DRAFT",
            "new_state": "COMPUTED",
            "actor_role": "system",
            "actor_user_id": "system",
            "company_id": "greenearthx_admin",
            "created_at": "2026-03-26T02:00:00+00:00",
            "payload": {
                "project_name": "Project Helios e-Methanol",
                "submitted_by": "system",
            },
        },
        {
            "object_type": "CapitalStackScenario",
            "object_id": "capstack-le-havre-001",
            "project_id": "proj_lehavre_eng",
            "previous_state": "COMPUTED",
            "new_state": "REVIEWED",
            "actor_role": "analyst",
            "actor_user_id": "j.dupont@gex.io",
            "company_id": "greenearthx_admin",
            "created_at": "2026-03-27T03:00:00+00:00",
            "payload": {
                "project_name": "Le Havre e-NG",
                "submitted_by": "j.dupont@gex.io",
                "reviewer_user_id": "j.dupont@gex.io",
                "reviewer_name": "Jean Dupont",
                "reviewer_title": "Senior Analyst",
                "review_scope": "Capital stack readiness",
            },
        },
        {
            "object_type": "ICPack",
            "object_id": "icpack-le-havre-001",
            "project_id": "proj_lehavre_eng",
            "previous_state": "COMPUTED",
            "new_state": "REVIEWED",
            "actor_role": "analyst",
            "actor_user_id": "j.dupont@gex.io",
            "company_id": "greenearthx_admin",
            "created_at": "2026-03-26T21:00:00+00:00",
            "payload": {
                "project_name": "Le Havre e-NG",
                "submitted_by": "j.dupont@gex.io",
                "reviewer_user_id": "j.dupont@gex.io",
                "reviewer_name": "Jean Dupont",
                "reviewer_title": "Senior Analyst",
                "review_scope": "IC pack review",
            },
        },
    ]

    for seed in seeds:
        append_workflow_transition(**seed)


init_event_store()

