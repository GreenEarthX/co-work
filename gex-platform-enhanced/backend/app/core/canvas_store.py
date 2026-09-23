"""
Canvas blobs — the plant canvas JSON, its version history, site infrastructure
and the per-user custom library.

WHY THIS EXISTS, AND WHY IT IS ALSO A REPAIR
--------------------------------------------
These documents lived in the Supabase Storage bucket `plant-data`, reached from
the browser under the anon key shipped in the bundle. Measured 2026-09-20:

  - The anon key **lists and reads** the whole bucket. Anyone holding the
    bundle — it is public JavaScript — can read every user's canvas.
  - The bucket is **not** public, correcting an earlier claim in the cutover
    document. `/storage/v1/object/public/plant-data/...` answers
    404 "Bucket not found".
  - Which means the frontend's own read path was broken. `useCanvasData` loads
    a canvas with `getPublicUrl()` and then fetches that URL with no key, so
    **every cloud canvas read has been failing** and silently falling through
    to localStorage. Saves worked; loads never did. A user changing device did
    not get their canvas back.

So this store closes an exposure and fixes a data-loss bug at the same time.

LAYOUT
------
Content on disk, metadata in the store — the pattern `development_packages`
already uses, which is the only file-write path this backend has.

    {CANVAS_BLOBS_DIR}/{owner}/{kind}/{slug}/{sha256[:16]}.json

Content-addressed, so a version identical to its predecessor costs nothing and
re-saving an unchanged canvas writes no new bytes. Because several rows can
point at one file, a delete only unlinks the file when the last row referring
to it has gone.

OWNERSHIP
---------
Every function takes `owner_user_id` first and the route fills it from the
bearer token. Nothing accepts an owner from the client. The old paths embedded
`users/{userId}/...` in a string the browser composed, so naming somebody
else's id read their canvas.

VERSIONS
--------
`version_id` is '' for the live document and a timestamp stamp for a snapshot,
so live and history share one table and one ownership rule. Retention keeps the
newest `MAX_VERSIONS_KEPT` snapshots per document, matching the frontend's
existing rule so the cutover changes no behaviour.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.core.db_backend import workspace_connection, workspace_is_postgres

# Anchored on the backend package root, not the working directory. A relative
# root would resolve against wherever uvicorn happened to be started, and the
# stored_path recorded in a row would stop finding its bytes the first time
# the service was launched from somewhere else — every canvas would read as
# "content missing" while the files sat safely on disk.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _blob_root() -> Path:
    configured = Path(os.getenv("GEX_CANVAS_BLOBS_DIR", CANVAS_BLOBS_DIR))
    return configured if configured.is_absolute() else (_BACKEND_ROOT / configured)


CANVAS_BLOBS_DIR = "data/canvas_blobs"

# Matches MAX_VERSIONS_KEPT in frontend/src/hooks/useCanvasData.ts.
MAX_VERSIONS_KEPT = 30

# A canvas measured 18 kB. The cap is generous but finite: an unbounded write
# path behind an authenticated endpoint is still a way to fill a disk.
MAX_BLOB_BYTES = 10 * 1024 * 1024

KINDS = ("canvas", "site", "library")

LIVE = ""  # the version_id of the current document


class BlobNotFound(LookupError):
    """No such document for this owner. The route turns it into a 404."""


class BlobTooLarge(ValueError):
    pass


class UnknownKind(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    """Follows WORKSPACE_DB_BACKEND. On PostgreSQL the connection carries the
    caller's `app.current_user_id`, which is the whole of 050's policy: the
    owner sees their own rows, everyone else — platform admin included — sees
    none."""
    return workspace_connection()


def _canvas_is_postgres() -> bool:
    # WORKSPACE_DB_BACKEND, declared in config.py. This used to read
    # CANVAS_DB_BACKEND straight from the environment, which `Settings`
    # never saw and nothing validated.
    return workspace_is_postgres()


def init_db() -> None:
    if _canvas_is_postgres():
        # Migration 050 owns canvas_blobs and its OWNER-ONLY policy
        # (no admin clause). Nothing to create here; a runtime
        # CREATE TABLE would produce it unprotected.
        return
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS canvas_blobs (
                owner_user_id TEXT NOT NULL,
                kind          TEXT NOT NULL,
                slug          TEXT NOT NULL,
                version_id    TEXT NOT NULL,
                sha256        TEXT NOT NULL,
                size_bytes    INTEGER NOT NULL,
                stored_path   TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                PRIMARY KEY (owner_user_id, kind, slug, version_id)
            );
            CREATE INDEX IF NOT EXISTS idx_canvas_blobs_owner
                ON canvas_blobs (owner_user_id, kind, slug);
        """)
        conn.commit()
    finally:
        conn.close()


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise UnknownKind(kind)


def _safe(part: str) -> str:
    """One path segment, with no way out of the directory. Slugs arrive from a
    URL, so `..`, separators and NULs must not survive into a filesystem path."""
    cleaned = "".join(c for c in part if c.isalnum() or c in "-_.")
    cleaned = cleaned.replace("..", "_")
    return cleaned or "_"


def _disk_path(owner: str, kind: str, slug: str, sha: str) -> Path:
    return (_blob_root() / _safe(owner) / _safe(kind)
            / _safe(slug or "_") / f"{sha[:16]}.json")


def put_blob(owner_user_id: str, kind: str, slug: str, content: bytes, *,
             version_id: str = LIVE) -> dict[str, Any]:
    """Write the live document, or one snapshot when `version_id` is given."""
    _check_kind(kind)
    if len(content) > MAX_BLOB_BYTES:
        raise BlobTooLarge(f"{len(content)} bytes exceeds {MAX_BLOB_BYTES}")

    sha = hashlib.sha256(content).hexdigest()
    dest = _disk_path(owner_user_id, kind, slug, sha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():                       # content-addressed: identical
        dest.write_bytes(content)               # content is written once
    now = _now()

    conn = _conn()
    try:
        prior = conn.execute(
            "SELECT stored_path, created_at FROM canvas_blobs WHERE owner_user_id=? "
            "AND kind=? AND slug=? AND version_id=?",
            (owner_user_id, kind, slug, version_id)).fetchone()
        conn.execute(
            "INSERT INTO canvas_blobs (owner_user_id, kind, slug, version_id, "
            "sha256, size_bytes, stored_path, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(owner_user_id, kind, slug, version_id) DO UPDATE SET "
            "sha256=excluded.sha256, size_bytes=excluded.size_bytes, "
            "stored_path=excluded.stored_path, updated_at=excluded.updated_at",
            (owner_user_id, kind, slug, version_id, sha, len(content), str(dest),
             prior["created_at"] if prior else now, now))
        conn.commit()
        if prior and prior["stored_path"] != str(dest):
            _unlink_if_unreferenced(conn, prior["stored_path"])
            conn.commit()
    finally:
        conn.close()

    return {"kind": kind, "slug": slug, "version_id": version_id, "sha256": sha,
            "size_bytes": len(content), "updated_at": now}


def get_blob(owner_user_id: str, kind: str, slug: str, *,
             version_id: str = LIVE) -> tuple[bytes, dict[str, Any]]:
    _check_kind(kind)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM canvas_blobs WHERE owner_user_id=? AND kind=? "
            "AND slug=? AND version_id=?",
            (owner_user_id, kind, slug, version_id)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise BlobNotFound(f"{kind}/{slug}")
    path = Path(row["stored_path"])
    if not path.exists():
        # The row outlived its bytes. Say so rather than serving an empty
        # document that a canvas would happily overwrite its own state with.
        raise BlobNotFound(f"{kind}/{slug} (metadata present, content missing)")
    return path.read_bytes(), {
        "kind": kind, "slug": slug, "version_id": version_id,
        "sha256": row["sha256"], "size_bytes": row["size_bytes"],
        "updated_at": row["updated_at"], "created_at": row["created_at"]}


def list_versions(owner_user_id: str, kind: str, slug: str) -> list[dict[str, Any]]:
    _check_kind(kind)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT version_id, sha256, size_bytes, created_at, updated_at "
            "FROM canvas_blobs WHERE owner_user_id=? AND kind=? AND slug=? "
            "AND version_id<>'' ORDER BY version_id DESC",
            (owner_user_id, kind, slug)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def prune_versions(owner_user_id: str, kind: str, slug: str, *,
                   keep: int = MAX_VERSIONS_KEPT) -> int:
    """Keep the newest `keep` snapshots. Mirrors the frontend's existing rule."""
    _check_kind(kind)
    conn = _conn()
    removed = 0
    try:
        stale = conn.execute(
            "SELECT version_id, stored_path FROM canvas_blobs WHERE owner_user_id=? "
            "AND kind=? AND slug=? AND version_id<>'' ORDER BY version_id DESC "
            "LIMIT -1 OFFSET ?", (owner_user_id, kind, slug, keep)).fetchall()
        for row in stale:
            conn.execute(
                "DELETE FROM canvas_blobs WHERE owner_user_id=? AND kind=? "
                "AND slug=? AND version_id=?",
                (owner_user_id, kind, slug, row["version_id"]))
            _unlink_if_unreferenced(conn, row["stored_path"])
            removed += 1
        conn.commit()
    finally:
        conn.close()
    return removed


def delete_document(owner_user_id: str, kind: str, slug: str) -> int:
    """Remove the live document and every snapshot of it."""
    _check_kind(kind)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT version_id, stored_path FROM canvas_blobs WHERE owner_user_id=? "
            "AND kind=? AND slug=?", (owner_user_id, kind, slug)).fetchall()
        if not rows:
            raise BlobNotFound(f"{kind}/{slug}")
        conn.execute(
            "DELETE FROM canvas_blobs WHERE owner_user_id=? AND kind=? AND slug=?",
            (owner_user_id, kind, slug))
        for row in rows:
            _unlink_if_unreferenced(conn, row["stored_path"])
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def _unlink_if_unreferenced(conn, stored_path: str) -> None:
    """Content is shared between identical versions, so the file goes only when
    the last row pointing at it has gone. Deleting eagerly would blank a
    snapshot that merely happened to match."""
    still = conn.execute(
        "SELECT 1 FROM canvas_blobs WHERE stored_path=? LIMIT 1",
        (stored_path,)).fetchone()
    if still:
        return
    try:
        Path(stored_path).unlink(missing_ok=True)
    except OSError:
        pass  # a file we cannot remove is not a reason to fail the request


def count_for_owner(owner_user_id: str, kind: Optional[str] = None) -> int:
    conn = _conn()
    try:
        if kind:
            return conn.execute(
                "SELECT COUNT(*) FROM canvas_blobs WHERE owner_user_id=? AND kind=?",
                (owner_user_id, kind)).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM canvas_blobs WHERE owner_user_id=?",
            (owner_user_id,)).fetchone()[0]
    finally:
        conn.close()
