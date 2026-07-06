"""
Authorization headers for backend→engine calls (ADR 2026-07-06).

One identity issuer: engines (:8001 PF, :8002 TEA) verify GEX platform JWTs
only. Every outbound engine call must carry either the caller's own bearer
(preserves user identity end-to-end — preferred when a Request is in scope)
or a short-lived platform service token.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request


def engine_auth_headers(request: Optional[Request] = None) -> dict[str, str]:
    """Forward the caller's bearer when available, else mint a service token."""
    if request is not None:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return {"Authorization": header}
    from app.core.auth import create_service_token

    return {"Authorization": f"Bearer {create_service_token()}"}
