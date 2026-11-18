"""
Pre-FID access — one decision, applied on every path to the data.
=================================================================
Pre-FID packages and the spend wave are the producer's development spend. The
rule (app/core/devex_share.py) is: the owner reads its own; anyone else reads a
section only while the owner's share of that section for that project is
active. This module turns the rule into checks the routes use, so the brief,
the package register, the spend wave, the project datasets and the one-shot
project view cannot drift apart:

    resolve(request, project_id)       who is asking, and what they may read
    read_tenant(access)                the tenant a permitted read is made in
    require(access, section, ...)      refuse with 403 unless the section is open
    require_section(section, ...)      the same, as a route dependency
    withheld(request, project_id, …)   for mixed answers: leave the pre-FID part out?

Ownership comes from the project record (projects.owner_tenant_id) and is
compared with the caller's tenant. If the record or the shares cannot be read
the answer is 503 — unavailable — never "nothing to show".

A permitted read by someone outside the owner company is made in the OWNER's
tenant (read_tenant). Row-level security admits only the owner and companies
with project_access, so without this a share held by an adviser with no
project relationship would pass the check and return nothing — an empty
answer that would look like "nothing recorded".

Nothing is cached: every request re-reads the shares, so a revocation closes
every path at once. Writes are never opened by a share. Attempts by anyone
other than the owner or platform staff are written to the entitlement audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request

from app.core.devex_share import PRE_FID_PHASES, decide, section_of
from app.core.request_tenant import company_from_payload, current_company, payload_from_request

PLATFORM_ADMIN = "PLATFORM_ADMIN"


@dataclass(frozen=True)
class Access:
    project_id: str               # the current id, after any alias
    project_name: Optional[str]
    owner_tenant: str             # projects.owner_tenant_id
    basis: str                    # owner | platform_admin | share | none
    sections: tuple[str, ...]
    tenant: Optional[str]
    user_id: Optional[str]

    @property
    def full(self) -> bool:
        return self.basis in ("owner", "platform_admin")

    def allows(self, section: str) -> bool:
        return section in self.sections


def is_pre_fid(phase: Any) -> bool:
    return getattr(phase, "value", phase) in PRE_FID_PHASES


# The three reads below are functions so tests can replace them.
def _owner_record(project_id: str) -> Optional[dict]:
    from app.core.projects_store import project_owner_record
    return project_owner_record(project_id)


def _active_sections(user_id: str, project_id: str) -> list[str]:
    from app.core import entitlements as ent
    return [section for row in ent.list_entitlements(user_id=user_id, project_id=project_id)
            if (section := section_of(row["capability"])) and row["status"] == "active"]


def _audit(*, allowed: bool, user_id: Optional[str], project_id: str, basis: str, route: str, reason: str) -> None:
    from app.core import entitlements as ent
    ent.log_access(allowed=allowed, user_id=user_id or "unknown", project_id=project_id,
                   basis=basis, reason=reason, route=route)


def unavailable(what: str) -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "PRE_FID_DATA_UNAVAILABLE",
        "message": f"{what} could not be read, so pre-FID data is unavailable. Nothing is shown "
                   "rather than an incomplete or empty figure. Try again shortly."})


def resolve(request: Optional[Request], project_id: str) -> Access:
    """Who is asking about this project's pre-FID data, and what they may read.

    404 when there is no such project; 503 when ownership or shares cannot be
    established. The caller's tenant is the verified token's, or the tenant
    bound for this request when a token is not at hand.
    """
    payload = payload_from_request(request) if request is not None else None
    payload = payload or {}
    tenant = company_from_payload(payload) or current_company()
    user_id = payload.get("user_id") or payload.get("email") or None

    try:
        record = _owner_record(project_id)
    except Exception as exc:  # noqa: BLE001 — any failure here is "unavailable"
        raise unavailable("The project's ownership record") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown project '{project_id}'")
    owner = record.get("owner_tenant_id")
    if not owner:
        raise unavailable("The project's owner")

    is_admin = bool(payload.get("is_platform_admin")) or tenant == PLATFORM_ADMIN
    is_owner = bool(tenant) and tenant == owner
    shared: list[str] = []
    if user_id and not (is_admin or is_owner):
        try:
            shared = _active_sections(user_id, record["project_id"])
        except Exception as exc:  # noqa: BLE001
            raise unavailable("The project's shares") from exc
    sections, basis = decide(is_owner=is_owner, is_platform_admin=is_admin, shared_sections=shared)
    return Access(project_id=record["project_id"], project_name=record.get("project_name"),
                  owner_tenant=owner, basis=basis, sections=sections, tenant=tenant, user_id=user_id)


def read_tenant(access: Access) -> Optional[str]:
    """The tenant to read pre-FID rows in: the owner's for a shared read, else
    None, meaning "as the caller" (the owner, or platform staff)."""
    return access.owner_tenant if access.basis == "share" else None


def refusal(section: str, write: bool) -> HTTPException:
    message = ("Only the project's owner changes its pre-FID data. A share is read-only." if write else
               "This pre-FID data has not been shared with you for this project. The owner's finance "
               "or executive function can share it.")
    return HTTPException(status_code=403, detail={
        "code": "PRE_FID_NOT_SHARED", "error": "forbidden", "section": section,
        "message": message, "reason": message})


def require(access: Access, section: str, *, write: bool = False, route: str) -> Access:
    """Refuse unless `section` is open to the caller. A write needs the owner."""
    ok = access.full if write else access.allows(section)
    if not access.full:
        _audit(allowed=ok, user_id=access.user_id, project_id=access.project_id, basis=access.basis,
               route=route, reason=f"section={section}; write={write}")
    if not ok:
        raise refusal(section, write)
    return access


def require_section(section: str, *, write: bool = False, route: str):
    """Route dependency for paths that carry `project_id`."""
    def dependency(project_id: str, request: Request) -> Access:
        return require(resolve(request, project_id), section, write=write, route=route)
    return dependency


def withheld(request: Optional[Request], project_id: str, section: str, *, route: str) -> bool:
    """For answers that mix pre-FID data with other data: must the pre-FID part
    be left out for this caller?

    False for a direct internal call (no request). True when the project is not
    in the registry, because its owner cannot be established.
    """
    if request is None:
        return False
    try:
        access = resolve(request, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return True
        raise
    ok = access.allows(section)
    if not access.full:
        _audit(allowed=ok, user_id=access.user_id, project_id=access.project_id, basis=access.basis,
               route=route, reason=f"section={section}; mixed answer")
    return not ok
