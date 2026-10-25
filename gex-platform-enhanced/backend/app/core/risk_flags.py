"""
Structured project risk flags — server-authoritative registry + ABAC policy.

Replaces flat risk_alerts strings with auditable resources:
  id · claim · severity · confidence · category · owner_function
  · classification · source_ids · status

Design split (deliberate):
  - owner_function  = WHO WORKS the risk (task assignment)
  - classification  = WHO MAY SEE the risk (ABAC visibility)
These are never the same field: a related-party offtake risk is owned by
FINANCE but exists to warn the lenders (associated companies), so visibility
must come from classification × stakeholding, not from ownership.

Classification ladder:
  PUBLIC       → anyone who can see the project
  STAKEHOLDER  → owner company + associated companies
  CONFIDENTIAL → owner company only
  RESTRICTED   → owner company EXECUTIVE / FINANCE_TREASURY only
Platform admins see everything. Responses never include hidden-flag counts —
"3 flags (1 hidden)" would leak that a hidden risk exists.

The frontend keeps a static copy in customerProjects.ts as dev fallback only;
this registry is the enforced source (frontend is NEVER trusted for data
protection).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from app.core.project_registry import company_slug, get_project_profile

CLASSIFICATIONS = ("PUBLIC", "STAKEHOLDER", "CONFIDENTIAL", "RESTRICTED")


@dataclass(frozen=True)
class RiskFlag:
    id: str
    project_id: str
    claim: str
    severity: str           # low | medium | high | critical
    confidence: str         # low | medium | high
    category: str           # capacity_claim | certification | offtake | financing
                            # | site_permits | insurance | supply_chain | policy
    owner_function: str     # EXECUTIVE | FINANCE_TREASURY | COMMERCIAL
                            # | ENGINEERING | OPERATIONS | COMPLIANCE_LEGAL
    classification: str     # PUBLIC | STAKEHOLDER | CONFIDENTIAL | RESTRICTED
    source_ids: tuple[str, ...]
    status: str = "OPEN"    # OPEN | ACKNOWLEDGED | WAIVED | RESOLVED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_ids"] = list(self.source_ids)
        return d


def _flags(project_id: str) -> list[RiskFlag]:
    """The project's flags from PostgreSQL (project_risk_flag, alembic 068).

    Read as a bootstrap (PLATFORM_ADMIN, through projects_store): the
    classification filter below is what decides what a caller sees. The
    RISK_FLAGS dictionary that stood here was moved into that table by
    scripts/move_project_profiles_20261025.py and deleted (JML, 2026-10-25).
    """
    from app.core.projects_store import _rows

    rows = _rows("SELECT id, project_id, claim, severity, confidence, category, owner_function, "
                 "classification, source_ids, status FROM project_risk_flag WHERE project_id = :pid "
                 "ORDER BY seq, id", {"pid": project_id})
    return [RiskFlag(**{**r, "source_ids": tuple(r["source_ids"] or ())}) for r in rows]



def visible_risk_flags(project_id: str, payload: dict[str, Any]) -> list[RiskFlag] | None:
    """
    ABAC filter: returns the flags this caller may see, or None when the
    caller has no access to the project at all (404, not an empty list —
    an empty list would leak that the project exists).
    """
    profile = get_project_profile(project_id)
    if profile is None:
        return None

    is_admin = bool(payload.get("is_platform_admin"))
    company_id = company_slug(payload.get("company_name", ""))
    is_owner = company_id == profile.owner_company_id
    is_stakeholder = company_id in profile.stakeholder_company_ids

    if not (is_admin or is_stakeholder):
        return None

    business_function = payload.get("business_function", "")

    def can_see(flag: RiskFlag) -> bool:
        if is_admin:
            return True
        if flag.classification == "PUBLIC":
            return True
        if flag.classification == "STAKEHOLDER":
            return is_stakeholder
        if flag.classification == "CONFIDENTIAL":
            return is_owner
        if flag.classification == "RESTRICTED":
            return is_owner and business_function in ("EXECUTIVE", "FINANCE_TREASURY")
        return False

    return [f for f in _flags(project_id) if can_see(f)]
