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


def company_slug(name: str) -> str:
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


def normalize_project_id(project_id: str | None) -> str | None:
    if not project_id:
        return project_id
    return PROJECT_ID_ALIASES.get(project_id, project_id)


def get_project_profile(project_id: str | None) -> ProjectAccessProfile | None:
    normalized = normalize_project_id(project_id)
    if not normalized:
        return None
    return PROJECT_ACCESS_PROFILES.get(normalized)


def visible_project_ids_for_company(company_name: str) -> list[str]:
    company_id = company_slug(company_name)
    visible: list[str] = []
    for project_id, profile in PROJECT_ACCESS_PROFILES.items():
        if company_id in profile.stakeholder_company_ids:
            visible.append(project_id)
    return visible

