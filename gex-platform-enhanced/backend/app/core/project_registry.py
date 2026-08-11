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


PROJECT_ID_ALIASES = {
    "proj_le_havre_eng": "proj_lehavre_eng",
    "proj_helios_emethanol": "proj_sansebastian_emethanol",
}


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


PROJECT_ACCESS_PROFILES: dict[str, ProjectAccessProfile] = {
    # ── ETFuels SA portfolio ─────────────────────────────────────────────
    "proj_etf_pecos1": ProjectAccessProfile(
        project_id="proj_etf_pecos1",
        project_name="ETFuels Pecos I",
        owner_company_name="ETFuels SA",
        associated_company_names=("ING Capital", "BNP Paribas CIB", "Maersk Decarbonization"),
        jurisdiction="US",
    ),
    "etfuels_us_tx_rattlesnake_gap": ProjectAccessProfile(
        project_id="etfuels_us_tx_rattlesnake_gap",
        project_name="Rattlesnake Gap",
        owner_company_name="ETFuels SA",
        associated_company_names=(),
        jurisdiction="US",
    ),
    "etfuels_fi_ranua_naataaapa": ProjectAccessProfile(
        project_id="etfuels_fi_ranua_naataaapa",
        project_name="Ranua Näätäaapa e-Methanol",
        owner_company_name="ETFuels SA",
        associated_company_names=(),
        jurisdiction="FI",
    ),
    "etfuels_uk_skyfuel_teesside": ProjectAccessProfile(
        project_id="etfuels_uk_skyfuel_teesside",
        project_name="Project SkyFuel Teesside",
        owner_company_name="ETFuels SA",
        associated_company_names=(),
        jurisdiction="GB",
    ),
    # ── Other companies ──────────────────────────────────────────────────
    "proj_rheinwerk_prosumer": ProjectAccessProfile(
        project_id="proj_rheinwerk_prosumer",
        project_name="RheinWerk Duisburg H₂ (Prosumer)",
        owner_company_name="RheinWerk Industries AG",
        associated_company_names=(),
        jurisdiction="DE",
    ),
    "proj_bremen_h2": ProjectAccessProfile(
        project_id="proj_bremen_h2",
        project_name="Bremen Green Hydrogen Plant",
        owner_company_name="HeliosNord GmbH",
        associated_company_names=("Allianz", "Siemens Energy"),
        jurisdiction="DE",
        mandated_insurer_names=("Allianz",),
    ),
    "proj_rotterdam_nh3": ProjectAccessProfile(
        project_id="proj_rotterdam_nh3",
        project_name="Rotterdam Green Ammonia Terminal",
        owner_company_name="RotterdamGreenFuels BV",
        associated_company_names=("Allianz", "Zurich Versicherung AG"),
        jurisdiction="NL",
        mandated_insurer_names=("Allianz", "Zurich Versicherung AG"),
    ),
    "proj_sansebastian_emethanol": ProjectAccessProfile(
        project_id="proj_sansebastian_emethanol",
        project_name="Project Helios e-Methanol",
        owner_company_name="Helios Energia SL",
        associated_company_names=("Allianz",),
        jurisdiction="ES",
        mandated_insurer_names=("Allianz",),
    ),
    "proj_wales_saf": ProjectAccessProfile(
        project_id="proj_wales_saf",
        project_name="Celtic Green SAF Complex",
        owner_company_name="Celtic Green Fuels Ltd",
        associated_company_names=("Zurich Versicherung AG",),
        jurisdiction="GB",
        mandated_insurer_names=("Zurich Versicherung AG",),
    ),
    "proj_lehavre_eng": ProjectAccessProfile(
        project_id="proj_lehavre_eng",
        project_name="Le Havre e-Gas Hub",
        owner_company_name="Normandie Hydrogene SA",
        associated_company_names=("Allianz", "Zurich Versicherung AG"),
        jurisdiction="FR",
        mandated_insurer_names=("Allianz", "Zurich Versicherung AG"),
    ),
    "proj_hamburgone_emethanol": ProjectAccessProfile(
        project_id="proj_hamburgone_emethanol",
        project_name="HamburgOne e-Methanol Plant",
        owner_company_name="HamburgOne.com",
        associated_company_names=("NordLB", "BremenThree AG", "Allianz", "Siemens Energy"),
        jurisdiction="DE",
        mandated_lender_names=("NordLB",),
        mandated_insurer_names=("Allianz",),
    ),
    "proj_madrid2_sansebastian": ProjectAccessProfile(
        project_id="proj_madrid2_sansebastian",
        project_name="Madrid2 San-Sebastian e-Methanol",
        owner_company_name="Madrid2.com",
        associated_company_names=("ABN-AMRO", "RotterdamOfftake4 AG", "Zurich Versicherung AG"),
        jurisdiction="ES",
        mandated_lender_names=("ABN-AMRO",),
        mandated_insurer_names=("Zurich Versicherung AG",),
    ),
}


# ── Physical context — power model + lifecycle phase per project ────────────
# Server-side source for the bankability engine's power-model-aware gate
# scoping and phase-aware severity escalation. The frontend static seeds in
# customerProjects.ts mirror this for dev fallback; THIS is what the engine
# actually receives. Belongs in the project store once projects are
# server-persisted.

@dataclass(frozen=True)
class ProjectPhysicalContext:
    power_model: str               # OFF_GRID_BTM | GRID_CONNECTED | HYBRID
    phase: str                     # development | construction | commissioning | operating
    financing_model: str = "PROJECT_FINANCE"  # PROJECT_FINANCE | BALANCE_SHEET


# SEED ONLY. The runtime source of truth is the project_context DB table
# (see routes_project_context.py) — these values initialise it and are
# superseded by any PATCH. Editing this dict is NOT how projects are
# onboarded or updated; the API is.
PROJECT_PHYSICAL: dict[str, ProjectPhysicalContext] = {
    # ETFuels portfolio — off-grid behind-the-meter, SPV project finance
    "proj_etf_pecos1":                ProjectPhysicalContext("OFF_GRID_BTM", "development"),
    "etfuels_us_tx_rattlesnake_gap":  ProjectPhysicalContext("OFF_GRID_BTM", "development"),
    "etfuels_fi_ranua_naataaapa":     ProjectPhysicalContext("OFF_GRID_BTM", "development"),
    "etfuels_uk_skyfuel_teesside":    ProjectPhysicalContext("OFF_GRID_BTM", "development"),
    # Grid-connected SPV projects
    "proj_bremen_h2":                 ProjectPhysicalContext("GRID_CONNECTED", "construction"),
    "proj_hamburgone_emethanol":      ProjectPhysicalContext("GRID_CONNECTED", "development"),
    # Prosumer demo — hybrid power, corporate balance sheet, internal offtake
    "proj_rheinwerk_prosumer":        ProjectPhysicalContext("HYBRID", "development", "BALANCE_SHEET"),
}


def get_project_physical(project_id: str | None) -> ProjectPhysicalContext | None:
    normalized = normalize_project_id(project_id)
    if not normalized:
        return None
    return PROJECT_PHYSICAL.get(normalized)


# ── Effective context: DB override > seed ────────────────────────────────────
# project_context rows are written by PATCH /api/v1/projects/{id}/context
# (audited, owner-EXEC/admin only). This is how project context is updated in
# operation — code-edits to PROJECT_PHYSICAL are seed/dev only.

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
    Stored context wins; the in-code seed is the fallback.

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
    return PROJECT_PHYSICAL.get(normalized)


def normalize_project_id(project_id: str | None) -> str | None:
    if not project_id:
        return project_id
    return PROJECT_ID_ALIASES.get(project_id, project_id)


# ── Runtime project registry (the on-ramp) ───────────────────────────────────
# The static PROJECT_ACCESS_PROFILES / PROJECT_PHYSICAL dicts are SEED/demo
# data. New projects are created at runtime via POST /api/v1/projects and live
# in the `projects` table. get_project_profile() consults the seed first, then
# the runtime table — so a UI-created project is a first-class bridge citizen
# (ABAC, context, gates, packages) without a code edit. This is the fix for the
# "master data lives in a TypeScript file" gap.

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


def _runtime_profile(project_id: str) -> ProjectAccessProfile | None:
    """
    Runtime project lookup against the CANONICAL projects table.

    Collision resolved 2026-08-07: the PostgreSQL shape wins (migration 033).
    There is no longer a second `projects` table in SQLite with its own shape.

    NOTE on jurisdiction: this returns `country` ("DE"), not the row's
    `jurisdiction` ("EU"). The pre-migration code did the same — the two were
    conflated — and downstream ABAC compares against country values. Changing
    it here would silently alter authorization, so the behaviour is preserved
    deliberately and the columns are now separate so it CAN be untangled.
    """
    from app.core.projects_store import fetch_project

    row = fetch_project(project_id)
    if not row:
        return None
    return ProjectAccessProfile(
        project_id=project_id,
        project_name=row["project_name"],
        owner_company_name=row["owner_company_name"],
        associated_company_names=(),
        jurisdiction=row["country"] or "",
    )


def get_project_profile(project_id: str | None) -> ProjectAccessProfile | None:
    normalized = normalize_project_id(project_id)
    if not normalized:
        return None
    return PROJECT_ACCESS_PROFILES.get(normalized) or _runtime_profile(normalized)


def visible_project_ids_for_company(company_name: str) -> list[str]:
    company_id = company_slug(company_name)
    visible: list[str] = []
    for project_id, profile in PROJECT_ACCESS_PROFILES.items():
        if company_id in profile.stakeholder_company_ids:
            visible.append(project_id)
    # Runtime-created projects owned by this company, from the canonical store.
    from app.core.projects_store import project_ids_owned_by

    for pid in project_ids_owned_by(company_id):
        if pid not in visible:
            visible.append(pid)
    return visible


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

