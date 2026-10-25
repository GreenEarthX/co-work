"""
Canonical project/company registry for security and access scope.

This file gives the backend a stable source of truth for:
- project ownership
- stakeholder company scope
- mandated lender / insurer lists
- project jurisdiction

It mirrors the frontend customer project registry closely enough to make
JWT scope and ABAC enforcement project-aware.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def company_slug(name: str | None) -> str:
    # Callers pass payload.get("company_name", "") — which yields None when the
    # key is PRESENT and null (service identities), not the "" default. The
    # trailing `or "unknown_company"` already signals this is meant to tolerate
    # junk input; None was the one case it crashed on.
    if not name:
        return "unknown_company"
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return slug or "unknown_company"


# Retired project ids live in PostgreSQL (project_id_alias, alembic 069); the
# PROJECT_ID_ALIASES dictionary that stood here was moved there on 2026-10-25.


@dataclass(frozen=True)
class ProjectAccessProfile:
    project_id: str
    project_name: str
    owner_company_name: str
    associated_company_names: tuple[str, ...]
    jurisdiction: str
    mandated_lender_names: tuple[str, ...] = ()
    mandated_insurer_names: tuple[str, ...] = ()

    @property
    def owner_company_id(self) -> str:
        return company_slug(self.owner_company_name)

    @property
    def stakeholder_company_ids(self) -> set[str]:
        return {
            self.owner_company_id,
            *(company_slug(name) for name in self.associated_company_names),
        }

    @property
    def shared_with_company_ids(self) -> set[str]:
        return {company_slug(name) for name in self.associated_company_names}

    @property
    def mandated_lender_ids(self) -> set[str]:
        return {company_slug(name) for name in self.mandated_lender_names}

    @property
    def mandated_insurer_ids(self) -> set[str]:
        return {company_slug(name) for name in self.mandated_insurer_names}


# Project access lives in PostgreSQL only (projects, tenants, project_access).
# The PROJECT_ACCESS_PROFILES dictionary that stood here was moved by
# scripts/move_project_registry_20261025.py and deleted (JML, 2026-10-25).


# ── Physical context — power model + lifecycle phase per project ────────────
# Read by the bankability engine for power-model-aware gate scoping and
# phase-aware severity. Source: the project_context table (migration 033),
# written by PATCH /api/v1/projects/{id}/context. The PROJECT_PHYSICAL seed
# dictionary that stood here was moved into that table (scripts/
# move_project_profiles_20261025.py) and deleted (JML, 2026-10-25).

@dataclass(frozen=True)
class ProjectPhysicalContext:
    power_model: str               # OFF_GRID_BTM | GRID_CONNECTED | HYBRID
    phase: str                     # development | construction | commissioning | operating
    financing_model: str = "PROJECT_FINANCE"  # PROJECT_FINANCE | BALANCE_SHEET


def get_project_physical(project_id: str | None) -> ProjectPhysicalContext | None:
    return get_effective_context(project_id)


# ── Effective context: the project_context table ─────────────────────────────
# project_context rows are written by PATCH /api/v1/projects/{id}/context
# (audited, owner-EXEC/admin only) and by project creation.

import os as _os
import sqlite3 as _sqlite3
from app.core.config import settings

_DB_PATH = settings.SQLITE_DB_PATH

VALID_POWER_MODELS = ("OFF_GRID_BTM", "GRID_CONNECTED", "HYBRID")
VALID_PHASES = ("development", "construction", "commissioning", "operating")
VALID_FINANCING_MODELS = ("PROJECT_FINANCE", "BALANCE_SHEET")


def ensure_context_tables(conn: "_sqlite3.Connection") -> None:
    """
    RETIRED 2026-08-07 — explicit no-op, deliberately not deleted.

    project_context and project_context_events are canonical in PostgreSQL
    (migration 033). This used to CREATE TABLE IF NOT EXISTS the SQLite copies;
    because IF NOT EXISTS is silent, any surviving caller would recreate them
    and split context truth again — which is exactly what happened between the
    033 migration and this change, with create_project writing Postgres while
    PATCH /context wrote SQLite.
    """
    return None


def get_effective_context(project_id: str | None) -> ProjectPhysicalContext | None:
    """
    The stored context; None when the project has none (no in-code fallback).

    Reads the CANONICAL PostgreSQL project_context (migration 033), which moved
    there with `projects` so that create_project stays atomic. The SQLite copy
    is retired — while both existed, this endpoint and create_project were
    writing different stores.
    """
    from app.core.projects_store import fetch_context

    normalized = normalize_project_id(project_id)
    if not normalized:
        return None
    row = fetch_context(normalized)
    if row:
        return ProjectPhysicalContext(
            row["power_model"], row["phase"], row["financing_model"]
        )
    return None


def normalize_project_id(project_id: str | None) -> str | None:
    if not project_id:
        return project_id
    from app.core.projects_store import resolve_alias

    return resolve_alias(project_id) or project_id


# ── Project registry: PostgreSQL only ────────────────────────────────────────
# Every project — seeded or created through POST /api/v1/projects — lives in
# the `projects` table, with access in `project_access` and context in
# `project_context`. Since 2026-10-25 there is no seed dictionary in code.

def ensure_project_table(conn: "_sqlite3.Connection") -> None:
    """
    RETIRED 2026-08-07 — kept as an explicit no-op, not deleted.

    This used to CREATE TABLE IF NOT EXISTS a SQLite `projects` table whose
    shape collided with the canonical PostgreSQL one (migration 020): company
    NAME instead of a tenant FK, no RLS. The ruling was that the PostgreSQL
    shape wins.

    It is a no-op rather than a deletion because IF NOT EXISTS is silent — any
    caller still invoking it would quietly recreate the second table and
    re-open the collision. Failing to create is the safe behaviour; the
    canonical store is app/core/projects_store.py.
    """
    return None


# Roles that make a company a project stakeholder. REVIEWER is deliberately
# absent: an appointed reviewer's access is gate-scoped (JML, 2026-10-21) and is
# enforced by RLS and the reviewer rules, not by stakeholder visibility.
_STAKEHOLDER_ROLES = ("STAKEHOLDER", "MANDATED_LENDER", "MANDATED_INSURER")


def _build_profile(row: dict, access: list[dict]) -> ProjectAccessProfile:
    """
    jurisdiction is the row's `country` ("DE"), not its `jurisdiction` ("EU"):
    downstream ABAC compares country values, and the dictionary this replaced
    carried countries (moved to the country column on 2026-10-25).
    """
    def names(*roles):
        return tuple(a["company_name"] for a in access if a["access_role"] in roles)

    return ProjectAccessProfile(
        project_id=row["project_id"],
        project_name=row["project_name"],
        owner_company_name=row["owner_company_name"],
        associated_company_names=names(*_STAKEHOLDER_ROLES),
        jurisdiction=row["country"] or "",
        mandated_lender_names=names("MANDATED_LENDER"),
        mandated_insurer_names=names("MANDATED_INSURER"),
    )


def get_project_profile(project_id: str | None) -> ProjectAccessProfile | None:
    """The project's access profile, from PostgreSQL (projects, tenants, project_access)."""
    from app.core.projects_store import fetch_project, fetch_project_access

    normalized = normalize_project_id(project_id)
    if not normalized:
        return None
    row = fetch_project(normalized)
    if not row:
        return None
    return _build_profile(row, fetch_project_access(normalized))


def all_project_profiles() -> list[ProjectAccessProfile]:
    """Every active project's access profile, in two queries."""
    from app.core.projects_store import fetch_project_access, list_projects

    access: dict[str, list[dict]] = {}
    for a in fetch_project_access():
        access.setdefault(a["project_id"], []).append(a)
    return [_build_profile(r, access.get(r["project_id"], [])) for r in list_projects()]


def visible_project_ids_for_company(company_name: str) -> list[str]:
    company_id = company_slug(company_name)
    return [p.project_id for p in all_project_profiles() if company_id in p.stakeholder_company_ids]


def _gen_project_id(name: str) -> str:
    import secrets
    base = company_slug(name)[:32] or "project"
    return f"proj_{base}_{secrets.token_hex(3)}"


def create_project(
    *,
    name: str,
    molecule: str,
    location: str,
    country: str,
    capacity_mtpd: float,
    capex_eur: float,
    owner_company_name: str,
    power_model: str,
    financing_model: str,
    phase: str,
    created_by: str,
) -> str:
    """
    Create a runtime project and seed its physical/financing context in one
    transaction. Returns the generated project_id.

    Collision resolved 2026-08-07: this writes the CANONICAL PostgreSQL
    `projects` table (migration 020/033), not the retired SQLite one. The
    owner is resolved to a tenant id — the old table stored a company *name*
    with no FK, so an owner could be a string that matched nothing.

    project_context and project_context_events moved with it (033) precisely
    so this stays atomic: all three writes are one transaction in one store.
    """
    from app.core.projects_store import create_project as _create

    project_id = _gen_project_id(name)
    return _create(
        project_id=project_id,
        name=name,
        molecule=molecule,
        location=location,
        country=country,
        capacity_mtpd=capacity_mtpd,
        capex_eur=capex_eur,
        owner_tenant_id=company_slug(owner_company_name),
        power_model=power_model,
        financing_model=financing_model,
        phase=phase,
        created_by=created_by,
    )

