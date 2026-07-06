"""
GEX Platform — Permission Engine API (CISO Workspace)
=======================================================
Endpoints for managing the 165-permission × 30-profile matrix.

The CISO can:
  • View all role profiles and their permission counts
  • Query effective permissions for any user
  • Simulate permission checks with context
  • Grant/revoke individual permissions (per-user overrides)
  • Diff two profiles side-by-side
  • Export the full matrix for audit
  • View capability impact analysis
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.permission_engine import (
    PERMISSIONS, ROLE_PROFILES, CAPABILITY_GRANTS, CONTEXT_CONDITIONS,
    get_all_profiles, get_profile_permissions, get_full_matrix,
    get_effective_permissions, check_permission, diff_profiles,
    get_capability_impact, set_user_override, clear_user_override,
    get_user_overrides, resolve_profile_key,
)

router = APIRouter(prefix="/permissions", tags=["permissions"])


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────

class PermCheckRequest(BaseModel):
    perm_string: str
    company_type: str
    business_function: str
    service_type: Optional[str] = None
    capabilities: Optional[list[str]] = None
    user_id: Optional[str] = None
    context: Optional[dict] = None


class OverrideRequest(BaseModel):
    user_id: str
    perm_string: str
    granted: bool  # True = grant, False = revoke


class EffectivePermsRequest(BaseModel):
    company_type: str
    business_function: str
    service_type: Optional[str] = None
    capabilities: Optional[list[str]] = None
    user_id: Optional[str] = None


class DiffRequest(BaseModel):
    profile_a: str
    profile_b: str


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/registry")
async def get_permission_registry():
    """Return all 165 registered permissions with metadata."""
    return {
        "total": len(PERMISSIONS),
        "permissions": [
            {
                "perm_id": p.perm_id,
                "perm_string": p.perm_string,
                "module": p.module,
                "sub_service": p.sub_service,
                "resource": p.resource,
                "action": p.action,
                "description": p.description,
                "access_tier": p.access_tier.value,
                "has_conditions": p.perm_string in CONTEXT_CONDITIONS,
                "conditions": CONTEXT_CONDITIONS.get(p.perm_string, []),
            }
            for p in sorted(PERMISSIONS.values(), key=lambda x: x.perm_id)
        ],
    }


@router.get("/profiles")
async def list_profiles():
    """Return all role profiles with permission counts."""
    profiles = get_all_profiles()
    return {
        "total_profiles": len(profiles),
        "total_permissions": len(PERMISSIONS),
        "profiles": [
            {"profile_key": k, "permission_count": v}
            for k, v in profiles.items()
        ],
    }


@router.get("/profiles/{profile_key}")
async def get_profile_detail(profile_key: str):
    """Return all permissions for a specific profile."""
    if profile_key not in ROLE_PROFILES:
        raise HTTPException(404, f"Profile '{profile_key}' not found")
    perms = get_profile_permissions(profile_key)
    return {
        "profile_key": profile_key,
        "permission_count": len(perms),
        "permissions": perms,
    }


@router.post("/effective")
async def compute_effective_permissions(req: EffectivePermsRequest):
    """Compute effective permissions for a user (profile + capabilities + overrides)."""
    profile_key = resolve_profile_key(
        req.company_type, req.business_function, req.service_type
    )
    perms = get_effective_permissions(
        req.company_type, req.business_function, req.service_type,
        req.capabilities, req.user_id,
    )
    # Group by module
    by_module: dict[str, list[str]] = {}
    for ps in sorted(perms):
        mod = ps.split(".")[0]
        by_module.setdefault(mod, []).append(ps)

    overrides = get_user_overrides(req.user_id) if req.user_id else {"grants": set(), "revocations": set()}

    return {
        "profile_key": profile_key,
        "total_permissions": len(perms),
        "user_id": req.user_id,
        "overrides_applied": {
            "grants": sorted(overrides["grants"]),
            "revocations": sorted(overrides["revocations"]),
        },
        "by_module": {mod: {"count": len(ps), "permissions": ps} for mod, ps in by_module.items()},
    }


@router.post("/check")
async def check_single_permission(req: PermCheckRequest):
    """Check if a user has a specific permission (with context)."""
    result = check_permission(
        req.perm_string, req.company_type, req.business_function,
        req.service_type, req.capabilities, req.user_id, req.context,
    )
    return {
        "allowed": result.allowed,
        "perm_string": result.perm_string,
        "reason": result.reason,
        "profile_key": result.profile_key,
        "conditions_evaluated": result.conditions_evaluated,
        "override_applied": result.override_applied,
    }


@router.post("/override")
async def apply_override(req: OverrideRequest):
    """CISO: Grant or revoke a specific permission for a user."""
    if req.perm_string not in PERMISSIONS:
        raise HTTPException(400, f"Unknown permission: {req.perm_string}")
    set_user_override(req.user_id, req.perm_string, req.granted)
    action = "granted" if req.granted else "revoked"
    return {
        "status": "ok",
        "message": f"Permission '{req.perm_string}' {action} for user '{req.user_id}'",
        "user_id": req.user_id,
        "perm_string": req.perm_string,
        "granted": req.granted,
    }


@router.delete("/override/{user_id}/{perm_string}")
async def remove_override(user_id: str, perm_string: str):
    """Remove override — revert to profile default."""
    clear_user_override(user_id, perm_string)
    return {
        "status": "ok",
        "message": f"Override removed for '{perm_string}' on user '{user_id}'",
    }


@router.get("/overrides/{user_id}")
async def list_user_overrides(user_id: str):
    """List all overrides for a user."""
    overrides = get_user_overrides(user_id)
    return {
        "user_id": user_id,
        "grants": sorted(overrides["grants"]),
        "revocations": sorted(overrides["revocations"]),
    }


@router.post("/diff")
async def compare_profiles(req: DiffRequest):
    """Compare two profiles — shows only-in-A, only-in-B, shared."""
    for pk in [req.profile_a, req.profile_b]:
        if pk not in ROLE_PROFILES:
            raise HTTPException(404, f"Profile '{pk}' not found")
    return diff_profiles(req.profile_a, req.profile_b)


@router.get("/matrix")
async def get_matrix():
    """Return the full permission matrix (all profiles × all permissions)."""
    return get_full_matrix()


@router.get("/capabilities")
async def list_capabilities():
    """Return all capabilities and their permission impact."""
    return {
        cap: {
            "permission_count": len(perms),
            "permissions": sorted(perms),
        }
        for cap, perms in sorted(CAPABILITY_GRANTS.items())
    }


@router.get("/capabilities/{capability}")
async def get_capability_detail(capability: str):
    """Return permissions granted by a specific capability."""
    capability = capability.upper()
    if capability not in CAPABILITY_GRANTS:
        raise HTTPException(404, f"Capability '{capability}' not found")
    perms = get_capability_impact(capability)
    return {
        "capability": capability,
        "permission_count": len(perms),
        "permissions": perms,
    }


@router.get("/conditions")
async def list_context_conditions():
    """Return all permissions that have context conditions."""
    return {
        "total": len(CONTEXT_CONDITIONS),
        "conditions": {
            ps: conds for ps, conds in sorted(CONTEXT_CONDITIONS.items())
        },
    }
