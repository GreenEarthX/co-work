"""
A PRESENTED credential that fails is a refusal, not an absence.
===============================================================
Under GEX_DEMO_MODE the `x-demo-user` header resolves a seeded account by e-mail,
with no credential. That is tolerable only for a caller who sent NO Authorization
header — a local demo session. Both identity layers used to consult the demo
header whenever the bearer failed to *decode*, so a forged, expired or re-keyed
bearer was silently served as whichever seeded user the header named.

Measured 2026-09-14 on the live :8000 backend with a forged, unsigned JWT:
`GET /api/v1/pricing/term-curve/SAF` answered 401 to the bearer alone and **200**
once the demo headers were added — which the frontend fetch bridge adds to every
/api/ call. A session the server had rejected therefore looked alive (HANDOFF
§8.11), and the bridge's 401 handler never fired.

The rule, asserted against both layers because each can be the only gate:
  - ABACMiddleware._extract_user            (skipped for ABAC-exempt routes, and
                                             absent when ENABLE_ABAC_MIDDLEWARE=False)
  - route_security.require_authenticated    (the global default-deny dependency)

Store isolation. The demo lookup is stubbed, so no request here reads or seeds a
store. A lookup that escapes the stub lands in `isolated_store`: since 2026-09-14
app.core.auth resolves `settings.SQLITE_DB_PATH` at call time and the fixture carries
the real auth schema (pinned by tests/test_auth_store_isolation.py). Before, auth
captured `DB_PATH` at import, and this file redirected `auth.DB_PATH` to compensate.

The app modules are imported HERE, at collection — the same import every
app-importing test performs. Until 2026-09-15 importing app.core.auth ran
`init_auth_db()` against the dev database; it is now an app-startup step and the
import writes nothing (tests/test_auth_store_isolation.py).
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.core import abac_middleware, auth
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from app.core.route_security import require_authenticated

PROBE = "/api/v1/__demo_probe__"
DEMO_EMAIL = "demo-probe@example.com"
DEMO_HEADERS = {"x-demo-user": DEMO_EMAIL, "x-demo-company": "demo_probe_co"}

SEEDED_USER = {
    "user_id": "demo_probe_user",
    "email": DEMO_EMAIL,
    "company_id": "demo_probe_co",
    "company_name": "demo_probe_co",
    "company_type": "PRODUCER",
    "service_type": None,
    "business_function": "COMMERCIAL",
    "user_name": "Demo Probe",
    "clearance_level": "STANDARD",
    "jurisdiction": "DE",
    "kyc_status": "VERIFIED",
    "nda_signed_with": [],
    "assigned_audits": [],
    "actor_type_per_project": {},
    "capabilities": [],
    "is_platform_admin": False,
}

BEARER_USER_ID = "bearer_probe_user"


async def _probe(request: Request):
    payload = getattr(request.state, "auth_user_payload", None)
    return {"user_id": payload["user_id"] if payload else None}


def _middleware_stack() -> FastAPI:
    api = FastAPI()
    api.get(PROBE)(_probe)
    api.add_middleware(ABACMiddleware, phase=2)
    return api


def _dependency_stack() -> FastAPI:
    api = FastAPI(dependencies=[Depends(require_authenticated)])
    api.get(PROBE)(_probe)
    return api


@pytest.fixture(params=[_middleware_stack, _dependency_stack],
                ids=["abac_middleware", "require_authenticated"])
def client(request) -> TestClient:
    return TestClient(request.param())


@pytest.fixture
def lookups(isolated_store, monkeypatch) -> list[str]:
    """Every e-mail the demo fallback asked for. Empty means it was never consulted."""
    asked: list[str] = []

    def stub(email: str):
        asked.append(email)
        return dict(SEEDED_USER) if email.lower() == DEMO_EMAIL else None

    # The middleware holds its own reference; route_security imports at call time.
    monkeypatch.setattr(abac_middleware, "get_user_payload_by_email", stub)
    monkeypatch.setattr(auth, "get_user_payload_by_email", stub)
    monkeypatch.setattr(settings, "GEX_DEMO_MODE", True)
    return asked


def _token() -> str:
    token, _ = create_access_token({
        "user_id": BEARER_USER_ID,
        "email": "bearer-probe@example.com",
        "user_name": "Bearer Probe",
        "company_id": "bearer_probe_co",
        "company_name": "bearer_probe_co",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "clearance_level": "STANDARD",
        "jurisdiction": "DE",
        "kyc_status": "VERIFIED",
        "nda_signed_with": [],
        "assigned_audits": [],
        "actor_type_per_project": {},
    })
    return token


def _b64url(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _refused_authorization(kind: str, monkeypatch) -> str:
    if kind == "forged_unsigned":
        # A genuine token's claims under alg=none with no signature — the live measurement.
        claims = _token().split(".")[1]
        return f"Bearer {_b64url({'alg': 'none', 'typ': 'JWT'})}.{claims}."
    if kind == "expired":
        # Correctly signed, past its exp: the tab-left-open case.
        monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -5)
        return f"Bearer {_token()}"
    if kind == "garbage":
        return "Bearer not-a-jwt"
    if kind == "non_bearer_scheme":
        return "Basic ZGVtbzpkZW1vMTIzNA=="
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["forged_unsigned", "expired", "garbage", "non_bearer_scheme"])
def test_a_failed_credential_plus_demo_headers_is_401(client, lookups, monkeypatch, kind):
    r = client.get(PROBE, headers={
        "Authorization": _refused_authorization(kind, monkeypatch), **DEMO_HEADERS,
    })
    assert r.status_code == 401, (
        f"a {kind} Authorization header with x-demo-user was answered {r.status_code} "
        f"as {r.json().get('user_id')!r} — a rejected credential fell through to the "
        "demo header, so a dead session is served and the frontend cannot see it"
    )
    assert lookups == [], "the demo lookup was consulted although a credential was presented"


def test_demo_headers_alone_still_resolve_the_seeded_user(client, lookups):
    r = client.get(PROBE, headers=DEMO_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == SEEDED_USER["user_id"]
    assert lookups == [DEMO_EMAIL]


def test_a_valid_bearer_wins_over_the_demo_headers(client, lookups):
    r = client.get(PROBE, headers={"Authorization": f"Bearer {_token()}", **DEMO_HEADERS})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == BEARER_USER_ID
    assert lookups == []


def test_demo_headers_are_refused_when_demo_mode_is_off(client, lookups, monkeypatch):
    monkeypatch.setattr(settings, "GEX_DEMO_MODE", False)
    r = client.get(PROBE, headers=DEMO_HEADERS)
    assert r.status_code == 401, (
        f"GEX_DEMO_MODE=False answered demo headers {r.status_code} "
        f"as {r.json().get('user_id')!r}"
    )
