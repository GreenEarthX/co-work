"""
GEX ABAC Middleware — FastAPI Request Interceptor
==================================================
Wraps every API request with ABAC policy evaluation.
Logs every access decision to the immutable audit trail.

Location: gex-enhanced-platform/backend/app/core/abac_middleware.py

Usage in main.py:
    from app.core.abac_middleware import ABACMiddleware
    app.add_middleware(ABACMiddleware, phase=1)
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.abac import (
    evaluate_access, get_visible_gates,
    UserAttributes, ResourceAttributes, ContextAttributes,
    Action, Sensitivity, Decision,
)

logger = logging.getLogger("gex.abac")


# Routes that bypass ABAC (public endpoints, health checks)
BYPASS_ROUTES = {
    "/docs", "/openapi.json", "/redoc",
    "/api/v1/health", "/api/v1/bankability/health",
    "/api/v1/model/health", "/api/v1/decision-twin/health",
    "/api/v1/onboarding/reference-data/molecules",
    "/api/v1/onboarding/reference-data/certifications",
}

# Map HTTP methods to ABAC actions
METHOD_ACTION_MAP = {
    "GET": Action.READ,
    "HEAD": Action.READ,
    "POST": Action.WRITE,
    "PUT": Action.WRITE,
    "PATCH": Action.WRITE,
    "DELETE": Action.DELETE,
}


class ABACMiddleware(BaseHTTPMiddleware):
    """
    Intercepts every API request, evaluates ABAC policy,
    and logs the decision to the audit trail.
    """

    def __init__(self, app, phase: int = 1):
        super().__init__(app)
        self.phase = phase

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Bypass public routes
        if path in BYPASS_ROUTES or path.startswith("/static"):
            return await call_next(request)

        # Extract user attributes from auth token
        # (In production, this reads from JWT claims + DB lookup)
        user = await self._extract_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        # Extract resource attributes from the request path + body
        resource = await self._extract_resource(request)
        if not resource:
            # If we can't determine the resource, allow the request
            # (this handles routes that don't map to specific project data)
            return await call_next(request)

        # Build context
        context = await self._build_context(resource.project_id)

        # Determine action
        action = METHOD_ACTION_MAP.get(request.method, Action.READ)

        # Override action for specific endpoints
        if "/export" in path:
            action = Action.EXPORT
        elif "/verify" in path:
            action = Action.VERIFY
        elif "/share" in path:
            action = Action.SHARE

        # Evaluate ABAC policy
        decision = evaluate_access(
            user=user,
            resource=resource,
            action=action,
            context=context,
            phase=self.phase,
        )

        # Log to audit trail (always, regardless of decision)
        await self._log_access(user, resource, action, decision)

        # Enforce decision
        if decision.decision == Decision.DENY:
            logger.warning(
                "ABAC DENY: user=%s company=%s project=%s reason=%s",
                user.user_id, user.company_id, resource.project_id,
                decision.denial_reason,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Access denied",
                    "reason": decision.denial_reason,
                    "rules_evaluated": decision.rules_evaluated,
                },
            )

        # Inject visible_gates into request state for downstream handlers
        request.state.abac_user = user
        request.state.abac_visible_gates = get_visible_gates(user, resource.project_id)
        request.state.abac_decision = decision

        return await call_next(request)

    async def _extract_user(self, request: Request) -> Optional[UserAttributes]:
        """
        Extract user attributes from the authentication token.
        
        PLACEHOLDER: In production, this reads from:
        1. JWT token (user_id, company_id)
        2. DB lookup (actor_type_per_project, clearance_level, nda_signed_with)
        3. Cache (to avoid DB hit on every request)
        """
        # TODO: Replace with real auth token extraction
        auth_header = request.headers.get("authorization", "")
        if not auth_header and not request.headers.get("x-demo-user"):
            return None

        # Demo/dev mode: read from header
        demo_user = request.headers.get("x-demo-user", "")
        if demo_user:
            return UserAttributes(
                user_id=demo_user,
                company_id=request.headers.get("x-demo-company", "demo_company"),
                actor_type_per_project={},  # Populated from DB in production
                jurisdiction=request.headers.get("x-demo-jurisdiction", "EU"),
            )

        # Production: decode JWT, lookup user, build attributes
        # from app.core.auth import decode_token, get_user_attributes
        # token_data = decode_token(auth_header)
        # return get_user_attributes(token_data.user_id)
        return None

    async def _extract_resource(self, request: Request) -> Optional[ResourceAttributes]:
        """
        Extract resource attributes from the request path.
        Maps URL patterns to project_id and resource_type.
        """
        path = request.url.path
        parts = path.split("/")

        # Extract project_id from common URL patterns
        project_id = None
        resource_type = "EVIDENCE"

        # /api/v1/bankability/* or /api/v1/finance-model/*
        if "/bankability/" in path or "/finance-model/" in path:
            # Project ID comes from request body
            try:
                body = await request.json()
                project_id = body.get("project_id")
            except Exception:
                project_id = request.query_params.get("project_id")
            resource_type = "FINANCIAL_MODEL" if "/finance-model/" in path else "EVIDENCE"

        # /api/v1/marketplace/* or /api/v1/matching/*
        elif "/marketplace/" in path or "/matching/" in path:
            resource_type = "MARKETPLACE"
            # These are multi-project endpoints — ABAC filters results, not access
            return None

        # /api/v1/contracts/*
        elif "/contracts/" in path:
            resource_type = "CONTRACT"
            project_id = request.query_params.get("project_id")

        if not project_id:
            return None

        # TODO: In production, load resource attributes from DB
        return ResourceAttributes(
            project_id=project_id,
            data_owner_company_id="",  # Loaded from DB
            sensitivity=Sensitivity.SHARED,  # Default; overridden per-record
            resource_type=resource_type,
        )

    async def _build_context(self, project_id: str) -> ContextAttributes:
        """
        Build context attributes for the request.
        
        PLACEHOLDER: In production, queries the STAKEHOLDERS table
        for the project to get the list of stakeholder company_ids.
        """
        # TODO: Replace with real DB query
        # stakeholders = await db.get_project_stakeholders(project_id)
        return ContextAttributes(
            project_stakeholders=set(),  # Populated from DB
            project_jurisdiction="",  # From PROJECT table
            project_state="SPECULATIVE",  # From latest bankability evaluation
        )

    async def _log_access(
        self,
        user: UserAttributes,
        resource: ResourceAttributes,
        action: Action,
        decision,
    ):
        """
        Log access decision to immutable audit trail.
        
        PLACEHOLDER: In production, writes to ACCESS_LOG table.
        Append-only, never updated or deleted.
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user.user_id,
            "company_id": user.company_id,
            "action": action.value,
            "resource_type": resource.resource_type,
            "resource_id": resource.resource_id,
            "project_id": resource.project_id,
            "decision": decision.decision.value,
            "rules_evaluated": decision.rules_evaluated,
            "denial_reason": decision.denial_reason,
            "attributes_snapshot": decision.attributes_snapshot,
        }

        # TODO: Write to ACCESS_LOG table in PostgreSQL
        # await db.insert_access_log(log_entry)

        # For now, log to application logger
        logger.info("ABAC: %s", json.dumps(log_entry, default=str))
