"""
Canonical projects store — PostgreSQL.
======================================
Collision resolved 2026-08-07 (user ruling): **the PostgreSQL shape wins.**

There used to be two tables called `projects`:

  · SQLite  — written by the /projects/new on-ramp. owner was a company
              *name*, no tenant FK, no RLS.
  · Postgres — migration 020. owner_tenant_id FK -> tenants, RLS-protected.

The Postgres one is now the only one. This module is the single accessor for
it, plus project_context / project_context_events, which moved with it
(migration 033) so that `create_project()` stays atomic — all three writes are
one transaction in one store.

TENANT CONTEXT
--------------
These tables are RLS-protected. Every connection MUST set
`app.current_company_id` or it sees nothing (fails closed, by design — see
migration 032, which removed the empty-string bypass).

Registry/ABAC lookups are platform-internal and run with the PLATFORM_ADMIN
sentinel: `get_project_profile()` is called while *deciding* what a user may
see, so it cannot itself be filtered by that decision. Request-scoped reads
should go through app/db/session.py's per-request tenant context instead.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger("gex.projects_store")

PLATFORM_ADMIN = "PLATFORM_ADMIN"


def _engine():
    from app.db.session import get_sync_engine

    return get_sync_engine()


def _rows(sql: str, params: dict, company_id: str = PLATFORM_ADMIN) -> list[dict]:
    """Run a read with an explicit tenant context. Never leaves it unset."""
    try:
        with _engine().connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_company_id = '{_safe(company_id)}'"))
            return [dict(r) for r in conn.execute(text(sql), params).mappings()]
    except Exception as exc:  # noqa: BLE001
        # The registry is consulted on hot paths (ABAC, JWT scope). A database
        # blip must degrade to "no runtime projects", not 500 every request —
        # the static seed profiles still answer. Logged, never silent.
        logger.warning("projects_store read failed (%s): %s", sql.split()[0], exc)
        return []


def _safe(company_id: str) -> str:
    """Whitelist before interpolation — SET LOCAL cannot take a bind param."""
    import re

    if company_id == PLATFORM_ADMIN or re.fullmatch(r"[a-z0-9_]{1,120}", company_id or ""):
        return company_id
    raise ValueError(f"unsafe company_id for tenant context: {company_id!r}")


def fetch_project(project_id: str) -> Optional[dict[str, Any]]:
    """One project, with the owner's company NAME resolved from tenants."""
    rows = _rows(
        "SELECT p.project_id, p.project_name, p.owner_tenant_id, p.molecule, "
        "       p.status, p.jurisdiction, p.country, p.location, p.created_by, "
        "       p.capex_eur, p.capacity_mtpd, t.company_name AS owner_company_name "
        "FROM projects p LEFT JOIN tenants t ON t.company_id = p.owner_tenant_id "
        "WHERE p.project_id = :pid AND p.is_active",
        {"pid": project_id},
    )
    return rows[0] if rows else None


def list_projects(owner_tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Projects with the owner's company NAME resolved. `owner_tenant_id=None`
    returns all (platform-admin view).

    Only projects NOT in the static registry are of interest to callers
    rendering "runtime" projects, but this deliberately returns everything —
    filtering by provenance is the caller's business, not the store's.
    """
    where = "WHERE p.is_active"
    params: dict[str, Any] = {}
    if owner_tenant_id is not None:
        where += " AND p.owner_tenant_id = :cid"
        params["cid"] = owner_tenant_id
    return _rows(
        "SELECT p.project_id, p.project_name, p.owner_tenant_id, p.molecule, "
        "       p.status, p.jurisdiction, p.country, p.location, p.created_by, "
        "       p.capex_eur, p.capacity_mtpd, t.company_name AS owner_company_name "
        f"FROM projects p LEFT JOIN tenants t ON t.company_id = p.owner_tenant_id {where} "
        "ORDER BY p.project_id",
        params,
    )


def project_ids_owned_by(company_id: str) -> list[str]:
    return [
        r["project_id"]
        for r in _rows(
            "SELECT project_id FROM projects WHERE owner_tenant_id = :cid AND is_active "
            "ORDER BY project_id",
            {"cid": company_id},
        )
    ]


def fetch_context(project_id: str) -> Optional[dict[str, Any]]:
    """Stored project context, or None. Callers fall back to the static seed."""
    rows = _rows(
        "SELECT power_model, phase, financing_model, updated_by, updated_at "
        "FROM project_context WHERE project_id = :pid",
        {"pid": project_id},
    )
    return rows[0] if rows else None


def fetch_context_events(project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return _rows(
        "SELECT field, old_value, new_value, actor, at FROM project_context_events "
        "WHERE project_id = :pid ORDER BY id DESC LIMIT :lim",
        {"pid": project_id, "lim": limit},
    )


def update_context(
    *,
    project_id: str,
    power_model: str,
    phase: str,
    financing_model: str,
    actor: str,
    changes: list[tuple[str, Any, Any]],
) -> str:
    """
    Upsert context and append its audit events in ONE transaction.

    `changes` is (field, old, new) for fields that actually changed. The state
    write and the audit rows must commit together — a context change recorded
    without its audit entry, or vice versa, is exactly the kind of gap the
    append-only events table exists to prevent.

    Returns the `updated_at` timestamp written.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with _engine().begin() as conn:
        conn.execute(text(f"SET LOCAL app.current_company_id = '{PLATFORM_ADMIN}'"))
        conn.execute(text("""
            INSERT INTO project_context (project_id, power_model, phase,
                financing_model, updated_by, updated_at)
            VALUES (:pid, :pm, :ph, :fm, :by, :at)
            ON CONFLICT (project_id) DO UPDATE SET
                power_model = EXCLUDED.power_model,
                phase = EXCLUDED.phase,
                financing_model = EXCLUDED.financing_model,
                updated_by = EXCLUDED.updated_by,
                updated_at = EXCLUDED.updated_at
        """), {"pid": project_id, "pm": power_model, "ph": phase,
               "fm": financing_model, "by": actor, "at": now})
        for field, old_value, new_value in changes:
            conn.execute(text("""
                INSERT INTO project_context_events (project_id, field, old_value,
                    new_value, actor, at)
                VALUES (:pid, :f, :o, :n, :a, :at)
            """), {"pid": project_id, "f": field,
                   "o": None if old_value is None else str(old_value),
                   "n": str(new_value), "a": actor, "at": now})
    return now


def create_project(
    *,
    project_id: str,
    name: str,
    molecule: str,
    location: str,
    country: str,
    capacity_mtpd: float,
    capex_eur: float,
    owner_tenant_id: str,
    power_model: str,
    financing_model: str,
    phase: str,
    created_by: str,
) -> str:
    """
    Create a project and seed its context — ONE transaction, ONE store.

    power_model / financing_model / phase are written to project_context only.
    The old SQLite `projects` table also stored them; that duplication was not
    carried over. `projects.status` holds the lifecycle value.
    """
    with _engine().begin() as conn:
        conn.execute(text(f"SET LOCAL app.current_company_id = '{PLATFORM_ADMIN}'"))
        conn.execute(text("""
            INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule,
                status, jurisdiction, capex_eur, capacity_mtpd, location, country,
                created_by, is_active)
            VALUES (:pid, :name, :tenant, :mol, :status, 'EU', :capex, :cap,
                    :loc, :country, :by, true)
        """), {"pid": project_id, "name": name, "tenant": owner_tenant_id,
               "mol": molecule, "status": phase or "development", "capex": capex_eur,
               "cap": capacity_mtpd, "loc": location, "country": country, "by": created_by})
        conn.execute(text("""
            INSERT INTO project_context (project_id, power_model, phase,
                financing_model, updated_by, updated_at)
            VALUES (:pid, :pm, :ph, :fm, :by, now()::text)
            ON CONFLICT (project_id) DO UPDATE SET
                power_model = EXCLUDED.power_model,
                phase = EXCLUDED.phase,
                financing_model = EXCLUDED.financing_model,
                updated_by = EXCLUDED.updated_by,
                updated_at = EXCLUDED.updated_at
        """), {"pid": project_id, "pm": power_model, "ph": phase,
               "fm": financing_model, "by": created_by})
        conn.execute(text("""
            INSERT INTO project_context_events (project_id, field, old_value,
                new_value, actor, at)
            VALUES (:pid, 'project', NULL, 'created', :by, now()::text)
        """), {"pid": project_id, "by": created_by})
    return project_id
