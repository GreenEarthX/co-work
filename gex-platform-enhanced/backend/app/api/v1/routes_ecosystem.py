"""
Ecosystem Navigator API — map publication, server-side.

Replaces the browser-only publication path in
`frontend/src/lib/ecosystem/userProjects.ts`, which wrote to `localStorage` and
therefore never reached another user.

Authenticated, not public: the map is reached after login. The `PUBLIC` tier on
the `ecosystem.map.*` rights in `permission_engine.py` is an ACCESS TIER (which
roles may see it), not a statement that the HTTP route is unauthenticated. Adding
it to `route_security.PUBLIC_ROUTES` would be a separate, deliberate decision.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import ecosystem_store as store
from app.core.request_tenant import company_from_payload, payload_from_request

router = APIRouter(prefix="/ecosystem", tags=["Ecosystem Navigator"])


def _caller(request: Request) -> tuple[str, str]:
    """(tenant_id, user_id) for the authenticated caller."""
    payload = payload_from_request(request)
    tenant = company_from_payload(payload)
    if not tenant:
        raise HTTPException(status_code=403, detail="no tenant context")
    user = (payload or {}).get("sub") or (payload or {}).get("email") or "unknown"
    return tenant, str(user)


class PublishIn(BaseModel):
    slug: str
    name: str
    lat: float
    lng: float
    # Lifecycle is two fields (Data Structure v4.2). Older clients send only a
    # legacy status; the store normalises rather than refusing them.
    phase: str = "unknown"
    status: str = "active"
    country: Optional[str] = None
    moleculeType: Optional[str] = None
    productionPathway: Optional[str] = None
    owner: Optional[str] = None
    capacity: Optional[str] = None
    capacityValue: Optional[str] = None
    capacityUnit: Optional[str] = None
    extras: dict[str, Any] = Field(default_factory=dict)
    visibleFields: list[str] = Field(default_factory=list)


class EnrichIn(BaseModel):
    targetEcoId: str
    payload: dict[str, Any] = Field(default_factory=dict)
    visibleFields: list[str] = Field(default_factory=list)
    matchRule: Optional[str] = None
    matchReason: Optional[str] = None


@router.get("/projects")
def list_projects(request: Request) -> dict[str, Any]:
    """The map feed. Every live marker, redacted to what its publisher exposed.

    Enrichments are returned ALONGSIDE the projects rather than merged into
    them. More than one tenant may have a reading of the same project, and
    collapsing them here would destroy exactly the disagreement the map exists
    to show. The client decides how to present them.
    """
    payload = payload_from_request(request)
    viewer = company_from_payload(payload)
    projects = [store.redact_for_viewer(p, viewer) for p in store.list_published()]
    return {
        "projects": projects,
        "enrichments": store.list_enrichments(),
        "count": len(projects),
    }


@router.post("/publish")
def publish(body: PublishIn, request: Request) -> dict[str, Any]:
    tenant, user = _caller(request)
    try:
        rec = store.publish_project(
            tenant_id=tenant, user_id=user, slug=body.slug, name=body.name,
            lat=body.lat, lng=body.lng, phase=body.phase, status=body.status,
            country=body.country,
            molecule_type=body.moleculeType,
            production_pathway=body.productionPathway, owner_name=body.owner,
            capacity_label=body.capacity, capacity_value=body.capacityValue,
            capacity_unit=body.capacityUnit, extras=body.extras,
            visible_fields=body.visibleFields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"kind": "added", "project": store.redact_for_viewer(rec, tenant)}


@router.post("/enrich")
def enrich(body: EnrichIn, request: Request) -> dict[str, Any]:
    tenant, user = _caller(request)
    if store.get_published(body.targetEcoId) is None:
        raise HTTPException(status_code=404, detail="target project not found")
    result = store.attach_enrichment(
        tenant_id=tenant, user_id=user, target_eco_id=body.targetEcoId,
        payload=body.payload, visible_fields=body.visibleFields,
        match_rule=body.matchRule, match_reason=body.matchReason)
    return {"kind": "enriched", **result}


@router.delete("/publish/{slug}")
def withdraw(slug: str, request: Request) -> dict[str, Any]:
    tenant, _ = _caller(request)
    return {"withdrawn": store.withdraw_project(tenant_id=tenant, slug=slug)}


@router.delete("/enrich/{target_eco_id}")
def withdraw_enrichment(target_eco_id: str, request: Request) -> dict[str, Any]:
    tenant, _ = _caller(request)
    return {"withdrawn": store.withdraw_enrichment(
        tenant_id=tenant, target_eco_id=target_eco_id)}
