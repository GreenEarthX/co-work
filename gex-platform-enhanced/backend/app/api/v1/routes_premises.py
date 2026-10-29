"""
Project premises — propose, confirm, contest, withdraw (JML 2026-10-28; 077).

  GET  /api/v1/premises/{project_id}                         in force + history
  POST /api/v1/premises/{project_id}                         propose (multipart: field, to_value, file)
  POST /api/v1/premises/{project_id}/{change_id}/confirm     second party or GEX
  POST /api/v1/premises/{project_id}/{change_id}/contest     any party (multipart: note, file)
  POST /api/v1/premises/{project_id}/{change_id}/reject      GEX staff
  POST /api/v1/premises/{project_id}/{change_id}/withdraw    the proposing company

Who may do what is app.core.premises; this module only wires it. Every
decision that moves a premise re-evaluates the project.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core import premises as pm

router = APIRouter()


def _context(request: Request, project_id: str):
    from app.api.v1.routes_projects import _visible_ids_from_jwt
    from app.core.project_registry import get_project_profile
    from app.core.request_tenant import payload_from_request

    payload = payload_from_request(request) or {}
    if not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    profile = get_project_profile(project_id)
    if profile is None or project_id not in _visible_ids_from_jwt(payload):
        raise HTTPException(status_code=404, detail="Project not found")
    party = pm.party_for(payload, profile.owner_company_id, profile.stakeholder_company_ids)
    return payload, profile, party


def _refused(exc: pm.PremiseRefusal):
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


async def _apply(project_id: str, field: str, value: Optional[str], actor: str, reason: str) -> dict:
    """Put a confirmed premise into project_context and re-evaluate."""
    from app.api.v1.routes_bankability_proxy import reevaluate
    from app.core.project_registry import get_effective_context
    from app.core.projects_store import update_context

    current = get_effective_context(project_id)
    ctx = {"power_model": getattr(current, "power_model", None) or "GRID_CONNECTED",
           "phase": getattr(current, "phase", None) or "development",
           "financing_model": getattr(current, "financing_model", None) or "PROJECT_FINANCE"}
    old = ctx.get(field)
    if value is not None:
        ctx[field] = value
    update_context(project_id=project_id, actor=actor, changes=[(field, old, ctx[field])], **ctx)
    try:
        return (await reevaluate(project_id, reason=reason, actor=actor))["changes"]
    except HTTPException as exc:
        return {"error": exc.detail, "state_withdrawn": True}


async def _reevaluate(project_id: str, actor: str, reason: str) -> dict:
    from app.api.v1.routes_bankability_proxy import reevaluate
    try:
        return (await reevaluate(project_id, reason=reason, actor=actor))["changes"]
    except HTTPException as exc:
        return {"error": exc.detail, "state_withdrawn": True}


@router.get("/premises/{project_id}")
def list_premises(project_id: str, request: Request):
    from app.core.project_registry import get_effective_context

    _, _, party = _context(request, project_id)
    ctx = get_effective_context(project_id)
    overrides = pm.protective_overrides(project_id)
    in_force = {f: overrides.get(f, getattr(ctx, f, None)) if f in overrides else getattr(ctx, f, None)
                for f in pm.FIELDS}
    return {"project_id": project_id, "declared": {f: getattr(ctx, f, None) for f in pm.FIELDS},
            "in_force_for_the_engine": in_force, "protective_overrides": overrides,
            "changes": pm.changes(project_id),
            "you": {"is_owner_executive": party.is_owner_executive, "is_gex": party.is_gex,
                    "is_project_party": party.is_project_party, "company_id": party.company_id}}


@router.post("/premises/{project_id}", status_code=201)
async def propose(project_id: str, request: Request, field: str = Form(...), to_value: str = Form(...),
                  file: Optional[UploadFile] = File(default=None)):
    from app.core.project_registry import VALID_FINANCING_MODELS, VALID_POWER_MODELS, get_effective_context

    payload, _, party = _context(request, project_id)
    if field not in pm.FIELDS:
        raise HTTPException(status_code=422, detail=f"field must be one of {pm.FIELDS}")
    allowed = VALID_FINANCING_MODELS if field == "financing_model" else VALID_POWER_MODELS
    if to_value not in allowed:
        raise HTTPException(status_code=422, detail=f"{field} must be one of {allowed}")
    try:
        pm.check_propose(party)
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    current = getattr(get_effective_context(project_id), field, None)
    if current == to_value:
        raise HTTPException(status_code=422, detail="That premise is already declared.")
    if not pm.removes_items(field, current, to_value):
        # Back to project finance strengthens the bar: no second party needed.
        change_id = pm.open_change(project_id, field, current, to_value, party)
        pm.set_status(project_id, change_id, "CONFIRMED", party, note="Removes no evidence; applied at once.",
                      applied=True)
        return {"change_id": change_id, "status": "CONFIRMED",
                "reevaluation": await _apply(project_id, field, to_value, party.user_id, f"premise {field} -> {to_value}")}
    if file is None:
        raise HTTPException(status_code=422, detail={
            "code": "PREMISE_NEEDS_DOCUMENT",
            "message": "This change removes evidence from the bar: attach the document that supports it."})
    content = await file.read()
    try:
        change_id = pm.open_change(project_id, field, current, to_value, party)
        doc = pm.add_document(project_id, change_id, "SUPPORT", content, file.filename, party, None)
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    return {"change_id": change_id, "status": "PENDING", "document": doc,
            "message": "Pending: nothing changes until a second party confirms."}


@router.post("/premises/{project_id}/{change_id}/confirm")
async def confirm(project_id: str, change_id: int, request: Request, note: Optional[str] = Form(default=None)):
    _, _, party = _context(request, project_id)
    try:
        change = pm.get_change(project_id, change_id)
        pm.check_confirm(party, change)
        if not any(d["role"] == "SUPPORT" for c in pm.changes(project_id) if c["id"] == change_id
                   for d in c["documents"]):
            raise pm.PremiseRefusal(409, "NO_SUPPORTING_DOCUMENT", "No supporting document is registered.")
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    pm.set_status(project_id, change_id, "CONFIRMED", party, note=note, applied=True)
    return {"change_id": change_id, "status": "CONFIRMED",
            "reevaluation": await _apply(project_id, change["field"], change["to_value"], party.user_id,
                                         f"premise {change['field']} -> {change['to_value']} confirmed")}


@router.post("/premises/{project_id}/{change_id}/contest")
async def contest(project_id: str, change_id: int, request: Request, note: str = Form(...),
                  file: UploadFile = File(...)):
    _, _, party = _context(request, project_id)
    try:
        change = pm.get_change(project_id, change_id)
        pm.check_contest(party, change)
        doc = pm.add_document(project_id, change_id, "CONTEST", await file.read(), file.filename, party, note)
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    pm.set_status(project_id, change_id, "CONTESTED", party)
    # Contesting a premise already in force restores the protective one now.
    reevaluation = await _reevaluate(project_id, party.user_id, f"premise {change['field']} contested") \
        if change["applied"] else None
    return {"change_id": change_id, "status": "CONTESTED", "document": doc, "reevaluation": reevaluation}


@router.post("/premises/{project_id}/{change_id}/reject")
async def reject(project_id: str, change_id: int, request: Request, note: str = Form(...)):
    _, _, party = _context(request, project_id)
    if not party.is_gex:
        raise HTTPException(status_code=403, detail={"code": "GEX_ONLY", "message": "GEX staff reject a premise."})
    try:
        change = pm.get_change(project_id, change_id)
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    pm.set_status(project_id, change_id, "REJECTED", party, note=note)
    reevaluation = await _reevaluate(project_id, party.user_id, f"premise {change['field']} rejected") \
        if change["applied"] else None
    return {"change_id": change_id, "status": "REJECTED", "reevaluation": reevaluation}


@router.post("/premises/{project_id}/{change_id}/withdraw")
def withdraw(project_id: str, change_id: int, request: Request):
    _, _, party = _context(request, project_id)
    try:
        change = pm.get_change(project_id, change_id)
        pm.check_withdraw(party, change)
    except pm.PremiseRefusal as exc:
        raise _refused(exc)
    pm.set_status(project_id, change_id, "WITHDRAWN", party)
    return {"change_id": change_id, "status": "WITHDRAWN"}
