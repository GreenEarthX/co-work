"""
Refresh token persistence with token-family rotation.

Each refresh token belongs to a family (one per login). On reuse of a revoked
token, the entire family is revoked (all active sessions from that login).
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH


def _get_conn():
    """Same store as app.core.auth — refresh tokens are part of the auth slice
    and must follow it across backends (core/db_backend.py)."""
    from app.core.db_backend import auth_connection

    return auth_connection(DB_PATH)


def ensure_refresh_token_table() -> None:
    # On Postgres the schema is owned by alembic revision 030 (branch
    # "auth_slice"); this SQLite DDL must not run there. One owner per schema.
    from app.core.db_backend import is_postgres

    if is_postgres():
        return
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_id    TEXT PRIMARY KEY,
                family_id   TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                token_hash  TEXT NOT NULL UNIQUE,
                expires_at  TEXT NOT NULL,
                used_at     TEXT,
                revoked     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rt_user ON refresh_tokens(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rt_family ON refresh_tokens(family_id)")
        conn.commit()
    finally:
        conn.close()


def _hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(user_id: str, family_id: str | None = None, expire_days: int = 7) -> tuple[str, str]:
    """Create and persist a new refresh token. Returns (raw_token, family_id)."""
    ensure_refresh_token_table()
    raw = secrets.token_urlsafe(48)
    token_id = secrets.token_hex(16)
    fid = family_id or secrets.token_hex(16)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expire_days)).isoformat()

    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO refresh_tokens (token_id, family_id, user_id, token_hash, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_id, fid, user_id, _hash_token(raw), expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return raw, fid


def rotate_refresh_token(raw_token: str, expire_days: int = 7) -> tuple[str, str, str] | None:
    """
    Validate and rotate a refresh token.

    Returns (new_raw_token, new_family_id, user_id) on success.
    Returns None if the token is invalid/expired.
    If the token was already used (replay attack), revokes the whole family and returns None.
    """
    ensure_refresh_token_table()
    token_hash = _hash_token(raw_token)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()

        if not row:
            return None

        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if row["revoked"] or now > expires_at:
            return None

        if row["used_at"]:
            # Replay — revoke entire family
            conn.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE family_id = ?",
                (row["family_id"],),
            )
            conn.commit()
            return None

        # Mark current token as used
        conn.execute(
            "UPDATE refresh_tokens SET used_at = ? WHERE token_id = ?",
            (now.isoformat(), row["token_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    # Issue successor in same family
    new_raw, fid = issue_refresh_token(row["user_id"], family_id=row["family_id"], expire_days=expire_days)
    return new_raw, fid, row["user_id"]


def revoke_all_for_user(user_id: str) -> None:
    """Revoke all active refresh tokens for a user (called on logout)."""
    ensure_refresh_token_table()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()
