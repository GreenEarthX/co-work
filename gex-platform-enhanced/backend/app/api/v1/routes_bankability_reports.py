"""
Bankability reports — the pull and the push (JML, 2026-10-28).

  GET  /api/v1/projects/{id}/report               the project as the engine sees
                                                  it for the caller: state, gates
                                                  and every open item in parallel
  GET  /api/v1/projects/{id}/report-recipients    the designated executives
  PUT  /api/v1/projects/{id}/report-recipients    owner's executive or GEX staff
  GET  /api/v1/bankability-updates                my notifications (the push)
  POST /api/v1/bankability-updates/{id}/read

Everything shown comes from the engine's stored snapshot, refreshed if the
rules changed (routes_bankability_proxy.fresh_snapshot).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


def _caller(request: Request) -> dict:
    from app.core.request_tenant import payload_from_request

    payload = payload_from_request(request) or {}
    if not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def _visible_or_404(project_id: str, payload: dict):
    from app.api.v1.routes_projects import _visible_ids_from_jwt
    from app.core.project_registry import get_project_profile

    profile = get_project_profile(project_id)
    if profile is None or project_id not in _visible_ids_from_jwt(payload):
        raise HTTPException(status_code=404, detail="Project not found")
    return profile


@router.get("/projects/{project_id}/report")
async def project_report(project_id: str, request: Request):
    from app.api.v1.routes_bankability_proxy import _load_evidence, engine_rules, fresh_snapshot
    from app.core.bankability_reports import recipients
    from app.core.engine_view import bankability_view, open_items, persona_for

    payload = _caller(request)
    profile = _visible_or_404(project_id, payload)
    persona = persona_for(payload, profile.owner_company_id)
    persona_gates = (await engine_rules()).get("persona_gates", {})
    snapshot, evaluated_at = await fresh_snapshot(project_id)
    return {
        "project_id": project_id,
        "project_name": profile.project_name,
        "bankability": bankability_view(snapshot, persona, persona_gates, evaluated_at),
        "open_items": open_items(snapshot, persona, persona_gates, _load_evidence(project_id),
                                 today=date.today().isoformat()),
        "recipients": recipients(project_id),
    }


@router.get("/projects/{project_id}/report-recipients")
def get_recipients(project_id: str, request: Request):
    from app.core.bankability_reports import recipients

    _visible_or_404(project_id, _caller(request))
    return {"project_id": project_id, "recipients": recipients(project_id)}


class RecipientsBody(BaseModel):
    user_ids: list[str]


@router.put("/projects/{project_id}/report-recipients")
def put_recipients(project_id: str, body: RecipientsBody, request: Request):
    """Designate who receives the project's reports: the owner company's
    executive or GEX staff; each recipient an ACTIVE account of a company
    that is party to the project."""
    from app.core.bankability_reports import set_recipients
    from app.core.projects_store import _rows

    payload = _caller(request)
    profile = _visible_or_404(project_id, payload)
    owner_exec = (payload.get("company_id") == profile.owner_company_id
                  and payload.get("business_function") == "EXECUTIVE")
    if not (owner_exec or payload.get("is_platform_admin")):
        raise HTTPException(status_code=403, detail={
            "code": "OWNER_EXECUTIVE_OR_GEX", "message": "Only the owner's executive or GEX staff designate recipients."})
    if not body.user_ids:
        raise HTTPException(status_code=422, detail="Name at least one recipient.")
    parties = profile.stakeholder_company_ids
    found = {r["user_id"]: r for r in _rows(
        "SELECT user_id, company_id, account_state FROM auth_users WHERE user_id = ANY(:ids)",
        {"ids": list(body.user_ids)})}
    refused = [u for u in body.user_ids if u not in found or found[u]["account_state"] != "ACTIVE"
               or found[u]["company_id"] not in parties]
    if refused:
        raise HTTPException(status_code=422, detail={
            "code": "NOT_A_PROJECT_PARTY", "refused": refused,
            "message": "Recipients must be active accounts of a company party to the project."})
    return {"project_id": project_id,
            "recipients": set_recipients(project_id, body.user_ids, payload["user_id"])}


@router.get("/bankability-updates")
def my_updates(request: Request, limit: int = 50):
    from app.core.bankability_reports import my_notifications

    _caller(request)
    items = my_notifications(min(max(limit, 1), 200))
    return {"unread": sum(1 for i in items if not i["read_at"]), "items": items}


@router.post("/bankability-updates/{notification_id}/read")
def read_update(notification_id: int, request: Request):
    from app.core.bankability_reports import mark_read

    _caller(request)
    if not mark_read(notification_id):
        raise HTTPException(status_code=404, detail="No unread notification of yours with that id.")
    return {"id": notification_id, "read": True}
