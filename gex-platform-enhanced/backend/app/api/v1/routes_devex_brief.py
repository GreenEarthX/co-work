"""
DEVEX brief — the owner's view of all pre-FID spend, and its shares.
====================================================================
  GET    /api/v1/devex-brief/{project_id}                 the brief, limited to what the caller may read
  GET    /api/v1/devex-brief/{project_id}/shares          the shares of this project      (owner finance/executive)
  POST   /api/v1/devex-brief/{project_id}/shares          share sections with one user    (owner finance/executive)
  DELETE /api/v1/devex-brief/{project_id}/shares/{id}     revoke one shared section       (owner finance/executive)

Access is decided by app/core/pre_fid_access.py, the same decision the package
register, the spend wave, the project datasets and the one-shot project view
use: the owner (projects.owner_tenant_id) reads its own data; anyone else
reads a section only while the owner's share of that section is active. Inside
the owner company the brief itself goes to finance and executives.

A share is one row per section in the project entitlement store
(finance_entitlements, capability "DEVEX_SHARE:<SECTION>"). Revoking it closes
the brief section and the matching API path together, because both read the
same row on every request. Every read of the brief is audited.

The brief is assembled here and holds only the sections the caller may read.
Its data is read in the owner's tenant, taken from the project record. A read
that fails is answered 503: an empty brief means "nothing recorded" and is
never used to mean "could not be read".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import entitlements as ent
from app.core import pre_fid_access
from app.core.devex_share import (
    SECTION_LABELS, brief_sections, build_brief, capability, may_manage_shares, normalise_expiry,
    section_of, validate_share,
)
from app.core.request_tenant import payload_from_request

router = APIRouter(prefix="/api/v1/devex-brief", tags=["devex-brief"])


class ShareRequest(BaseModel):
    user_id: str                       # the person the sections are shared with
    sections: list[str]
    expires_at: Optional[str] = None   # ISO-8601 date or datetime
    reason: Optional[str] = None


def _payload(request: Request) -> dict:
    payload = payload_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def _read_packages(project_id: str, owner_tenant: str) -> list[dict]:
    from app.api.v1.development_packages import _row_to_response
    from app.core.db_backend import capital_connection

    conn = capital_connection(company_id=owner_tenant)
    try:
        rows = conn.execute("SELECT * FROM development_packages WHERE project_id=?", [project_id]).fetchall()
    finally:
        conn.close()
    return [_row_to_response(r) for r in rows]


def _read_spend_wave(project_id: str, owner_tenant: str) -> tuple[Optional[list], Optional[str]]:
    from app.core.projects_store import dataset_strict

    row = dataset_strict(project_id, "spend_wave", owner_tenant)
    if not row:
        return None, None
    payload = row["payload"]
    return (json.loads(payload) if isinstance(payload, str) else payload), row["verification_state"]


@router.get("/{project_id}")
def read_brief(project_id: str, request: Request):
    payload = _payload(request)
    access = pre_fid_access.resolve(request, project_id)
    function = payload.get("business_function")
    sections = brief_sections(access.sections, access.basis, function)
    pre_fid_access._audit(allowed=bool(sections), user_id=access.user_id, project_id=access.project_id,
                          basis=access.basis, route="devex_brief",
                          reason=f"sections={'+'.join(sections) or 'none'}")
    if not sections:
        raise pre_fid_access.refusal("BRIEF", write=False)

    try:
        needs_register = any(s in sections for s in ("SUMMARY", "BREAKDOWN", "PACKAGES"))
        packages = _read_packages(access.project_id, access.owner_tenant) if needs_register else []
        wave, verification = (_read_spend_wave(access.project_id, access.owner_tenant)
                              if "FUNDING" in sections else (None, None))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a failed read is "unavailable", never an empty brief
        raise pre_fid_access.unavailable("The project's pre-FID records") from exc

    return {
        "project_id": access.project_id,
        "project_name": access.project_name,
        "basis": access.basis,
        "read_only": not access.full,
        "can_manage_shares": may_manage_shares(owns_project=access.basis == "owner", business_function=function),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "section_labels": SECTION_LABELS,
        **build_brief(packages, wave, sections, verification),
    }


def _manager(request: Request, project_id: str) -> pre_fid_access.Access:
    payload = _payload(request)
    access = pre_fid_access.resolve(request, project_id)
    if not may_manage_shares(owns_project=access.basis == "owner",
                             business_function=payload.get("business_function")):
        raise HTTPException(status_code=403, detail={
            "error": "forbidden", "route": "devex_brief_shares",
            "reason": "Only the finance or executive function of the project's owner shares its pre-FID data."})
    return access


def _share_row(row: dict) -> dict:
    return {"entitlement_id": row["entitlement_id"], "user_id": row["user_id"],
            "section": section_of(row["capability"]), "granted_by": row["granted_by"],
            "granted_at": row["granted_at"], "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"], "revoked_by": row["revoked_by"],
            "reason": row["reason"], "status": row["status"]}


@router.get("/{project_id}/shares")
def list_shares(project_id: str, request: Request):
    access = _manager(request, project_id)
    rows = ent.list_entitlements(project_id=access.project_id)
    return {"project_id": access.project_id, "section_labels": SECTION_LABELS,
            "shares": [_share_row(r) for r in rows if section_of(r["capability"])]}


@router.post("/{project_id}/shares", status_code=201)
def create_share(project_id: str, body: ShareRequest, request: Request):
    access = _manager(request, project_id)
    try:
        sections = validate_share(user_id=body.user_id, sections=body.sections, expires_at=body.expires_at)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    user_id = body.user_id.strip()
    already = {section_of(r["capability"]) for r in ent.list_entitlements(user_id=user_id, project_id=access.project_id)
               if r["status"] == "active"}
    created = [ent.grant_entitlement(
        user_id=user_id, project_id=access.project_id, granted_by=access.user_id or "owner",
        capability=capability(section), reason=body.reason, expires_at=normalise_expiry(body.expires_at))
        for section in sections if section not in already]
    return {"project_id": access.project_id, "shares": [_share_row(r) for r in created],
            "already_shared": [s for s in sections if s in already],
            "note": "Read-only. Each section opens only itself, on the brief and on the matching API."}


@router.delete("/{project_id}/shares/{entitlement_id}")
def revoke_share(project_id: str, entitlement_id: str, request: Request):
    access = _manager(request, project_id)
    row = ent.get_entitlement(entitlement_id)
    if not row or row["project_id"] != access.project_id or not section_of(row["capability"]):
        raise HTTPException(status_code=404, detail="No such pre-FID share on this project")
    return _share_row(ent.revoke_entitlement(entitlement_id, revoked_by=access.user_id or "owner"))
