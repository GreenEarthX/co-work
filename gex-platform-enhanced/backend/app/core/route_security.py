"""
Route Security Doctrine (ADR 2026-07-06)
========================================
Layering, outermost first:

  1. Authentication by default   — `require_authenticated` is installed as a
     global FastAPI dependency in main.py. Every route requires a verified
     identity unless the route is EXPLICITLY registered below, with a reason.
  2. Domain-specific authorization — per-router dependencies
     (e.g. require_finance_entitlement) own business rules.
  3. ABAC middleware              — second layer: policy evaluation + audit.
  4. PostgreSQL RLS               — final backstop once the Postgres
     migration lands (migrations/setup_postgres_rls.sql).
  5. CI guardrails                — tests/test_architecture_guardrails.py
     fails the build if a route is public without registration here.

Rules:
  - No route is trusted because middleware might catch it.
  - No data is trusted because the frontend says it is authenticated.
  - No demo shortcut can exist in production (config.py hard-fails on
    GEX_DEMO_MODE in production/staging).
  - No public endpoint without explicit registration AND a stated reason.

This module is the ONLY place public routes may be declared. The ABAC
middleware derives its bypass list from here — there is no second list.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger("gex.route_security")


# ── Tier 1: PUBLIC — reachable without any identity. Reason mandatory. ───────

PUBLIC_ROUTES: dict[str, str] = {
    "/": "service banner only, exposes no data",
    "/docs": "OpenAPI UI (served pre-dependency by FastAPI; listed for completeness)",
    "/openapi.json": "OpenAPI schema",
    "/redoc": "OpenAPI UI",
    "/health": "liveness probe",
    "/healthz": "liveness probe",
    "/api/v1/health": "liveness probe",
    "/api/v1/auth/health": "auth subsystem probe",
    "/api/v1/bankability/health": "engine reachability probe",
    "/api/v1/model/health": "finance model probe",
    "/api/v1/decision-twin/health": "decision twin probe",
    "/api/v1/auth/login": "credential exchange — must be reachable unauthenticated",
    "/api/v1/account/register": "self-service registration — no account exists yet. Creates a PENDING account ONLY; grants nothing until a GEX employee completes vetting (see core/account_lifecycle.py). Rate-limit before GA.",
    "/api/v1/auth/refresh": "token refresh — authenticates via refresh token in body",
    "/api/v1/auth/jwks": "public signing keys for token verification by other services",
    "/api/v1/auth/oidc-discovery": "public OIDC metadata",
    "/api/v1/onboarding/reference-data/molecules": "public reference data",
    "/api/v1/onboarding/reference-data/fuels": "public reference data",
    "/api/v1/onboarding/reference-data/certifications": "public reference data",
    "/api/v1/onboarding/step1/market-demand": "pre-signup prospect wizard — no account exists yet; rate-limit before GA",
    "/api/v1/onboarding/step2/bankability-check": "pre-signup prospect wizard — no account exists yet; rate-limit before GA",
    "/api/v1/onboarding/step3/certification-eligibility": "pre-signup prospect wizard — no account exists yet; rate-limit before GA",
    "/api/v1/onboarding/complete": "pre-signup prospect wizard — no account exists yet; rate-limit before GA",
    "/api/v1/onboarding/trust-score": "pre-signup prospect wizard — no account exists yet; rate-limit before GA",
}

PUBLIC_PREFIXES: dict[str, str] = {
    "/static": "static assets",
}


# ── Tier 2: ABAC-EXEMPT — authentication IS required, but the ABAC policy
#    evaluation is skipped. Reason mandatory. ─────────────────────────────────

ABAC_EXEMPT_ROUTES: dict[str, str] = {
    "/api/v1/bankability/evidence/seed": (
        "demo-seed helper writes across ALL gates so ABAC rule R5 cannot "
        "resolve a single gate context; project_id scoping is the guard. "
        "Auth is still required (tightened 2026-07-06; was fully public)."
    ),
}

ABAC_EXEMPT_PREFIXES: dict[str, str] = {}


def is_public(path: str) -> bool:
    return path in PUBLIC_ROUTES or any(
        path.startswith(prefix) for prefix in PUBLIC_PREFIXES
    )


def is_abac_exempt(path: str) -> bool:
    """Paths ABAC middleware skips: everything public plus the exempt tier."""
    if is_public(path):
        return True
    return path in ABAC_EXEMPT_ROUTES or any(
        path.startswith(prefix) for prefix in ABAC_EXEMPT_PREFIXES
    )


# ── The default-deny dependency ──────────────────────────────────────────────

async def require_authenticated(request: Request) -> None:
    """
    Global dependency: fail closed unless the route is registered public.

    Independent of ABAC middleware by design — if the middleware is disabled,
    misconfigured, or bypassed, this dependency still refuses unauthenticated
    requests. On success it populates request.state.user_payload, which is
    also what app/db/session.py reads to set the Postgres RLS tenant context.
    """
    if request.method == "OPTIONS":  # CORS preflight
        return

    path = request.url.path
    if is_public(path):
        return

    # Reuse identity if the ABAC middleware already verified this request.
    payload = getattr(request.state, "auth_user_payload", None) or getattr(
        request.state, "user_payload", None
    )

    if payload is None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                from app.core.auth import get_user_payload_from_token

                payload = get_user_payload_from_token(token)
            except ValueError:
                payload = None

    if payload is None and settings.GEX_DEMO_MODE:
        # Demo fallback — cannot exist in production: config.py refuses to
        # start with GEX_DEMO_MODE=True outside development.
        demo_user = request.headers.get("x-demo-user", "").strip()
        if demo_user:
            from app.core.auth import get_user_payload_by_email

            payload = get_user_payload_by_email(demo_user)
            if payload is not None:
                logger.warning(
                    "DEMO MODE: authenticated %s via x-demo-user header", demo_user
                )

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user_payload = payload
    request.state.auth_user_payload = payload
    # Routes authenticated by this dependency rather than by the middleware must
    # bind the tenant too, or the shim would see no caller.
    from app.core.request_tenant import bind_from_request
    bind_from_request(request)
