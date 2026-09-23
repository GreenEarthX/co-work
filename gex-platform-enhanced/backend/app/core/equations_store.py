"""
Equipment equations — per-user, per-plant, per-node equation configurations.

WHY THIS EXISTS
---------------
`equipment_equations` was read and written from the browser under the anon key
in the shipped bundle. Increment 4 of `docs/supabase-cutover-endpoints.md`.

THE DEFECT THIS CLOSES (CLAUDE_HANDOFF §8.16)

`useEquipmentEquations.remove` was:

    supabase.from("equipment_equations").delete().eq("id", id)

No user scoping at all. Every other query in that hook filtered on `user_id`;
the delete did not. Under the anon key with RLS off, that removes any row by
id, for anyone. Only two rows exist today, which is the only reason it is
small rather than serious.

Here the owner is the first argument of every function and the route fills it
from the bearer token, so a delete that names another person's row matches
nothing. The route turns that into **404, not 403** — a 403 would confirm the
id exists.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.db_backend import workspace_connection, workspace_is_postgres


class EquationNotFound(LookupError):
    """No such row for this owner."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    """Follows WORKSPACE_DB_BACKEND. On PostgreSQL the connection carries the
    caller's `app.current_user_id`, which is the whole of 050's policy: the
    owner sees their own rows, everyone else — platform admin included — sees
    none."""
    return workspace_connection()


def _equations_is_postgres() -> bool:
    # WORKSPACE_DB_BACKEND, declared in config.py. This used to read
    # EQUATIONS_DB_BACKEND straight from the environment, which `Settings`
    # never saw and nothing validated.
    return workspace_is_postgres()


def init_db() -> None:
    if _equations_is_postgres():
        # Migration 050 owns equipment_equations and its OWNER-ONLY policy
        # (no admin clause). Nothing to create here; a runtime
        # CREATE TABLE would produce it unprotected.
        return
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS equipment_equations (
                row_id              TEXT PRIMARY KEY,
                owner_user_id       TEXT NOT NULL,
                plant_slug          TEXT NOT NULL,
                equipment_node_id   TEXT NOT NULL,
                equipment_label     TEXT NOT NULL DEFAULT '',
                equation_id         TEXT NOT NULL,
                equation_expression TEXT NOT NULL,
                output_param        TEXT NOT NULL,
                variable_bindings   TEXT NOT NULL DEFAULT '{}',
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL,
                UNIQUE (owner_user_id, plant_slug, equipment_node_id, equation_id)
            );
            CREATE INDEX IF NOT EXISTS idx_equipment_equations_scope
                ON equipment_equations (owner_user_id, plant_slug, equipment_node_id);
        """)
        conn.commit()
    finally:
        conn.close()


def _row(r) -> dict[str, Any]:
    """The shape `StoredEquipmentEquation` expects, unchanged by the move."""
    return {
        "id": r["row_id"],
        "equation_id": r["equation_id"],
        "equation_expression": r["equation_expression"],
        "output_param": r["output_param"],
        "variable_bindings": json.loads(r["variable_bindings"] or "{}"),
    }


def list_equations(owner_user_id: str, plant_slug: str,
                   equipment_node_id: str) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM equipment_equations WHERE owner_user_id=? AND "
            "plant_slug=? AND equipment_node_id=? ORDER BY created_at",
            (owner_user_id, plant_slug, equipment_node_id)).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def upsert_equation(owner_user_id: str, *, plant_slug: str,
                    equipment_node_id: str, equipment_label: str,
                    equation_id: str, equation_expression: str,
                    output_param: str,
                    variable_bindings: dict[str, Any],
                    row_id: str | None = None) -> dict[str, Any]:
    """
    Upsert on (owner, plant, node, equation) — the same conflict target the
    browser used, so re-saving an equation updates it rather than duplicating.
    """
    now = _now()
    conn = _conn()
    try:
        existing = conn.execute(
            "SELECT row_id FROM equipment_equations WHERE owner_user_id=? AND "
            "plant_slug=? AND equipment_node_id=? AND equation_id=?",
            (owner_user_id, plant_slug, equipment_node_id, equation_id)).fetchone()
        rid = existing["row_id"] if existing else (row_id or str(uuid.uuid4()))
        conn.execute(
            "INSERT INTO equipment_equations (row_id, owner_user_id, plant_slug, "
            "equipment_node_id, equipment_label, equation_id, equation_expression, "
            "output_param, variable_bindings, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(owner_user_id, plant_slug, equipment_node_id, equation_id) "
            "DO UPDATE SET equipment_label=excluded.equipment_label, "
            "equation_expression=excluded.equation_expression, "
            "output_param=excluded.output_param, "
            "variable_bindings=excluded.variable_bindings, "
            "updated_at=excluded.updated_at",
            (rid, owner_user_id, plant_slug, equipment_node_id, equipment_label,
             equation_id, equation_expression, output_param,
             json.dumps(variable_bindings or {}), now, now))
        conn.commit()
        written = conn.execute(
            "SELECT * FROM equipment_equations WHERE row_id=?", (rid,)).fetchone()
    finally:
        conn.close()
    return _row(written)


def delete_equation(owner_user_id: str, row_id: str) -> None:
    """
    Delete one row **belonging to this owner**. The unscoped version of this
    query is the defect the module docstring describes; the owner predicate is
    not optional and must not be removed "because the id is already unique".
    """
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM equipment_equations WHERE row_id=? AND owner_user_id=?",
            (row_id, owner_user_id))
        conn.commit()
        if cur.rowcount == 0:
            raise EquationNotFound(row_id)
    finally:
        conn.close()


def count_for_owner(owner_user_id: str) -> int:
    conn = _conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM equipment_equations WHERE owner_user_id=?",
            (owner_user_id,)).fetchone()[0]
    finally:
        conn.close()
