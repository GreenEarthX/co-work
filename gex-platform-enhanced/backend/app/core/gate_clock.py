"""
The gate clock (rules 4.8.0; migration 080): when each gate was first seen satisfied.

`record` is called by `reevaluate` after every evaluation. It writes a row only for a gate that is
SATISFIED and has none yet (first wins, never rewritten), and it never raises: a measurement must not
be able to fail an evaluation. A gate WAIVED by the financing model is not "satisfied" and is not recorded.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def record(conn, project_id: str, gate_evaluations: list[dict], rules_version: str | None, state: str | None) -> int:
    """Insert the first-satisfied row for each newly satisfied gate. Returns how many were new."""
    new = 0
    for g in gate_evaluations or []:
        if g.get("determination") != "SATISFIED":
            continue
        cur = conn.execute(
            "INSERT INTO project_gate_clock (project_id, gate_id, first_satisfied_at, rules_version, state_at_time) "
            "VALUES (?, ?, datetime('now'), ?, ?) ON CONFLICT(project_id, gate_id) DO NOTHING",
            (project_id, g["gate_id"], rules_version, state))
        new += getattr(cur, "rowcount", 0) or 0
    return new


def read(conn, project_id: str) -> list[dict]:
    rows = conn.execute("SELECT gate_id, first_satisfied_at, rules_version, state_at_time FROM project_gate_clock "
                        "WHERE project_id = ? ORDER BY first_satisfied_at, gate_id", (project_id,)).fetchall()
    return [{"gate_id": r["gate_id"], "first_satisfied_at": str(r["first_satisfied_at"]),
             "rules_version": r["rules_version"], "state_at_time": r["state_at_time"]} for r in rows]
