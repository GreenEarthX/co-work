"""
Who is told when a project's bankability changes, and what they are told.

JML, 2026-10-28: every premise or contract-term change re-evaluates the
project, and the result reaches the designated executives — pushed (an in-app
notification) or pulled (the report route). The re-evaluation itself is
`routes_bankability_proxy.reevaluate`; this module only routes its outcome.

Designated executives: `project_report_recipient` (alembic 076). With none
designated, the owner company's ACTIVE EXECUTIVE accounts receive the report.
A notification is written only when something moved — the state, or a gate's
determination; every re-evaluation is in the event ledger regardless.
"""
from __future__ import annotations

import json
from typing import Optional


def _rows(sql: str, params: tuple) -> list[dict]:
    from app.core.db_backend import domain_connection

    conn = domain_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def recipients(project_id: str) -> list[str]:
    """Designated executives, or the owner company's executives by default."""
    from app.core.project_registry import get_project_profile
    from app.core.projects_store import _rows as admin_rows

    designated = [r["user_id"] for r in _rows(
        "SELECT user_id FROM project_report_recipient WHERE project_id = ? ORDER BY user_id", (project_id,))]
    if designated:
        return designated
    profile = get_project_profile(project_id)
    if profile is None:
        return []
    # auth_users carries no RLS; the owner company comes from the registry.
    return [r["user_id"] for r in admin_rows(
        "SELECT user_id FROM auth_users WHERE company_id = :c AND business_function = 'EXECUTIVE' "
        "AND account_state = 'ACTIVE' ORDER BY user_id", {"c": profile.owner_company_id})]


def notify_changes(project_id: str, changes: dict, *, reason: str, actor: Optional[str],
                   snapshot: dict) -> int:
    """Push one notification per recipient when the state or a gate moved.
    Returns how many were written."""
    if changes.get("first_evaluation") or not (changes.get("state_changed") or changes.get("gates")):
        return 0
    from app.core.db_backend import domain_connection

    to = recipients(project_id)
    if not to:
        return 0
    conn = domain_connection()
    try:
        for user_id in to:
            conn.execute(
                "INSERT INTO bankability_notification (project_id, user_id, reason, from_state, to_state, "
                "gate_changes) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, user_id, reason, changes.get("from_state"), changes.get("to_state"),
                 json.dumps(changes.get("gates") or [])))
        conn.commit()
    finally:
        conn.close()
    return len(to)


def my_notifications(limit: int = 50) -> list[dict]:
    """The bound user's notifications, unread first (RLS: own rows only)."""
    rows = _rows("SELECT id, project_id, created_at, reason, from_state, to_state, gate_changes, read_at "
                 "FROM bankability_notification ORDER BY (read_at IS NULL) DESC, created_at DESC LIMIT ?",
                 (limit,))
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["read_at"] = str(r["read_at"]) if r["read_at"] else None
        if isinstance(r["gate_changes"], str):
            r["gate_changes"] = json.loads(r["gate_changes"])
    return rows


def mark_read(notification_id: int) -> bool:
    from app.core.db_backend import domain_connection

    conn = domain_connection()
    try:
        cur = conn.execute("UPDATE bankability_notification SET read_at = now() WHERE id = ? AND read_at IS NULL",
                           (notification_id,))
        conn.commit()
        return (getattr(cur, "rowcount", 0) or 0) > 0
    finally:
        conn.close()


def set_recipients(project_id: str, user_ids: list[str], designated_by: str) -> list[str]:
    """Replace the designated list. RLS lets only the owner company or GEX write."""
    from app.core.db_backend import domain_connection

    conn = domain_connection()
    try:
        conn.execute("DELETE FROM project_report_recipient WHERE project_id = ?", (project_id,))
        for uid in sorted(set(user_ids)):
            conn.execute("INSERT INTO project_report_recipient (project_id, user_id, designated_by) "
                         "VALUES (?, ?, ?)", (project_id, uid, designated_by))
        conn.commit()
    finally:
        conn.close()
    return recipients(project_id)
