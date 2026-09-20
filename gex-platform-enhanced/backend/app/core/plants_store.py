"""
Plants — the canvas's per-user portfolio, moved behind the backend.

WHY THIS EXISTS
---------------
`plants` was read and written straight from the browser through PostgREST
under the anon key in the shipped bundle. Measured 2026-09-19: 53 rows,
readable anonymously, including the whole `data` blob and `user_id`. The write
probe returned `PGRST204`, so writes were very probably permitted too.

Increment 2 of `docs/supabase-cutover-endpoints.md`.

OWNERSHIP IS DERIVED, NEVER SUPPLIED
------------------------------------
Every function here takes `owner_user_id` as its first argument and the route
layer fills it from the bearer token. The client cannot name an owner. That is
the whole point: today the browser passes `user_id` and PostgREST honours it,
so anyone can read or overwrite anyone's portfolio by naming their id — and
the ids in use are guessable strings like `admin-001` and `demo-user`, not
even uuids.

There is **no platform-admin bypass**. A GEX administrator reading a customer's
plant portfolio is a decision about who may see what, not a technicality, and
GEX's rule is that such access is granted explicitly. Nothing here grants it
implicitly. If support access is wanted later it needs its own entitlement and
its own audit trail.

THE WIPE THIS FIXES
-------------------
`savePlantsToCloud` deleted every row for the user and then inserted the new
set as two separate PostgREST calls. A failure between them left the user with
nothing. `replace_all` does both inside one transaction and refuses a call
whose deletion count the caller did not predict.

POSTGRES
--------
Refused. These rows are user-scoped and need RLS policies from an Alembic
migration, exactly as `ecosystem_store` argues for its own tables; creating
them unprotected here would undo the point of the move.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.core.ecosystem_store import PostgresMigrationRequired


class PlantNotFound(LookupError):
    """No such plant for this owner. The route turns it into a 404."""


class DeletionGuardTripped(ValueError):
    """A bulk replace would have removed a different number of plants than the
    caller said it expected. Refused rather than guessed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    # Path read per call so `isolated_store` can redirect it in tests.
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _plants_is_postgres() -> bool:
    return (os.getenv("PLANTS_DB_BACKEND") or "sqlite").strip().lower() == "postgres"


def init_db() -> None:
    if _plants_is_postgres():
        raise PostgresMigrationRequired(
            "user_plants is user-scoped and needs RLS policies from an Alembic "
            "migration; refusing to create it unprotected"
        )
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_plants (
                owner_user_id TEXT NOT NULL,
                slug          TEXT NOT NULL,
                data_json     TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                PRIMARY KEY (owner_user_id, slug)
            );
            CREATE INDEX IF NOT EXISTS idx_user_plants_owner
                ON user_plants (owner_user_id);
        """)
        conn.commit()
    finally:
        conn.close()


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "slug": r["slug"],
        "data": json.loads(r["data_json"]),
        "updated_at": r["updated_at"],
        "created_at": r["created_at"],
    }


def list_plants(owner_user_id: str) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT slug, data_json, created_at, updated_at FROM user_plants "
            "WHERE owner_user_id=? ORDER BY updated_at DESC",
            (owner_user_id,)).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def get_plant(owner_user_id: str, slug: str) -> dict[str, Any]:
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT slug, data_json, created_at, updated_at FROM user_plants "
            "WHERE owner_user_id=? AND slug=?", (owner_user_id, slug)).fetchone()
    finally:
        conn.close()
    if r is None:
        raise PlantNotFound(slug)
    return _row(r)


def upsert_plant(owner_user_id: str, slug: str,
                 data: dict[str, Any]) -> dict[str, Any]:
    """Write one plant. Touches only this row — an edit to one plant must not
    move another's `updated_at`, which consumers key off."""
    now = _now()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO user_plants (owner_user_id, slug, data_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(owner_user_id, slug) DO UPDATE SET "
            "data_json=excluded.data_json, updated_at=excluded.updated_at",
            (owner_user_id, slug, json.dumps(data), now, now))
        conn.commit()
    finally:
        conn.close()
    return get_plant(owner_user_id, slug)


def touch_plant(owner_user_id: str, slug: str) -> dict[str, Any]:
    now = _now()
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE user_plants SET updated_at=? WHERE owner_user_id=? AND slug=?",
            (now, owner_user_id, slug))
        conn.commit()
        if cur.rowcount == 0:
            raise PlantNotFound(slug)
    finally:
        conn.close()
    return get_plant(owner_user_id, slug)


def delete_plant(owner_user_id: str, slug: str) -> None:
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM user_plants WHERE owner_user_id=? AND slug=?",
            (owner_user_id, slug))
        conn.commit()
        if cur.rowcount == 0:
            raise PlantNotFound(slug)
    finally:
        conn.close()


def replace_all(owner_user_id: str, plants: list[dict[str, Any]], *,
                expect_deletions: Optional[int] = None) -> list[dict[str, Any]]:
    """
    Replace this owner's whole portfolio in ONE transaction.

    The browser did this as `delete(user_id)` then `insert(rows)`, two calls,
    no transaction: a failure in between wiped the portfolio (CLAUDE_HANDOFF
    §8.15). Here either both halves land or neither does.

    `expect_deletions` is the second guard. A half-initialised client sending
    an empty list would otherwise legitimately mean "delete everything". The
    caller must state how many plants it expects to remove; a mismatch raises
    rather than proceeding. Passing None accepts whatever the diff removes,
    which is only appropriate for a caller that just read the current state.
    """
    now = _now()
    incoming = {p["slug"]: p for p in plants}
    conn = _conn()
    try:
        existing = {r["slug"]: r["created_at"] for r in conn.execute(
            "SELECT slug, created_at FROM user_plants WHERE owner_user_id=?",
            (owner_user_id,)).fetchall()}
        removed = sorted(set(existing) - set(incoming))
        if expect_deletions is not None and len(removed) != expect_deletions:
            raise DeletionGuardTripped(
                f"would delete {len(removed)} plants ({', '.join(removed) or 'none'}), "
                f"caller expected {expect_deletions}")

        conn.execute("BEGIN")
        conn.execute("DELETE FROM user_plants WHERE owner_user_id=?", (owner_user_id,))
        for slug, payload in incoming.items():
            # A plant that already existed keeps its original created_at.
            conn.execute(
                "INSERT INTO user_plants (owner_user_id, slug, data_json, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (owner_user_id, slug, json.dumps(payload.get("data", payload)),
                 existing.get(slug, now), now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return list_plants(owner_user_id)


def count_for_owner(owner_user_id: str) -> int:
    conn = _conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM user_plants WHERE owner_user_id=?",
            (owner_user_id,)).fetchone()[0]
    finally:
        conn.close()
