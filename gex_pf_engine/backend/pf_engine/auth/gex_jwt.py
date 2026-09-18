"""
GEX platform JWT verification for engine services (ADR 2026-07-06).
====================================================================
ONE identity issuer: the GEX platform backend (:8000, app/core/auth.py).
This module replaces the previous third-party (Supabase-era) verifier —
engines only accept platform-minted tokens. Deployed verbatim to every engine
(tea_engine, gex_pf_engine); keep it dependency-light and package-agnostic.

Accepted tokens, both minted by the platform:
  - user tokens     (POST /api/v1/auth/login)         session_tier=authenticated
  - service tokens  (auth.create_service_token)       session_tier=service

Algorithms, mirroring the platform's own selection:
  - HS256 — shared secret. Set GEX_JWT_SECRET to the platform SECRET_KEY.
  - RS256 — public key fetched from the platform JWKS endpoint.

Environment
-----------
GEX_JWT_SECRET       Shared secret for HS256. Defaults to the platform DEV
                     default so local dev works out of the box; production
                     deployments MUST set it (the platform refuses to boot
                     on the dev default, so mismatched engines fail closed).
GEX_JWKS_URL         Platform JWKS endpoint for RS256 verification.
                     Default: http://localhost:8000/api/v1/auth/jwks
GEX_JWT_ISSUER       Default: https://api.greenearthx.com
GEX_JWT_AUDIENCE     Default: gex-platform

Public surface (API-compatible with the retired legacy verifier)
--------------------------------------------------------------------
- AuthenticatedUser
- get_current_user             user tokens only
- get_current_user_or_service  user OR service tokens
- verify_gex_token             direct verification
- public_path_guard            dependency factory for engines that protect
                               everything except an explicit public list
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import jwt  # PyJWT >= 2.8 (with cryptography extras for RS256)
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("gex.engine_auth")

_DEV_SECRET_DEFAULT = "dev_secret_key_change_in_production"

GEX_JWT_SECRET = os.getenv("GEX_JWT_SECRET", _DEV_SECRET_DEFAULT)
GEX_JWKS_URL = os.getenv("GEX_JWKS_URL", "http://localhost:8000/api/v1/auth/jwks")
GEX_JWT_ISSUER = os.getenv("GEX_JWT_ISSUER", "https://api.greenearthx.com")
GEX_JWT_AUDIENCE = os.getenv("GEX_JWT_AUDIENCE", "gex-platform")
JWKS_CACHE_TTL = int(os.getenv("GEX_JWKS_CACHE_TTL", "600"))

if GEX_JWT_SECRET == _DEV_SECRET_DEFAULT:
    logger.warning(
        "GEX_JWT_SECRET is the development default — acceptable for local dev only."
    )


# ── Identity ──────────────────────────────────────────────────────────────────

@dataclass
class AuthenticatedUser:
    """Claims of a verified GEX platform token."""

    user_id: str                    # `sub`
    email: Optional[str]
    role: str                       # "authenticated" | "service" (session_tier)
    company_id: Optional[str] = None
    company_type: Optional[str] = None
    business_function: Optional[str] = None
    service_type: Optional[str] = None
    is_platform_admin: bool = False
    raw_claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_service_role(self) -> bool:
        return self.role == "service"


# ── JWKS cache (RS256) ────────────────────────────────────────────────────────

_jwks_lock = threading.Lock()
_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}


def _fetch_jwks(force: bool = False) -> list[dict[str, Any]]:
    with _jwks_lock:
        fresh = time.monotonic() - _jwks_cache["fetched_at"] < JWKS_CACHE_TTL
        if _jwks_cache["keys"] is not None and fresh and not force:
            return _jwks_cache["keys"]
        resp = httpx.get(GEX_JWKS_URL, timeout=5.0)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        _jwks_cache.update(keys=keys, fetched_at=time.monotonic())
        return keys


def _rs256_key(kid: Optional[str]):
    keys = _fetch_jwks()
    for k in keys:
        if kid is None or k.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(k)
    # kid not found — refresh once (platform may have rotated)
    for k in _fetch_jwks(force=True):
        if kid is None or k.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(k)
    raise _unauthorized("signing key not found in platform JWKS")


# ── Verification ──────────────────────────────────────────────────────────────

def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Invalid token: {detail}",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_gex_token(token: str) -> AuthenticatedUser:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"malformed token ({exc})") from exc

    alg = header.get("alg")
    if alg == "HS256":
        key: Any = GEX_JWT_SECRET
    elif alg == "RS256":
        key = _rs256_key(header.get("kid"))
    else:
        raise _unauthorized(f"unsupported algorithm {alg!r} — GEX issues HS256/RS256")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=GEX_JWT_AUDIENCE,
            issuer=GEX_JWT_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(str(exc)) from exc

    return AuthenticatedUser(
        user_id=str(claims.get("sub", "")),
        email=claims.get("email"),
        role=claims.get("session_tier", "authenticated"),
        company_id=claims.get("company_id"),
        company_type=claims.get("company_type"),
        business_function=claims.get("business_function"),
        service_type=claims.get("service_type"),
        is_platform_admin=bool(claims.get("is_platform_admin", False)),
        raw_claims=claims,
    )


# ── FastAPI dependencies ──────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthenticatedUser:
    """User tokens only — rejects service tokens."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("missing bearer token")
    user = verify_gex_token(credentials.credentials)
    if user.is_service_role:
        raise _unauthorized("service token not accepted on user endpoint")
    return user


async def get_current_user_or_service(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthenticatedUser:
    """Accepts EITHER a user token or a platform service token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("missing bearer token")
    return verify_gex_token(credentials.credentials)


def public_path_guard(public_paths: set[str]):
    """
    Dependency factory: authentication by default for a whole engine app.
    Usage:
        app = FastAPI(dependencies=[Depends(public_path_guard({"/", "/health"}))])
    """

    async def _guard(request: Request) -> None:
        if request.method == "OPTIONS" or request.url.path in public_paths:
            return
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise _unauthorized("missing bearer token")
        user = verify_gex_token(auth_header.split(" ", 1)[1].strip())
        request.state.gex_user = user

    return _guard
