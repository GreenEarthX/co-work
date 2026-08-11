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
from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH


def _get_conn() -> sqlite3.Connection:
    """
    Slice-6b-2 connection — SQLite or PostgreSQL by configuration
    (EVENTSTORE_DB_BACKEND).
    """
    from app.core.db_backend import PLATFORM_ADMIN, eventstore_connection

    # Explicit admin: the audit ledger must be able to record an event for any
    # project, including one the acting tenant cannot read.
    return eventstore_connection(company_id=PLATFORM_ADMIN)


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _row_json(row: sqlite3.Row, key: str, fallback: Any) -> Any:
    value = row[key]
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


# Arbitrary but FIXED application-wide key for the append lock. Any other
# advisory-lock user must not reuse it.
_APPEND_LOCK_KEY = 8_143_552_901


def _is_postgres() -> bool:
    from app.core.db_backend import eventstore_is_postgres

    return eventstore_is_postgres()


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(platform_events)")}


def _ensure_platform_event_schema(conn: sqlite3.Connection) -> None:
    """
    Additive SQLite migrations for the ledger.

    SQLite only — on PostgreSQL the schema is owned by alembic (migration 039),
    which also declares the RLS policy and the unique constraint that makes a
    forked chain impossible. Running PRAGMA/ALTER from here would bypass both.
    """
    from app.core.db_backend import eventstore_is_postgres

    if eventstore_is_postgres():
        return
    columns = _table_columns(conn)
    if "correlation_id" not in columns:
        conn.execute("ALTER TABLE platform_events ADD COLUMN correlation_id TEXT")
    if "causation_id" not in columns:
        conn.execute("ALTER TABLE platform_events ADD COLUMN causation_id TEXT")
    if "metadata_json" not in columns:
        conn.execute("ALTER TABLE platform_events ADD COLUMN metadata_json TEXT")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_project ON platform_events(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_stream ON platform_events(stream)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_object ON platform_events(object_type, object_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_created_at ON platform_events(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_correlation ON platform_events(correlation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_events_event_type ON platform_events(event_type)")


def init_event_store() -> None:
    """
    Create the SQLite event ledger.

    SQLite ONLY. On PostgreSQL the schema is owned by alembic (migration 039),
    which also declares the RLS policy and the UNIQUE constraint on
    previous_hash that makes a forked chain impossible. This DDL is SQLite
    dialect (AUTOINCREMENT) and errors outright on PostgreSQL.
    """
    from app.core.db_backend import eventstore_is_postgres

    if eventstore_is_postgres():
        return
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
                correlation_id TEXT,
                causation_id TEXT,
                previous_state TEXT,
                new_state TEXT,
                payload_json TEXT NOT NULL,
                metadata_json TEXT,
                previous_hash TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_platform_event_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _event_hash_input(
    *,
    event_id: str,
    stream: str,
    event_type: str,
    object_type: str | None,
    object_id: str | None,
    project_id: str | None,
    company_id: str | None,
    actor_user_id: str | None,
    correlation_id: str | None,
    causation_id: str | None,
    previous_state: str | None,
    new_state: str | None,
    payload: dict[str, Any],
    metadata: dict[str, Any],
    created_at: str,
    previous_hash: str | None,
) -> str:
    content = _json_dump(
        {
            "event_id": event_id,
            "stream": stream,
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "project_id": project_id,
            "company_id": company_id,
            "actor_user_id": actor_user_id,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "payload": payload,
            "metadata": metadata,
            "created_at": created_at,
            "previous_hash": previous_hash,
        }
    )
    return sha256(content.encode()).hexdigest()


def _append_event_row(
    *,
    stream: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
    company_id: str | None = None,
    actor_user_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    init_event_store()
    payload = payload or {}
    metadata = dict(metadata or {})
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    event_id = str(uuid4())

    project_id = project_id or payload.get("project_id")
    company_id = company_id or payload.get("company_id")
    previous_state = previous_state or payload.get("old_status") or payload.get("previous_state")
    new_state = new_state or payload.get("new_status") or payload.get("status")

    if actor_user_id and "user_id" not in metadata:
        metadata["user_id"] = actor_user_id
    if causation_id and "causation_id" not in metadata:
        metadata["causation_id"] = causation_id

    conn = _get_conn()
    try:
        _ensure_platform_event_schema(conn)

        # ── Serialise appenders ─────────────────────────────────────────────
        # The chain is GLOBAL and this is a read-then-write: read the last
        # event_hash, then INSERT it as previous_hash. Without a lock, two
        # concurrent appends read the same predecessor and FORK the chain.
        #
        # SQLite hides this by serialising writers. PostgreSQL does not —
        # measured on 12 concurrent appends BEFORE this lock existed: 3 were
        # rejected by the unique constraint (i.e. events LOST) and 1 fork still
        # got through at the NULL root, because SQL UNIQUE permits many NULLs.
        # A rejected audit event is as unacceptable as a forked one.
        #
        # A transaction-scoped advisory lock serialises only event appends and
        # releases automatically on commit or rollback. The unique constraint
        # and the partial root index stay as backstops — this is the mechanism
        # that makes them never fire.
        if _is_postgres():
            conn.execute("SELECT pg_advisory_xact_lock(%s)" % _APPEND_LOCK_KEY)

        last_row = conn.execute(
            "SELECT event_hash FROM platform_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = last_row["event_hash"] if last_row else None
        event_hash = _event_hash_input(
            event_id=event_id,
            stream=stream,
            event_type=event_type,
            object_type=object_type,
            object_id=object_id,
            project_id=project_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            previous_state=previous_state,
            new_state=new_state,
            payload=payload,
            metadata=metadata,
            created_at=created_at,
            previous_hash=previous_hash,
        )

        conn.execute(
            """
            INSERT INTO platform_events (
                event_id, stream, event_type, object_type, object_id, project_id,
                company_id, actor_user_id, correlation_id, causation_id,
                previous_state, new_state, payload_json, metadata_json,
                previous_hash, event_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                correlation_id,
                causation_id,
                previous_state,
                new_state,
                _json_dump(payload),
                _json_dump(metadata),
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
    correlation_id: str | None = None,
    causation_id: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _append_event_row(
        stream=stream,
        event_type=event_type,
        payload=payload,
        project_id=project_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        object_type=object_type,
        object_id=object_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        previous_state=previous_state,
        new_state=new_state,
        metadata=metadata,
        created_at=created_at,
    )


def append_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    data: dict[str, Any] | None = None,
    user_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    project_id: str | None = None,
    company_id: str | None = None,
    stream: str | None = None,
    created_at: str | None = None,
) -> str:
    result = _append_event_row(
        stream=stream or aggregate_type,
        event_type=event_type,
        payload=data,
        project_id=project_id,
        company_id=company_id,
        actor_user_id=user_id,
        object_type=aggregate_type,
        object_id=aggregate_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=metadata,
        created_at=created_at,
    )
    return result["event_id"]


def _format_event_row(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _row_json(row, "metadata_json", {})
    if row["actor_user_id"] and "user_id" not in metadata:
        metadata["user_id"] = row["actor_user_id"]
    if row["causation_id"] and "causation_id" not in metadata:
        metadata["causation_id"] = row["causation_id"]

    entity = None
    if row["object_type"] and row["object_id"]:
        entity = f"{row['object_type']}:{row['object_id']}"
    elif row["object_type"]:
        entity = row["object_type"]

    return {
        "id": row["event_id"],
        "event_number": row["id"],
        "stream": row["stream"],
        "event_type": row["event_type"],
        "aggregate_type": row["object_type"],
        "aggregate_id": row["object_id"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "project_id": row["project_id"],
        "company_id": row["company_id"],
        "data": _row_json(row, "payload_json", {}),
        "metadata": metadata,
        "timestamp": row["created_at"],
        "created_at": row["created_at"],
        "correlation_id": row["correlation_id"],
        "causation_id": row["causation_id"],
        "previous_state": row["previous_state"],
        "new_state": row["new_state"],
        "previous_hash": row["previous_hash"],
        "event_hash": row["event_hash"],
        "entity": entity,
    }


def get_events(
    *,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    event_type: str | None = None,
    correlation_id: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    init_event_store()
    conn = _get_conn()
    try:
        clauses: list[str] = []
        params: list[Any] = []

        if aggregate_type:
            clauses.append("object_type = ?")
            params.append(aggregate_type)
        if aggregate_id:
            clauses.append("object_id = ?")
            params.append(aggregate_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if correlation_id:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)

        query = "SELECT * FROM platform_events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        if limit is not None:
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            rows = list(reversed(rows))
        else:
            query += " ORDER BY id ASC"
            rows = conn.execute(query, params).fetchall()

        return [_format_event_row(row) for row in rows]
    finally:
        conn.close()


def get_entity_history(aggregate_type: str, aggregate_id: str) -> list[dict[str, Any]]:
    return get_events(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        limit=None,
    )


def get_compliance_thread(correlation_id: str) -> list[dict[str, Any]]:
    return get_events(correlation_id=correlation_id, limit=None)


def verify_integrity() -> None:
    init_event_store()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM platform_events ORDER BY id ASC").fetchall()
        previous_hash: str | None = None

        for row in rows:
            payload = _row_json(row, "payload_json", {})
            metadata = _row_json(row, "metadata_json", {})
            if row["actor_user_id"] and "user_id" not in metadata:
                metadata["user_id"] = row["actor_user_id"]
            if row["causation_id"] and "causation_id" not in metadata:
                metadata["causation_id"] = row["causation_id"]

            expected_hash = _event_hash_input(
                event_id=row["event_id"],
                stream=row["stream"],
                event_type=row["event_type"],
                object_type=row["object_type"],
                object_id=row["object_id"],
                project_id=row["project_id"],
                company_id=row["company_id"],
                actor_user_id=row["actor_user_id"],
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
                previous_state=row["previous_state"],
                new_state=row["new_state"],
                payload=payload,
                metadata=metadata,
                created_at=row["created_at"],
                previous_hash=previous_hash,
            )

            if row["previous_hash"] != previous_hash:
                raise ValueError(
                    f"Invalid previous hash linkage at event {row['event_id']}"
                )
            if row["event_hash"] != expected_hash:
                raise ValueError(f"Invalid event hash at event {row['event_id']}")

            previous_hash = row["event_hash"]
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
    correlation_id: str | None = None,
    causation_id: str | None = None,
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
        correlation_id=correlation_id,
        causation_id=causation_id,
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
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return append_platform_event(
        stream="access",
        event_type="access.decision",
        project_id=project_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        metadata=metadata,
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
