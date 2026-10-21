"""
Reviewer appointments — the routes. Policy and checks: core/reviewer_appointments.py.

    POST   /api/v1/projects/{project_id}/reviewers             GEX staff — appoint
    DELETE /api/v1/projects/{project_id}/reviewers/{user_id}   GEX staff — revoke (?role=…)
    GET    /api/v1/projects/{project_id}/reviewers             GEX staff, the project's
                                                               stakeholders, its reviewers

Owner decision 2026-10-21 (JML): GEX staff appoint, on the instruction of a named
party. Every appointment and revocation is written to the event ledger with the
employee's identity, the instructing party and the instruction document's hash.

ABAC maps no resource for /projects/{id}/reviewers (abac_middleware
._extract_resource), so the middleware authenticates and passes the request on.
Every handler here authorises the caller itself.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.account_lifecycle import AccountLifecycleError, assert_activator_is_gex_staff
from app.core.event_store import append_event
from app.core.project_registry import company_slug, get_project_profile, normalize_project_id
from app.core import reviewer_appointments as ra

logger = logging.getLogger("gex.reviewer_appointments")
router = APIRouter()


class AppointRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    instructed_by: str = Field(..., description="The party whose decision relies on the gate")
    instruction_sha256: str = Field(..., description="sha256 of the instruction document")


class RevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3)


def _actor(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(status_code=401, detail="Authentication required")
    return {**payload, "user_id": payload.get("user_id") or payload.get("sub")}


def _require_gex_staff(request: Request) -> dict:
    actor = _actor(request)
    try:
        assert_activator_is_gex_staff(actor)   # the same rule as account vetting
    except AccountLifecycleError as exc:
        raise HTTPException(status_code=403, detail={
            "code": "GEX_STAFF_ONLY",
            "message": "Only a GEX platform administrator appoints or revokes reviewers."}) from exc
    return actor


def _project(project_id: str):
    pid = normalize_project_id(project_id)
    profile = get_project_profile(pid) if pid else None
    if not profile:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND",
                                                     "message": f"{project_id!r} is unknown."})
    return pid, profile


def _store():
    """(connection, writes project_access?).

    On PostgreSQL ONE caller-bound connection carries all three records: the auth
    tables have no RLS, and project_access accepts the write because a GEX admin's
    request binds PLATFORM_ADMIN (request_tenant.company_from_payload), logged by
    the shim. On SQLite there is no project_access and no RLS to satisfy."""
    from app.core.db_backend import evidence_connection, evidence_is_postgres, is_postgres

    if is_postgres() != evidence_is_postgres():
        raise HTTPException(status_code=503, detail={
            "code": "SPLIT_STORE",
            "message": "Accounts and evidence are on different stores; an appointment cannot be atomic."})
    if is_postgres():
        return evidence_connection(), True
    from app.core.auth import auth_db_connection

    return auth_db_connection(), False


def _refusal(exc: ra.AppointmentRefused) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


def _commit(fn, **kwargs) -> dict:
    """Run one core change in its own transaction and commit it."""
    conn, write_access = _store()
    try:
        result = fn(conn, write_project_access=write_access, **kwargs)
        conn.commit()
        return result
    except ra.AppointmentRefused as exc:
        conn.rollback()
        raise _refusal(exc) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/{project_id}/reviewers")
async def appoint_reviewer(project_id: str, body: AppointRequest, request: Request):
    actor = _require_gex_staff(request)
    pid, profile = _project(project_id)
    result = _commit(ra.appoint, project_id=pid, owner_company_id=profile.owner_company_id,
                     appointee_user_id=body.user_id, role=body.role, appointer=actor,
                     instructed_by=body.instructed_by, instruction_sha256=body.instruction_sha256)
    # The ledger has its own connection, so it is written after the commit (on SQLite
    # an open write transaction locks the file against it). An appointment that cannot
    # be recorded is not made: undo it and fail.
    try:
        append_event(event_type="REVIEWER_APPOINTED", aggregate_type="reviewer_appointment",
                     aggregate_id=f"{pid}:{result['user_id']}:{result['role']}", data=result,
                     user_id=actor["user_id"], project_id=pid, company_id=result["company_id"])
    except Exception as exc:
        logger.exception("appointment not recorded; undoing it")
        _commit(ra.revoke, project_id=pid, appointee_user_id=result["user_id"], role=result["role"])
        raise HTTPException(status_code=500, detail={
            "code": "APPOINTMENT_NOT_RECORDED",
            "message": "The audit record could not be written, so the appointment was undone."}) from exc
    logger.info("reviewer appointed: %s as %s on %s by %s, instructed by %s",
                result["user_id"], result["role"], pid, actor["user_id"], result["instructed_by"])
    return result


@router.delete("/{project_id}/reviewers/{user_id}")
async def revoke_reviewer(project_id: str, user_id: str, body: RevokeRequest, request: Request,
                          role: str = Query(..., description="The reviewer role to revoke")):
    actor = _require_gex_staff(request)
    pid, _ = _project(project_id)
    # A revocation is never undone for want of a record: removing access is the safe
    # direction. A ledger failure is logged loudly instead.
    result = _commit(ra.revoke, project_id=pid, appointee_user_id=user_id, role=role)
    try:
        append_event(event_type="REVIEWER_REVOKED", aggregate_type="reviewer_appointment",
                     aggregate_id=f"{pid}:{user_id}:{result['role']}", data={**result, "reason": body.reason},
                     user_id=actor["user_id"], project_id=pid, company_id=result["company_id"])
    except Exception:
        logger.exception("revocation of %s as %s on %s made but NOT recorded", user_id, result["role"], pid)
    return {**result, "reason": body.reason, "effective": "at the reviewer's next sign-in"}


@router.get("/{project_id}/reviewers")
async def list_reviewers(project_id: str, request: Request):
    """Who verifies which gates on this project. Visible to GEX staff, the project's
    stakeholders and its reviewers — knowing who checks the evidence is the point."""
    actor = _actor(request)
    pid, profile = _project(project_id)
    stakeholders = {profile.owner_company_id, *(company_slug(n) for n in profile.associated_company_names)}
    conn, _ = _store()
    try:
        reviewers = ra.list_appointments(conn, pid)
    finally:
        conn.close()
    allowed = (bool(actor.get("is_platform_admin")) or actor.get("company_id") in stakeholders
               or any(r["user_id"] == actor["user_id"] for r in reviewers))
    if not allowed:
        raise HTTPException(status_code=403, detail={"code": "NOT_ON_PROJECT",
                                                     "message": "You are not a stakeholder or reviewer on this project."})
    # The screen shows the appoint form only when the server says so; the browser
    # never decides who is GEX staff.
    return {"project_id": pid, "reviewers": reviewers, "can_appoint": bool(actor.get("is_platform_admin")),
            "roles": {role: ra.gates_for(role) for role in sorted(ra.REVIEWER_ROLES)}}
