"""
Project Truth Registry
======================

Small project-aware truth layer used by guided UX endpoints.

This is not the final system of record. It is a transitional bridge that:
- replaces one-size-fits-all demo payloads with project-specific truth
- keeps task routing and deal-killer evaluation aligned
- can merge runtime evidence counts from bankability SQLite state when present

The long-term destination is a database-backed project truth service. For now,
this file removes the worst failure mode: every project returning the same flow.
"""

from __future__ import annotations

import copy
import os
import sqlite3
from pathlib import Path
from typing import Any
from app.core.config import settings



# The per-project inputs live in PostgreSQL (project_dataset kinds deal_inputs
# and task_router_inputs, alembic 069). PROJECT_TRUTH and DEFAULT_PROJECT_TRUTH
# — invented inputs, the default applied to every project without an entry —
# were removed on 2026-10-25. A project with no recorded inputs gets none: the
# deal-killer engine then treats every check as unmet (it fails closed), and the
# task router treats every step as not done.


def _load_runtime_evidence_stats(project_id: str) -> dict[str, Any]:
    from app.core.db_backend import evidence_connection, evidence_is_postgres

    conn = evidence_connection()
    try:
        # The table-existence probe is SQLite-specific (sqlite_master). On
        # PostgreSQL the table is guaranteed by migration 034, so skip it
        # rather than issue a query that would simply error.
        if not evidence_is_postgres() and not _table_exists(conn, "bankability_evidence"):
            return {}

        rows = conn.execute(
            "SELECT status FROM bankability_evidence WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        if not rows:
            return {}

        total = len(rows)
        audited = sum(1 for row in rows if row["status"] == "AUDITED")
        confirmed_plus = sum(1 for row in rows if row["status"] in {"AUDITED", "CONFIRMED"})

        return {
            "evidence_total_count": total,
            "evidence_audited_count": audited,
            "evidence_confirmed_pct": round((confirmed_plus / total) * 100, 1),
        }
    finally:
        conn.close()


def get_project_truth(project_id: str) -> dict[str, Any]:
    from app.core.projects_store import fetch_dataset, fetch_project

    row = fetch_project(project_id) or {}
    deal = fetch_dataset(project_id, "deal_inputs")
    tasks = fetch_dataset(project_id, "task_router_inputs")
    truth = {
        "project_name": row.get("project_name") or project_id,
        "molecule": row.get("molecule") or "",
        "deal_killers": copy.deepcopy(deal["payload"]) if deal else {},
        "task_router": copy.deepcopy(tasks["payload"]) if tasks else {},
        "inputs_recorded": bool(deal or tasks),
        "inputs_verification": (deal or tasks or {}).get("verification_state"),
    }
    runtime_stats = _load_runtime_evidence_stats(project_id)
    if runtime_stats:
        truth["task_router"].update(runtime_stats)
    return truth


def build_deal_killer_project_data(project_id: str) -> dict[str, Any]:
    return copy.deepcopy(get_project_truth(project_id)["deal_killers"])


def build_task_router_project_data(project_id: str) -> dict[str, Any]:
    return copy.deepcopy(get_project_truth(project_id)["task_router"])
