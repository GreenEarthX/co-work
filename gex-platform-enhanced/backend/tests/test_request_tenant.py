"""
The caller's tenant must reach BOTH database paths, identically.
================================================================
`Depends(get_db)` (109 sites) and the shim's `*_connection()` (64 sites) must
scope to the same tenant, derived the same way. Two defects made that false;
both were invisible under `gex_user` because SUPERUSER/BYPASSRLS means RLS is
never evaluated:

  1. The shim could not learn the caller at all — every accessor defaulted to
     PLATFORM_ADMIN and no call site overrode it. Fail-OPEN.
  2. ABACMiddleware set `request.state.auth_user_payload`; db/session.py read
     `request.state.user_payload`. Different attributes, so most SQLAlchemy
     sites resolved the tenant to 'GUEST'. Fail-CLOSED, but silently.

The load-bearing assumption is that a ContextVar set inside a Starlette
`BaseHTTPMiddleware` is visible in the downstream route handler. That depends on
Starlette running the child task with a copy of the context taken at spawn time.
It is true today, it is not documented API, and the whole design rests on it —
so it is asserted here against a real ASGI stack rather than reasoned about.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.db_backend import _tenant_context
from app.core.request_tenant import (
    NO_TENANT_CONTEXT,
    PLATFORM_ADMIN,
    company_from_payload,
    current_company,
    payload_from_request,
    reset_current_company,
    set_current_company,
)

COMPANY = "hamburgone_com"


def _app() -> FastAPI:
    """A real ASGI stack with the real middleware and a probe route."""
    from app.core.abac_middleware import ABACMiddleware

    api = FastAPI()

    @api.get("/api/v1/__probe__")
    async def probe(request: Request):
        # What each path would independently conclude about the caller.
        return {
            "contextvar": current_company(),
            "shim": _tenant_context(None, "probe"),
            "sqlalchemy": company_from_payload(payload_from_request(request)),
        }

    api.add_middleware(ABACMiddleware, phase=2)
    return api


def _token(company: str = COMPANY, admin: bool = False) -> str:
    from app.core.auth import create_access_token

    token, _ = create_access_token({
        "user_id": "probe_user",
        "email": "handoff-probe@example.com",
        "user_name": "Handoff Probe",
        "company_id": company,
        "company_name": company,
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "clearance_level": "STANDARD",
        "jurisdiction": "DE",
        "kyc_status": "VERIFIED",
        "nda_signed_with": [],
        "assigned_audits": [],
        "actor_type_per_project": {},
        "is_platform_admin": admin,
    })
    return token


# ── The propagation assumption, asserted ────────────────────────────────────

def test_the_tenant_set_in_middleware_reaches_the_route_handler():
    r = TestClient(_app()).get("/api/v1/__probe__",
                               headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contextvar"] == COMPANY, (
        "the ContextVar set in ABACMiddleware did not reach the route handler. "
        "Starlette's BaseHTTPMiddleware no longer propagates context downstream "
        "— the shim cannot learn the caller and every shim read will fail closed."
    )


def test_both_database_paths_agree_on_the_caller():
    """The whole point: one caller, one tenant, whichever path a route uses."""
    r = TestClient(_app()).get("/api/v1/__probe__",
                               headers={"Authorization": f"Bearer {_token()}"})
    body = r.json()
    assert body["shim"] == body["sqlalchemy"] == COMPANY, (
        f"the two paths disagree: shim={body['shim']!r} "
        f"sqlalchemy={body['sqlalchemy']!r}"
    )


def test_a_platform_admin_token_resolves_to_admin_on_both_paths():
    r = TestClient(_app()).get("/api/v1/__probe__",
                               headers={"Authorization": f"Bearer {_token(admin=True)}"})
    body = r.json()
    assert body["shim"] == body["sqlalchemy"] == PLATFORM_ADMIN


# ── Fail-closed properties ──────────────────────────────────────────────────

def test_an_unauthenticated_request_binds_no_tenant():
    r = TestClient(_app()).get("/api/v1/__probe__")
    assert r.status_code == 401, "the probe route is not actually protected"


def test_each_request_gets_its_own_tenant():
    """
    Two callers in sequence must each see themselves.

    NOTE ON WHAT THIS DOES AND DOES NOT PROVE. An earlier version of this test
    claimed the reset in dispatch's finally was what made it pass. Negative
    verification disproved that: deleting the reset changes nothing here,
    because each request is handled in its own asyncio task and a ContextVar set
    inside that task dies with it. Task-context isolation is the mechanism; the
    reset is defence-in-depth for any caller that does not get a fresh task
    (in-process ASGI invocation, a future server that reuses one). Both are
    worth having — but only one of them this test can see, and saying otherwise
    would have left a guardrail that passes for a reason nobody checked.

    The reset's continued existence is pinned separately, statically, below.
    """
    client = TestClient(_app())
    first = client.get("/api/v1/__probe__",
                       headers={"Authorization": f"Bearer {_token('hamburgone_com')}"})
    second = client.get("/api/v1/__probe__",
                        headers={"Authorization": f"Bearer {_token('etfuels_com')}"})
    assert first.json()["shim"] == "hamburgone_com"
    assert second.json()["shim"] == "etfuels_com", (
        "the second request saw the first request's tenant"
    )
    # And nothing survives into this test's own context.
    assert current_company() is None


def test_work_outside_a_request_has_no_tenant():
    """A background job has no caller, so it must reveal nothing rather than
    inherit whoever happened to run last."""
    assert current_company() is None
    assert _tenant_context(None, "background") == NO_TENANT_CONTEXT


def test_an_explicit_company_still_beats_the_bound_one():
    token = set_current_company("hamburgone_com")
    try:
        assert _tenant_context("etfuels_com", "probe") == "etfuels_com"
        assert _tenant_context(PLATFORM_ADMIN, "probe") == PLATFORM_ADMIN
    finally:
        reset_current_company(token)


# ── The attribute-name defect must not come back ────────────────────────────

@pytest.mark.parametrize("attr", ["user_payload", "auth_user_payload"])
def test_the_payload_is_found_under_either_state_attribute(attr):
    """
    ABACMiddleware writes auth_user_payload; route_security writes both. Reading
    only one was defect 2. If one name is ever retired, retire it deliberately —
    do not let this silently start returning None again.
    """
    class _State:
        pass

    class _Req:
        state = _State()

    req = _Req()
    setattr(req.state, attr, {"company_id": COMPANY})
    assert company_from_payload(payload_from_request(req)) == COMPANY


def test_the_middleware_sets_both_payload_attributes():
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           "abac_middleware.py").read_text()
    assigned = {
        t.attr
        for node in ast.walk(ast.parse(src)) if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Attribute) and t.attr.endswith("user_payload")
    }
    assert {"user_payload", "auth_user_payload"} <= assigned, (
        f"ABACMiddleware assigns only {assigned} — db/session.py and the shim "
        "read the other name and would resolve every caller to no tenant"
    )


def test_the_middleware_still_resets_the_tenant():
    """
    Static, because the HTTP-level test above cannot see this: per-task context
    isolation masks a missing reset. Asserted over the AST so the finally block
    cannot quietly become a no-op.
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           "abac_middleware.py").read_text()
    tree = ast.parse(src)
    dispatch = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "dispatch"), None)
    assert dispatch is not None, "ABACMiddleware.dispatch is gone"

    finallies = [t for n in ast.walk(dispatch) if isinstance(n, ast.Try)
                 for t in n.finalbody]
    called = {
        node.func.id
        for stmt in finallies for node in ast.walk(stmt)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "reset_current_company" in called, (
        "dispatch no longer unbinds the tenant in a finally. Nothing in the "
        "HTTP tests will catch this — per-request task contexts hide it — but "
        "any in-process or context-reusing caller would inherit the previous "
        "caller's tenant."
    )
