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
    evaluate_access, get_visible_gates, gate_for_evidence,
    UserAttributes, ResourceAttributes, ContextAttributes,
    Action, Sensitivity, Decision,
    ActorType, Capability, ClearanceLevel,
)
from app.core.auth import get_user_payload_by_email, get_user_payload_from_token
from app.core.permission_engine import check_permission as check_feature_permission
from app.core.project_registry import company_slug, get_project_profile, normalize_project_id

logger = logging.getLogger("gex.abac")


# Single source of truth for public/exempt routes: app.core.route_security.
# This middleware keeps NO private bypass list (ADR 2026-07-06) — every
# exemption is registered there with a stated reason.
from app.core.route_security import (
    PUBLIC_ROUTES, PUBLIC_PREFIXES, ABAC_EXEMPT_ROUTES, ABAC_EXEMPT_PREFIXES,
)

BYPASS_ROUTES = set(PUBLIC_ROUTES) | set(ABAC_EXEMPT_ROUTES)
BYPASS_PREFIXES = set(PUBLIC_PREFIXES) | set(ABAC_EXEMPT_PREFIXES)

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

        # Only intercept API routes — everything else passes through
        if not path.startswith("/api/"):
            return await call_next(request)

        # Bypass public routes
        if path in BYPASS_ROUTES or any(path.startswith(prefix) for prefix in BYPASS_PREFIXES):
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

        # ── Layer 2: Permission Engine (feature-level access) ──
        # Maps the request path to a permission string and checks
        # against the 165-permission × 30-profile matrix.
        perm_string = self._resolve_permission_string(path, request.method)
        if perm_string:
            identity = getattr(request.state, "auth_user_payload", {})
            perm_ctx = {
                "kyc_status": getattr(user, "kyc_status", "VERIFIED"),
                "token_ready": getattr(user, "token_ready", False),
                "credit_rating": getattr(user, "credit_rating", "NR"),
                "export_licenses": getattr(user, "export_licenses", []),
                "aggregation_limit_mt": getattr(user, "aggregation_limit_mt", None),
                "is_mandated_lender": user.company_id in resource.mandated_lenders,
                "is_mandated_insurer": user.company_id in resource.mandated_insurers,
            }
            perm_result = check_feature_permission(
                perm_string=perm_string,
                company_type=identity.get("company_type") or request.headers.get("x-demo-company-type", "PRODUCER"),
                business_function=identity.get("business_function") or request.headers.get("x-demo-function", "EXECUTIVE"),
                service_type=identity.get("service_type") or request.headers.get("x-demo-service-type") or None,
                capabilities=identity.get("capabilities")
                or (request.headers.get("x-demo-capabilities", "").split(",") if request.headers.get("x-demo-capabilities") else []),
                user_id=user.user_id,
                context=perm_ctx,
            )
            request.state.perm_result = perm_result
            if not perm_result.allowed:
                logger.warning(
                    "PERM DENY: user=%s perm=%s reason=%s",
                    user.user_id, perm_string, perm_result.reason,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Permission denied",
                        "perm_string": perm_string,
                        "reason": perm_result.reason,
                        "profile_key": perm_result.profile_key,
                    },
                )

        return await call_next(request)

    @staticmethod
    def _resolve_permission_string(path: str, method: str) -> Optional[str]:
        """
        Map a request URL to a permission string from the 165-permission registry.
        Returns None if no mapping exists (the route is not yet permission-gated).

        This is the bridge between HTTP routes and the permission engine.
        In production, this mapping lives in a DB table. For now, key routes
        are mapped statically.
        """
        # Normalize: /api/v1/xxx/yyy → xxx.yyy
        parts = path.replace("/api/v1/", "").strip("/").split("/")
        if len(parts) < 2:
            return None

        # Route → permission mappings for key endpoints
        ROUTE_MAP: dict[str, str] = {
            # GAM
            "gam/supply/tokenize": "gam.supply.token.mint",
            "gam/supply/volume": "gam.supply.supply_volume.view",
            "gam/matching/offtaker": "gam.matchmaking.offtaker_search.execute",
            "gam/matching/producer": "gam.matchmaking.producer_search.execute",
            "gam/demand/adjust": "gam.demand.supplier.adjust_volume",
            # Economics
            "economics/snapshot": "economics.snapshot.economics_dashboard.view",
            "economics/cost-stack": "economics.cost_stack.cost_stack.view",
            "economics/benchmark": "economics.benchmark.benchmark.view",
            "economics/lca": "economics.lca.lifecycle_assessment.view",
            # Compliance
            "compliance/regulatory": "compliance.regulatory.compliance_dashboard.view",
            "compliance/ghg": "compliance.ghg.ghg_calculation.view",
            "compliance/certification": "compliance.certification.certification_scheme.view",
            # Procurement
            "procurement/equipment": "procurement.equipment.equipment.view",
            "procurement/supplier-db": "procurement.supplier_db.supplier.view",
            # Plausibility
            "plausibility/check": "plausibility.document_verification.plausibility_check.view",
            "plausibility/attestation": "plausibility.blockchain.attestation.view",
        }

        # Try exact match first, then prefix match
        route_key = "/".join(parts[:2])
        if route_key in ROUTE_MAP:
            return ROUTE_MAP[route_key]

        # Export endpoints get the export variant
        if method == "GET" and "export" in path:
            base = ROUTE_MAP.get(route_key)
            if base:
                return base.rsplit(".", 1)[0] + ".export"

        return None

    async def _extract_user(self, request: Request) -> Optional[UserAttributes]:
        """
        Extract user attributes from the authentication token.
        """
        auth_header = request.headers.get("authorization", "")
        payload: dict | None = None

        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = get_user_payload_from_token(token)
            except ValueError:
                payload = None

        # Demo/dev compatibility: resolve the seeded auth user by e-mail.
        # Only active when GEX_DEMO_MODE=true; returns 401 in production.
        if payload is None:
            from app.core.config import settings as _settings
            demo_user = request.headers.get("x-demo-user", "").strip()
            if demo_user:
                if not _settings.GEX_DEMO_MODE:
                    logger.warning("DEMO MODE DISABLED: rejected x-demo-user header for %s", demo_user)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required — demo headers disabled in production"},
                    )
                logger.warning("DEMO MODE: accepting x-demo-user header for %s (no bearer token)", demo_user)
                payload = get_user_payload_by_email(demo_user)
                if payload is None:
                    payload = {
                        "user_id": demo_user,
                        "email": demo_user,
                        "company_id": request.headers.get("x-demo-company", "demo_company"),
                        "company_type": request.headers.get("x-demo-company-type", "PRODUCER"),
                        "business_function": request.headers.get("x-demo-function", "EXECUTIVE"),
                        "service_type": request.headers.get("x-demo-service-type") or None,
                        "company_name": request.headers.get("x-demo-company", "demo_company"),
                        "user_name": demo_user,
                        "jurisdiction": request.headers.get("x-demo-jurisdiction", "EU"),
                        "kyc_status": "VERIFIED",
                        "nda_signed_with": [],
                        "assigned_audits": [],
                        "actor_type_per_project": {},
                        "capabilities": request.headers.get("x-demo-capabilities", "").split(",")
                        if request.headers.get("x-demo-capabilities")
                        else [],
                        "credit_rating": "NR",
                        "credit_rating_source": "GEX",
                        "export_licenses": [],
                        "token_ready": False,
                        "transformation_license": False,
                        "aggregation_limit_mt": None,
                        "clearance_level": "STANDARD",
                    }

        if payload is None:
            return None

        request.state.auth_user_payload = payload
        return self._user_from_payload(payload)

    @staticmethod
    def _user_from_payload(payload: dict) -> UserAttributes:
        actor_type_per_project: dict[str, list[ActorType]] = {}
        for project_id, actor_types in (payload.get("actor_type_per_project") or {}).items():
            values = actor_types if isinstance(actor_types, list) else [actor_types]
            resolved: list[ActorType] = []
            for raw in values:
                try:
                    resolved.append(ActorType(raw))
                except ValueError:
                    continue
            actor_type_per_project[project_id] = resolved

        capabilities: set[Capability] = set()
        for raw in payload.get("capabilities", []):
            try:
                capabilities.add(Capability(raw))
            except ValueError:
                continue

        try:
            clearance = ClearanceLevel(payload.get("clearance_level", "STANDARD"))
        except ValueError:
            clearance = ClearanceLevel.STANDARD

        return UserAttributes(
            user_id=payload["user_id"],
            company_id=payload.get("company_id") or company_slug(payload.get("company_name", "")),
            actor_type_per_project=actor_type_per_project,
            clearance_level=clearance,
            jurisdiction=payload.get("jurisdiction", ""),
            kyc_status=payload.get("kyc_status", "VERIFIED"),
            nda_signed_with=set(payload.get("nda_signed_with", [])),
            assigned_audits=set(payload.get("assigned_audits", [])),
            capabilities=capabilities,
            credit_rating=payload.get("credit_rating", "NR"),
            credit_rating_source=payload.get("credit_rating_source", "GEX"),
            export_licenses=list(payload.get("export_licenses", [])),
            token_ready=bool(payload.get("token_ready", False)),
            transformation_license=bool(payload.get("transformation_license", False)),
            aggregation_limit_mt=payload.get("aggregation_limit_mt"),
        )

    async def _extract_resource(self, request: Request) -> Optional[ResourceAttributes]:
        """
        Extract resource attributes from the request path.
        Maps URL patterns to project_id and resource_type.
        """
        path = request.url.path

        # Extract project_id from common URL patterns
        project_id = None
        resource_type = "EVIDENCE"

        # /api/v1/bankability/* or /api/v1/finance-model/*
        evidence_gate_id: str | None = None
        if "/bankability/" in path or "/finance-model/" in path:
            if "/projects/" in path:
                project_id = normalize_project_id(path.split("/projects/", 1)[1].split("/", 1)[0])
            try:
                body = await request.json()
                project_id = project_id or normalize_project_id(body.get("project_id"))
                # Evidence write carries evidence_key, not a gate. Resolve the
                # owning gate so R5 can authorise the gate owner — else gate_id
                # is None and R5 denies EVERY actor ("write to gate None").
                evidence_gate_id = gate_for_evidence(body.get("evidence_key"))
            except Exception:
                project_id = project_id or normalize_project_id(request.query_params.get("project_id"))
            resource_type = "FINANCIAL_MODEL" if "/finance-model/" in path else "EVIDENCE"

        # /api/v1/marketplace/* or /api/v1/matching/*
        elif "/marketplace/" in path or "/matching/" in path:
            resource_type = "MARKETPLACE"
            # These are multi-project endpoints — ABAC filters results, not access
            return None

        # /api/v1/contracts/*
        elif "/contracts/" in path:
            resource_type = "CONTRACT"
            project_id = normalize_project_id(request.query_params.get("project_id"))

        elif "/data-room/" in path:
            resource_type = "DATA_ROOM"
            project_id = normalize_project_id(path.split("/data-room/", 1)[1].split("/", 1)[0])

        elif "/timeline/" in path:
            resource_type = "TIMELINE"
            project_id = normalize_project_id(path.split("/timeline/", 1)[1].split("/", 1)[0])

        elif "/performance/" in path:
            resource_type = "PERFORMANCE"
            project_id = normalize_project_id(path.split("/performance/", 1)[1].split("/", 1)[0])

        elif "/project-activity/" in path:
            resource_type = "AUDIT_ACTIVITY"
            project_id = normalize_project_id(path.split("/project-activity/", 1)[1].split("/", 1)[0])

        elif "/deal-killers/" in path:
            resource_type = "EVIDENCE"
            project_id = normalize_project_id(path.split("/deal-killers/", 1)[1].split("/", 1)[0])

        elif "/verification/summary/" in path:
            resource_type = "EVIDENCE"
            project_id = normalize_project_id(path.split("/verification/summary/", 1)[1].split("/", 1)[0])

        elif "/verification/log/" in path:
            resource_type = "EVIDENCE"
            project_id = normalize_project_id(path.split("/verification/log/", 1)[1].split("/", 1)[0])

        elif "/reports/banker/" in path:
            resource_type = "FINANCIAL_MODEL"
            project_id = normalize_project_id(path.split("/reports/banker/", 1)[1].split("/", 1)[0])

        elif "/commitments/project/" in path:
            resource_type = "CONTRACT"
            project_id = normalize_project_id(path.split("/commitments/project/", 1)[1].split("/", 1)[0])

        if not project_id:
            return None

        profile = get_project_profile(project_id)
        if not profile:
            return ResourceAttributes(
                project_id=project_id,
                data_owner_company_id="",
                sensitivity=Sensitivity.SHARED,
                resource_type=resource_type,
                gate_id=evidence_gate_id,
            )

        sensitivity = self._default_sensitivity(resource_type)
        return ResourceAttributes(
            project_id=project_id,
            data_owner_company_id=profile.owner_company_id,
            sensitivity=sensitivity,
            shared_with=profile.shared_with_company_ids,
            resource_type=resource_type,
            mandated_lenders=profile.mandated_lender_ids,
            mandated_insurers=profile.mandated_insurer_ids,
            gate_id=evidence_gate_id,
        )

    async def _build_context(self, project_id: str) -> ContextAttributes:
        """
        Build context attributes for the request.
        """
        profile = get_project_profile(project_id)
        return ContextAttributes(
            project_stakeholders=profile.stakeholder_company_ids if profile else set(),
            project_jurisdiction=profile.jurisdiction if profile else "",
            project_state="SPECULATIVE",
        )

    @staticmethod
    def _default_sensitivity(resource_type: str) -> Sensitivity:
        if resource_type == "FINANCIAL_MODEL":
            return Sensitivity.RESTRICTED
        if resource_type in {"DATA_ROOM", "CONTRACT", "EVIDENCE"}:
            return Sensitivity.CONFIDENTIAL
        return Sensitivity.SHARED

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
