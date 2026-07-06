"""
Tenant context — FastAPI dependencies for project-scoped data access.

These dependencies sit on top of the RLS-aware session (db/session.py) and
provide higher-level helpers:

  get_tenant_company_id  — extracts company_id from the request JWT
  get_visible_project_ids — queries PostgreSQL for the caller's projects
  require_project_access  — raises 403 if caller cannot see a given project_id

All project data reads in API routes should go through one of these rather
than querying `projects` or `project_access` directly without a session.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


# ── Low-level identity extraction ────────────────────────────────────────────

def get_tenant_company_id(request: Request) -> Optional[str]:
    """
    Return the company_id of the authenticated user, or None for guests.
    The value comes from request.state.user_payload set by auth middleware.
    """
    payload = getattr(request.state, "user_payload", None)
    if not payload:
        return None
    if payload.get("is_platform_admin"):
        return "PLATFORM_ADMIN"
    return payload.get("company_id")


def require_authenticated_company(
    company_id: Optional[str] = Depends(get_tenant_company_id),
) -> str:
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access project data.",
        )
    return company_id


# ── Project visibility ────────────────────────────────────────────────────────

async def get_visible_project_ids(
    db: AsyncSession = Depends(get_db),
    company_id: str = Depends(require_authenticated_company),
) -> list[str]:
    """
    Return the list of project_ids visible to the calling tenant.
    The RLS policy on `projects` already filters rows — this just returns
    what PostgreSQL gives us for the current app.current_company_id setting.
    """
    if company_id == "PLATFORM_ADMIN":
        rows = await db.execute(text("SELECT project_id FROM projects WHERE is_active = true"))
    else:
        rows = await db.execute(
            text("SELECT project_id FROM projects WHERE is_active = true")
        )
    return [row[0] for row in rows.fetchall()]


async def get_visible_project_ids_with_actor_types(
    db: AsyncSession = Depends(get_db),
    company_id: str = Depends(require_authenticated_company),
) -> dict[str, list[str]]:
    """
    Return {project_id: [actor_type, ...]} for all projects visible to the caller.
    Used by the ABAC engine to build UserAttributes.actor_type_per_project.
    """
    if company_id == "PLATFORM_ADMIN":
        rows = await db.execute(
            text("""
                SELECT pa.project_id, pa.actor_type
                FROM project_access pa
                JOIN projects p ON p.project_id = pa.project_id
                WHERE p.is_active = true
            """)
        )
    else:
        rows = await db.execute(
            text("""
                SELECT pa.project_id, pa.actor_type
                FROM project_access pa
                JOIN projects p ON p.project_id = pa.project_id
                WHERE p.is_active = true
            """)
        )

    result: dict[str, list[str]] = {}
    for project_id, actor_type in rows.fetchall():
        result.setdefault(project_id, []).append(actor_type)
    return result


async def require_project_access(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    company_id: str = Depends(require_authenticated_company),
) -> str:
    """
    Raise HTTP 403 if the calling tenant cannot see the given project_id.
    The check is done by attempting a SELECT through RLS — if the row is
    invisible, PostgreSQL returns nothing and we deny.
    """
    if company_id == "PLATFORM_ADMIN":
        return project_id

    row = await db.execute(
        text("SELECT project_id FROM projects WHERE project_id = :pid AND is_active = true"),
        {"pid": project_id},
    )
    if row.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project '{project_id}' not found or access denied.",
        )
    return project_id


# ── ABAC context builder ──────────────────────────────────────────────────────

async def build_abac_user_attributes(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> "UserAttributes":  # noqa: F821  (imported lazily to avoid circular import)
    """
    Build a fully-populated UserAttributes for the ABAC engine from the JWT
    payload + the PostgreSQL project_access table.

    This replaces the static project_registry lookup in legacy code paths.
    """
    from app.core.abac import (
        ActorType, Capability, ClearanceLevel, UserAttributes,
    )

    payload = getattr(request.state, "user_payload", None)
    if not payload:
        return UserAttributes(
            user_id="guest",
            company_id="",
            actor_type_per_project={},
            clearance_level=ClearanceLevel.STANDARD,
        )

    company_id: str = payload.get("company_id", "")

    # Fetch actor types per project from PostgreSQL (RLS-filtered)
    rows = await db.execute(
        text("""
            SELECT pa.project_id, pa.actor_type
            FROM project_access pa
            JOIN projects p ON p.project_id = pa.project_id
            WHERE p.is_active = true
        """)
    )
    actor_type_per_project: dict[str, list[ActorType]] = {}
    for row_project_id, actor_type_str in rows.fetchall():
        try:
            at = ActorType(actor_type_str)
        except ValueError:
            continue
        actor_type_per_project.setdefault(row_project_id, []).append(at)

    clearance_str = payload.get("clearance_level", "STANDARD")
    try:
        clearance = ClearanceLevel(clearance_str)
    except ValueError:
        clearance = ClearanceLevel.STANDARD

    caps_raw: list[str] = payload.get("capabilities", [])
    capabilities = set()
    for c in caps_raw:
        try:
            capabilities.add(Capability(c))
        except ValueError:
            pass

    return UserAttributes(
        user_id=payload.get("user_id", ""),
        company_id=company_id,
        actor_type_per_project=actor_type_per_project,
        clearance_level=clearance,
        jurisdiction=payload.get("jurisdiction", ""),
        kyc_status=payload.get("kyc_status", "VERIFIED"),
        nda_signed_with=set(payload.get("nda_signed_with", [])),
        assigned_audits=set(payload.get("assigned_audits", [])),
        capabilities=capabilities,
        credit_rating=payload.get("credit_rating", "NR"),
        credit_rating_source=payload.get("credit_rating_source", "GEX"),
        export_licenses=payload.get("export_licenses", []),
        token_ready=bool(payload.get("token_ready", False)),
        transformation_license=bool(payload.get("transformation_license", False)),
        aggregation_limit_mt=payload.get("aggregation_limit_mt"),
    )
