"""
Plants — the canvas portfolio, read and written through the backend.

Increment 2 of `docs/supabase-cutover-endpoints.md`. Replaces the
`supabase.from("plants")` calls in `PlantBuilder.tsx`, `plantStore.ts`,
`iterations.ts` and `useCanvasData.ts`.

THE RULE: THE CALLER CANNOT NAME AN OWNER

Every route derives the owner from the bearer token and passes it to the
store. No route accepts a `user_id` in a path, query or body. Today the
browser supplies one and PostgREST trusts it, so naming another id reads
another person's portfolio — and the ids in the live table are `admin-001`,
`demo-user`, `user-003`, not even uuids. After this, that is not expressible.

There is no platform-admin bypass here. GEX decides explicitly who may see
whose work; an implicit "admins see everything" is not that decision, so it is
not written. Support access, if wanted, needs its own entitlement and audit
trail.

A plant belonging to somebody else is **404, not 403**. A 403 would confirm
that the slug exists and who has one — the same reasoning that governs the
economics snapshot route.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core import plants_store
from app.core.plants_store import DeletionGuardTripped, PlantNotFound

router = APIRouter()


class PlantBody(BaseModel):
    """The canvas record. Opaque to the backend — it is the frontend's
    `ProjectRecord`, stored whole, exactly as the Supabase `data` column did."""
    data: dict[str, Any] = Field(default_factory=dict)


class PortfolioBody(BaseModel):
    plants: list[dict[str, Any]] = Field(default_factory=list)


def _owner(request: Request) -> str:
    payload = getattr(request.state, "auth_user_payload", None)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    owner = payload.get("user_id")
    if not owner:
        # A token with no subject must not fall back to a shared bucket.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token carries no user identity",
        )
    return owner


@router.get("")
def list_plants(request: Request) -> list[dict[str, Any]]:
    """The caller's own portfolio. There is no way to ask for another's."""
    return plants_store.list_plants(_owner(request))


@router.get("/{slug}")
def get_plant(slug: str, request: Request) -> dict[str, Any]:
    try:
        return plants_store.get_plant(_owner(request), slug)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail=f"No plant {slug!r}")


@router.put("/{slug}")
def upsert_plant(slug: str, request: Request,
                 body: PlantBody = Body(...)) -> dict[str, Any]:
    """Create or update one plant. Only this row's `updated_at` moves."""
    return plants_store.upsert_plant(_owner(request), slug, body.data)


@router.post("/{slug}/touch")
def touch_plant(slug: str, request: Request) -> dict[str, Any]:
    """Bump `updated_at` without rewriting the record."""
    try:
        return plants_store.touch_plant(_owner(request), slug)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail=f"No plant {slug!r}")


@router.delete("/{slug}", status_code=204)
def delete_plant(slug: str, request: Request) -> None:
    try:
        plants_store.delete_plant(_owner(request), slug)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail=f"No plant {slug!r}")


@router.put("")
def replace_portfolio(
    request: Request,
    body: PortfolioBody = Body(...),
    confirm_delete: Optional[int] = Query(
        default=None,
        description="How many plants the caller expects this call to remove. "
                    "A mismatch is refused with 409."),
) -> list[dict[str, Any]]:
    """
    Replace the whole portfolio atomically.

    This exists because the browser did it as delete-then-insert with no
    transaction, and a failure between the two wiped the portfolio
    (CLAUDE_HANDOFF §8.15). `confirm_delete` is the second guard: an empty
    body from a half-initialised client would otherwise mean "delete
    everything" and be honoured.
    """
    try:
        return plants_store.replace_all(
            _owner(request), body.plants, expect_deletions=confirm_delete)
    except DeletionGuardTripped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
