"""
Domain Authorization — layer 2 of the security doctrine (ADR 2026-07-06).
=========================================================================
Sits between authentication-by-default (route_security.py, layer 1) and the
ABAC middleware (layer 3). Answers one question per WRITE request: is this
user's business function allowed to change data in this business domain?

Design rules:
  - Every /api route prefix MUST map to a domain here. An unmapped route
    fails closed (403) — CI (tests/test_architecture_guardrails.py) verifies
    coverage so this only ever fires for brand-new, unregistered routers.
  - Reads (GET/HEAD/OPTIONS) pass — fine-grained read visibility is ABAC's
    and the permission engine's job. This layer guards writes.
  - Platform admins and platform service tokens pass.
  - Policies are deliberately coarse (business_function / service_type).
    Fine-grained per-project rules stay in entitlements + ABAC. Tightening a
    domain is a one-line edit to its DomainPolicy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status

from app.core.route_security import is_public

logger = logging.getLogger("gex.domain_authz")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class DomainPolicy:
    name: str
    description: str
    # business functions allowed to WRITE; None = any authenticated user
    write_functions: frozenset[str] | None = None
    # service_types additionally allowed to WRITE (BANK, DFI, INSURER, ...)
    write_service_types: frozenset[str] = field(default_factory=frozenset)


DOMAINS: dict[str, DomainPolicy] = {
    "finance": DomainPolicy(
        "finance",
        "Capital structuring, instruments, pricing, settlements, trading",
        write_functions=frozenset({"FINANCE_TREASURY", "EXECUTIVE"}),
        write_service_types=frozenset({"BANK", "DFI", "INSURER"}),
    ),
    "projects": DomainPolicy(
        "projects",
        "Project lifecycle, development packages, plant configuration",
        write_functions=frozenset({"EXECUTIVE", "ENGINEERING", "COMMERCIAL"}),
    ),
    "marketplace": DomainPolicy(
        "marketplace",
        "Listings, matching, demand, contracts, trader workflows",
        write_functions=frozenset({"COMMERCIAL", "EXECUTIVE"}),
    ),
    "sustainability": DomainPolicy(
        "sustainability",
        "Carbon attribution, mass balance, additionality, fuel lineage",
        write_functions=frozenset({"ENGINEERING", "COMMERCIAL", "EXECUTIVE"}),
    ),
    "verification": DomainPolicy(
        "verification",
        "Evidence, bankability gates, TEA runs, data rooms — assurance surface",
        write_functions=frozenset({"ENGINEERING", "EXECUTIVE", "THIRD_PARTY"}),
        write_service_types=frozenset({"ENGINEER", "AUDITOR", "BANK", "DFI", "INSURER"}),
    ),
    "governance": DomainPolicy(
        "governance",
        "CISO, audit, approvals, entitlements, adversarial reviews",
        write_functions=frozenset({"EXECUTIVE"}),
    ),
    "intelligence": DomainPolicy(
        "intelligence",
        "Analytics, decision twin, recommendations — derived data, low blast radius",
        write_functions=None,
    ),
    "platform": DomainPolicy(
        "platform",
        "Auth self-service, onboarding, events, comms, workflow plumbing",
        write_functions=None,
    ),
}


# Longest-prefix wins. Every /api/v1/<segment> prefix must appear here —
# CI fails if a registered route has no domain.
DOMAIN_PREFIXES: dict[str, str] = {
    # finance
    "/api/v1/finance": "finance",
    "/api/v1/finance-model": "finance",
    "/api/v1/capital-bridge": "finance",
    "/api/v1/drawdown-schedule": "finance",
    "/api/v1/spend-wave": "finance",
    "/api/v1/instruments": "finance",
    "/api/v1/sovereign-instruments": "finance",
    "/api/v1/risk-pricing": "finance",
    "/api/v1/pricing": "finance",
    "/api/v1/structuring": "finance",
    "/api/v1/commitments": "finance",
    "/api/v1/terms": "finance",
    "/api/v1/settlements": "finance",
    "/api/v1/trading-book": "finance",
    "/api/v1/account": "platform",
    "/api/v1/billing": "platform",
    # Producer/offtaker discovery. Domain authorization decides who may WRITE here;
    # per-interest confidentiality is decided separately in app.core.open_interest,
    # which a platform admin does NOT bypass.
    "/api/v1/open-interest": "marketplace",
    "/api/v1/tokens": "finance",
    "/api/v1/ic-pack": "finance",
    "/api/v1/dfi-criteria": "finance",
    # projects
    "/api/v1/projects": "projects",
    "/api/v1/packages": "projects",
    "/api/v1/plant-builder": "projects",
    "/api/v1/plant-data": "projects",
    "/api/v1/capacities": "projects",
    "/api/v1/project-truth": "projects",
    "/api/v1/project-ratings": "projects",
    "/api/v1/project-activity": "projects",
    "/api/v1/pre-cod-metrics": "projects",
    "/api/v1/performance": "projects",
    "/api/v1/timeline": "projects",
    "/api/v1/deal-killers": "projects",
    # marketplace
    "/api/v1/marketplace": "marketplace",
    "/api/v1/matching": "marketplace",
    "/api/v1/demand": "marketplace",
    "/api/v1/contracts": "marketplace",
    "/api/v1/trader": "marketplace",
    # sustainability
    "/api/v1/carbon-attribution": "sustainability",
    "/api/v1/mass-balance": "sustainability",
    "/api/v1/additionality": "sustainability",
    "/api/v1/lineage": "sustainability",
    "/api/v1/fuels": "sustainability",
    # verification
    "/api/v1/bankability": "verification",
    "/api/v1/evidence": "verification",
    "/api/v1/verification": "verification",
    "/api/v1/gates": "verification",
    "/api/v1/data-room": "verification",
    "/api/v1/tea": "verification",
    # governance
    "/api/v1/ciso": "governance",
    "/api/v1/audit": "governance",
    "/api/v1/approvals": "governance",
    "/api/v1/entitlements": "governance",
    "/api/v1/adversarial-reviews": "governance",
    "/api/v1/reports": "governance",
    # intelligence
    "/api/v1/decision-twin": "intelligence",
    "/api/v1/nba": "intelligence",
    "/api/v1/adjacency": "intelligence",
    "/api/v1/corpus": "intelligence",
    # platform
    "/api/v1/auth": "platform",
    "/api/v1/onboarding": "platform",
    "/api/v1/events": "platform",
    "/api/v1/comms": "platform",
    "/api/v1/task-flow": "platform",
    "/api/v1/workflow": "platform",
    "/api/v1/vocabulary": "platform",
}


def domain_for_path(path: str) -> str | None:
    best = None
    for prefix, domain in DOMAIN_PREFIXES.items():
        if (path == prefix or path.startswith(prefix + "/")) and (
            best is None or len(prefix) > len(best[0])
        ):
            best = (prefix, domain)
    return best[1] if best else None


def check_domain_access(
    payload: dict, path: str, method: str
) -> tuple[bool, str | None, str]:
    """
    Pure policy decision: (allowed, domain, reason). No I/O — unit-testable.
    """
    if method in SAFE_METHODS:
        return True, None, "read — visibility handled by ABAC/permission engine"
    if not path.startswith("/api/") or is_public(path):
        return True, None, "public or non-API path"

    domain = domain_for_path(path)
    if domain is None:
        return False, None, (
            "route is not mapped to a business domain — register it in "
            "app/core/domain_authorization.py DOMAIN_PREFIXES"
        )
    policy = DOMAINS[domain]

    if payload.get("is_platform_admin"):
        return True, domain, "platform admin"
    if payload.get("session_tier") == "service" or payload.get("business_function") == "SERVICE":
        return True, domain, "platform service token"
    if policy.write_functions is None:
        return True, domain, "domain open to all authenticated users"

    fn = payload.get("business_function")
    st = payload.get("service_type")
    if fn in policy.write_functions:
        return True, domain, f"business function {fn} authorized"
    if st and st in policy.write_service_types:
        return True, domain, f"service type {st} authorized"

    return False, domain, (
        f"business function {fn!r} / service type {st!r} may not write to the "
        f"{domain} domain (allowed functions: {sorted(policy.write_functions)}"
        + (f", service types: {sorted(policy.write_service_types)}" if policy.write_service_types else "")
        + ")"
    )


async def enforce_domain_authorization(request: Request) -> None:
    """
    Global dependency, runs AFTER require_authenticated (which populates
    request.state.user_payload). Guards writes per business domain.
    """
    if request.method in SAFE_METHODS:
        return
    payload = getattr(request.state, "user_payload", None)
    if payload is None:
        # Public route (require_authenticated let it through without identity)
        # — nothing to authorize at domain level.
        return

    allowed, domain, reason = check_domain_access(payload, request.url.path, request.method)
    if not allowed:
        logger.warning(
            "DOMAIN DENY: user=%s domain=%s path=%s reason=%s",
            payload.get("sub") or payload.get("user_id"), domain, request.url.path, reason,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "domain_authorization_denied", "domain": domain, "reason": reason},
        )
