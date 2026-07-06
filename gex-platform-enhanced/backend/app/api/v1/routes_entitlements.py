"""
Finance entitlements API + the shared authorization dependency (Ticket 1a).

  GET    /api/v1/entitlements?user_id=&project_id=     list grants
  POST   /api/v1/entitlements                          grant (admin/CISO)
  DELETE /api/v1/entitlements/{entitlement_id}         revoke (admin/CISO)
  GET    /api/v1/entitlements/check?project_id=        does the caller have access?

`require_finance_entitlement` is a FastAPI dependency that protects sensitive
project-finance endpoints: it resolves the caller identity from x-demo-* headers
(JWT in production), checks role OR project-scoped grant, audits the decision,
and raises 403 on denial. The frontend is NEVER trusted for data protection.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.core import entitlements as ent

router = APIRouter()


# ── Identity from request headers (demo) / JWT (prod) ─────────────────────────
def _identity(
    x_demo_user: Optional[str],
    x_demo_company: Optional[str],
    x_demo_function: Optional[str],
    x_demo_service_type: Optional[str],
    x_demo_capabilities: Optional[str],
    authorization: Optional[str],
) -> dict:
    user_id = x_demo_user
    company_id = x_demo_company
    business_function = x_demo_function
    service_type = x_demo_service_type or None
    capabilities = x_demo_capabilities.split(",") if x_demo_capabilities else []
    # Production: prefer verified JWT claims over demo headers.
    if authorization and authorization.lower().startswith("bearer "):
        try:
            from app.core.auth import get_user_payload_from_token
            payload = get_user_payload_from_token(authorization.split(" ", 1)[1].strip())
            user_id = payload.get("user_id") or payload.get("email") or user_id
            company_id = payload.get("company_id") or payload.get("company") or company_id
            business_function = payload.get("business_function") or business_function
            service_type = payload.get("service_type") or service_type
            capabilities = payload.get("capabilities") or capabilities
        except Exception:
            pass
    return {
        "user_id": user_id or "anonymous",
        "company_id": company_id,
        "business_function": business_function,
        "service_type": service_type,
        "capabilities": capabilities,
    }


def require_finance_entitlement(route_name: str):
    """
    Dependency factory. Use on sensitive endpoints:

        @router.get("/dscr-heatmap/{asset_id}",
                    dependencies=[Depends(require_finance_entitlement("dscr_sensitivity"))])

    `project_id` is taken from path/query param `project_id` or `asset_id`.
    """
    async def _dep(
        project_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        x_demo_user: Optional[str] = Header(default=None, alias="x-demo-user"),
        x_demo_company: Optional[str] = Header(default=None, alias="x-demo-company"),
        x_demo_function: Optional[str] = Header(default=None, alias="x-demo-function"),
        x_demo_service_type: Optional[str] = Header(default=None, alias="x-demo-service-type"),
        x_demo_capabilities: Optional[str] = Header(default=None, alias="x-demo-capabilities"),
        authorization: Optional[str] = Header(default=None),
    ):
        ident = _identity(x_demo_user, x_demo_company, x_demo_function, x_demo_service_type, x_demo_capabilities, authorization)
        proj = project_id or asset_id
        allowed, basis, reason = ent.check_finance_access(
            user_id=ident["user_id"], company_id=ident["company_id"], project_id=proj,
            business_function=ident["business_function"], service_type=ident["service_type"],
            capabilities=ident["capabilities"],
        )
        ent.log_access(allowed=allowed, user_id=ident["user_id"], project_id=proj,
                       basis=basis, reason=reason, route=route_name)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "forbidden",
                    "route": route_name,
                    "reason": reason,
                    "required": "finance role (Finance/Exec/Bank/DFI/Insurer) or project-scoped FINANCE_REVIEW grant",
                },
            )
        return ident
    return _dep


# ── Models ────────────────────────────────────────────────────────────────────
class GrantRequest(BaseModel):
    user_id: str
    project_id: str
    capability: str = ent.FINANCE_REVIEW
    reason: Optional[str] = None
    expires_at: Optional[str] = None  # ISO-8601


# ── Admin / CISO endpoints ─────────────────────────────────────────────────────
@router.get("")
def list_grants(user_id: Optional[str] = None, project_id: Optional[str] = None):
    return {"entitlements": ent.list_entitlements(user_id=user_id, project_id=project_id)}


@router.post("", status_code=201)
def grant(body: GrantRequest, x_demo_user: Optional[str] = Header(default=None, alias="x-demo-user")):
    rec = ent.grant_entitlement(
        user_id=body.user_id, project_id=body.project_id, capability=body.capability,
        granted_by=x_demo_user or "admin", reason=body.reason, expires_at=body.expires_at,
    )
    return rec


@router.delete("/{entitlement_id}")
def revoke(entitlement_id: str, x_demo_user: Optional[str] = Header(default=None, alias="x-demo-user")):
    rec = ent.revoke_entitlement(entitlement_id, revoked_by=x_demo_user or "admin")
    if not rec:
        raise HTTPException(status_code=404, detail="entitlement not found")
    return rec


@router.get("/check")
def check(
    project_id: Optional[str] = Query(default=None),
    x_demo_user: Optional[str] = Header(default=None, alias="x-demo-user"),
    x_demo_company: Optional[str] = Header(default=None, alias="x-demo-company"),
    x_demo_function: Optional[str] = Header(default=None, alias="x-demo-function"),
    x_demo_service_type: Optional[str] = Header(default=None, alias="x-demo-service-type"),
    x_demo_capabilities: Optional[str] = Header(default=None, alias="x-demo-capabilities"),
    authorization: Optional[str] = Header(default=None),
):
    """Frontend route-guard probe: may the caller access finance content for this project?"""
    ident = _identity(x_demo_user, x_demo_company, x_demo_function, x_demo_service_type, x_demo_capabilities, authorization)
    allowed, basis, reason = ent.check_finance_access(
        user_id=ident["user_id"], company_id=ident["company_id"], project_id=project_id,
        business_function=ident["business_function"], service_type=ident["service_type"],
        capabilities=ident["capabilities"],
    )
    # Audit the probe too (denied probes are useful signal).
    ent.log_access(allowed=allowed, user_id=ident["user_id"], project_id=project_id,
                   basis=basis, reason=reason, route="entitlement_check")
    return {"allowed": allowed, "basis": basis, "reason": reason, "project_id": project_id}
