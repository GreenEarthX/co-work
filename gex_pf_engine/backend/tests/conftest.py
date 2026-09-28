"""
Shared test fixtures.

`service_client` exists because the engine stopped answering anonymous calls.
Since the one-identity-issuer ADR (2026-07-06) `main.py` guards every path
outside ENGINE_PUBLIC_PATHS with `public_path_guard`, and the API tests still
built a bare `TestClient(app)`: from 2026-09-09 every call they made was
refused with 401 before reaching a route.

The tests now authenticate the way production traffic does, and the guard is
left alone. The platform proxy calls the engine with `engine_auth_headers()`,
which mints a short-lived service token (`create_service_token()` in
gex-platform-enhanced backend/app/core/auth.py). `gex_service_token()` builds
the same claims and signs them with the engine's OWN verification settings
from `pf_engine.auth.gex_jwt`, so every test request passes the full check
(signature, issuer, audience, expiry) whether the GEX_JWT_* variables are set
or left at their dev defaults.

`curve_service` exists because authenticating exposed the next problem. The
/pf routes share one module-level GabillonService whose calibration memory
defaults to $TMPDIR/gex_pf_engine/pricing_memory, the same store a local
engine uses when PF_ENGINE_DATA_DIR is unset. Calibrations written by one run
survive into the next, so the offtake test's "409 before calibration" held
exactly once: measured 2026-09-28, the second run got 200. Every
`service_client` test therefore gets fresh services on a throwaway store.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from pf_engine.auth import gex_jwt
from pf_engine.main import app
from pf_engine.pricing.gabillon.service import GabillonService
from pf_engine.pricing.memory import ProjectCalibrationMemory
from pf_engine.pricing.offtake.service import OfftakeService
from pf_engine.routers import pricing as pf_routes


def gex_service_token(service_name: str = "pf-engine-tests", ttl_minutes: int = 5) -> str:
    """Claims of the platform's `create_service_token()`, signed for this engine."""
    now = datetime.now(timezone.utc)
    claims = {
        "iss": gex_jwt.GEX_JWT_ISSUER,
        "aud": gex_jwt.GEX_JWT_AUDIENCE,
        "sub": f"service:{service_name}",
        "email": None,
        "session_tier": "service",
        "business_function": "SERVICE",
        "is_platform_admin": False,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    # HS256 against the shared secret: the engine's RS256 path would fetch the
    # platform JWKS over HTTP, which a unit test cannot rely on.
    return jwt.encode(claims, gex_jwt.GEX_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def curve_service(tmp_path, monkeypatch) -> GabillonService:
    """Point the /pf routes at fresh services on a throwaway calibration store."""
    curves = GabillonService(ProjectCalibrationMemory(str(tmp_path)))
    monkeypatch.setattr(pf_routes, "curve_service", curves)
    monkeypatch.setattr(pf_routes, "offtake_service", OfftakeService(curves))
    return curves


@pytest.fixture
def service_client(curve_service) -> TestClient:
    """A TestClient that sends a platform service bearer on every request."""
    return TestClient(app, headers={"Authorization": f"Bearer {gex_service_token()}"})
