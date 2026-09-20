"""
Plant canvas documents — canvas JSON, version history, site infrastructure and
the per-user custom library.

Increment 3 of `docs/supabase-cutover-endpoints.md`. Replaces the Supabase
Storage bucket `plant-data`, which the browser reached under the anon key in
the shipped bundle.

WHAT THIS REPLACES, AND WHAT IT REPAIRS

The bucket is readable and listable with the anon key, so anyone holding the
public bundle could read every user's canvas. It is NOT public, though — which
means `useCanvasData`'s own read path, `getPublicUrl()` followed by an
unauthenticated fetch, has been answering 404 the whole time. Cloud saves
worked, cloud loads never did, and the canvas quietly fell back to
localStorage. This router closes the exposure and restores the read.

THE RULES

- The owner comes from the bearer token. No path, query or body names a user.
  The old scheme put `users/{userId}/` in a string the browser composed, so
  naming another id fetched their canvas.
- Somebody else's document is **404, not 403** — a 403 would confirm it exists.
- `GET /public-url` does not exist and will not. The six `getPublicUrl` call
  sites become authenticated reads that return the bytes; there is no
  unauthenticated URL to hand out, which is the property that was missing.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core import canvas_store
from app.core.canvas_store import (
    BlobNotFound, BlobTooLarge, UnknownKind,
)

router = APIRouter()

_JSON = "application/json"


def _owner(request: Request) -> str:
    payload = getattr(request.state, "auth_user_payload", None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required")
    owner = payload.get("user_id")
    if not owner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token carries no user identity")
    return owner


async def _body(request: Request) -> bytes:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Empty document")
    return content


def _read(owner: str, kind: str, slug: str, version_id: str = "") -> Response:
    try:
        content, meta = canvas_store.get_blob(owner, kind, slug,
                                              version_id=version_id)
    except BlobNotFound:
        raise HTTPException(status_code=404, detail=f"No {kind} document for {slug!r}")
    except UnknownKind:
        raise HTTPException(status_code=404, detail="Unknown document kind")
    return Response(content=content, media_type=_JSON, headers={
        "X-Content-Sha256": meta["sha256"],
        "X-Updated-At": meta["updated_at"],
        # These documents are per-user and change constantly; a cached copy
        # served to the wrong session is exactly what this cutover prevents.
        "Cache-Control": "no-store, private",
    })


def _write(owner: str, kind: str, slug: str, content: bytes,
           version_id: str = "") -> dict[str, Any]:
    try:
        return canvas_store.put_blob(owner, kind, slug, content,
                                     version_id=version_id)
    except BlobTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UnknownKind:
        raise HTTPException(status_code=404, detail="Unknown document kind")


# ── canvas ───────────────────────────────────────────────────────────────────

@router.get("/canvas/{slug}")
def get_canvas(slug: str, request: Request) -> Response:
    return _read(_owner(request), "canvas", slug)


@router.put("/canvas/{slug}")
async def put_canvas(slug: str, request: Request) -> dict[str, Any]:
    """Save the live canvas. The body is the canvas JSON, sent whole."""
    return _write(_owner(request), "canvas", slug, await _body(request))


@router.delete("/canvas/{slug}", status_code=204)
def delete_canvas(slug: str, request: Request) -> None:
    """Remove the canvas and every snapshot of it."""
    try:
        canvas_store.delete_document(_owner(request), "canvas", slug)
    except BlobNotFound:
        raise HTTPException(status_code=404, detail=f"No canvas for {slug!r}")


@router.get("/canvas/{slug}/versions")
def list_canvas_versions(slug: str, request: Request) -> list[dict[str, Any]]:
    """Snapshot history, newest first. Empty list rather than 404 — a canvas
    with no history is a normal state, not a missing resource."""
    return canvas_store.list_versions(_owner(request), "canvas", slug)


@router.put("/canvas/{slug}/versions/{version_id}")
async def put_canvas_version(slug: str, version_id: str,
                             request: Request) -> dict[str, Any]:
    """Record a snapshot, then prune to the retention limit."""
    owner = _owner(request)
    meta = _write(owner, "canvas", slug, await _body(request), version_id=version_id)
    meta["pruned"] = canvas_store.prune_versions(owner, "canvas", slug)
    return meta


@router.get("/canvas/{slug}/versions/{version_id}")
def get_canvas_version(slug: str, version_id: str, request: Request) -> Response:
    return _read(_owner(request), "canvas", slug, version_id)


# ── site infrastructure ──────────────────────────────────────────────────────

@router.get("/site/{slug}")
def get_site(slug: str, request: Request) -> Response:
    return _read(_owner(request), "site", slug)


@router.put("/site/{slug}")
async def put_site(slug: str, request: Request) -> dict[str, Any]:
    return _write(_owner(request), "site", slug, await _body(request))


# ── custom library (one per user, hence no slug) ─────────────────────────────

@router.get("/library")
def get_library(request: Request) -> Response:
    return _read(_owner(request), "library", "")


@router.put("/library")
async def put_library(request: Request) -> dict[str, Any]:
    return _write(_owner(request), "library", "", await _body(request))
