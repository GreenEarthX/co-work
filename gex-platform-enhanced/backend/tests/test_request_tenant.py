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

from app.core.db_backend import _tenant_context, _user_context
from app.core.request_tenant import (
    NO_TENANT_CONTEXT,
    NO_USER_CONTEXT,
    PLATFORM_ADMIN,
    company_from_payload,
    current_company,
    current_user,
    payload_from_request,
    reset_current_company,
    set_current_company,
    user_from_payload,
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
            # The owner axis, resolved the same three ways.
            "user_contextvar": current_user(),
            "user_shim": _user_context(None),
            "user_sqlalchemy": user_from_payload(payload_from_request(request)),
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
    assert "reset_identity" in called, (
        "dispatch no longer unbinds the tenant in a finally. Nothing in the "
        "HTTP tests will catch this — per-request task contexts hide it — but "
        "any in-process or context-reusing caller would inherit the previous "
        "caller's tenant."
    )


# ── The owner axis (added 2026-09-22, before canvas/plants move) ─────────────
#
# Canvas documents, plants and equipment equations are OWNER-scoped, not
# company-scoped. Until this existed there was no `app.current_user_id`, so
# migration 042 left its user-scoped tables admin-only and said why. These
# tests are what that GUC has to be worth before an owner-only policy can rest
# on it.

def test_the_user_reaches_the_route_handler_and_both_paths_agree():
    r = TestClient(_app()).get("/api/v1/__probe__",
                               headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_contextvar"] == "probe_user", (
        "the user ContextVar set in ABACMiddleware did not reach the handler"
    )
    assert body["user_shim"] == body["user_sqlalchemy"] == "probe_user", (
        f"the two paths disagree on the owner: shim={body['user_shim']!r} "
        f"sqlalchemy={body['user_sqlalchemy']!r} — an owner-only policy would "
        "mean different things depending on which helper a route used"
    )


def test_a_platform_admin_is_still_just_one_user():
    """THE decision this axis encodes, asserted rather than trusted.

    `is_platform_admin` widens the TENANT to PLATFORM_ADMIN. It must not widen
    the OWNER: staff are a user who is also staff, and an owner-only policy
    that quietly admitted admins would make every private canvas readable by
    anyone holding the flag.
    """
    r = TestClient(_app()).get("/api/v1/__probe__",
                               headers={"Authorization": f"Bearer {_token(admin=True)}"})
    body = r.json()
    assert body["shim"] == PLATFORM_ADMIN, "tenant escalation stopped working"
    assert body["user_shim"] == "probe_user", (
        f"an admin token resolved the owner axis to {body['user_shim']!r} — "
        "platform admin must not be an owner-axis escalation"
    )
    assert body["user_shim"] != PLATFORM_ADMIN


def test_work_outside_a_request_owns_nothing():
    """A background job has no caller, so it owns no rows — the deny sentinel,
    never a blank or a NULL that an owner comparison would silently widen."""
    assert current_user() is None
    assert _user_context(None) == NO_USER_CONTEXT


def test_an_explicit_owner_still_beats_the_bound_one():
    """Same precedence as the tenant: explicit argument → bound caller →
    sentinel. The copiers rely on this to write one owner's rows at a time."""
    from app.core.request_tenant import set_current_user, reset_current_user

    token = set_current_user("bound_user")
    try:
        assert _user_context(None) == "bound_user"
        assert _user_context("explicit_user") == "explicit_user"
    finally:
        reset_current_user(token)
    assert _user_context(None) == NO_USER_CONTEXT


def test_the_middleware_unbinds_the_user_too():
    """Both axes are reset together. A pooled worker holding half an identity —
    tenant cleared, owner still set — is the failure this guards."""
    client = TestClient(_app())
    client.get("/api/v1/__probe__", headers={"Authorization": f"Bearer {_token()}"})
    assert current_user() is None, "the owner axis leaked out of the request"
    assert current_company() is None, "the tenant leaked out of the request"


@pytest.mark.parametrize("hostile", [
    "bob'; SET app.current_user_id = 'alice",
    "alice' OR '1'='1",
    "owner\nSET app.current_company_id = 'PLATFORM_ADMIN",
])
def test_a_hostile_user_id_is_refused_not_escaped(hostile):
    """`SET` cannot take a bind parameter, so the value is interpolated. A value
    that is not a user id is REFUSED — not escaped, not silently swapped for the
    sentinel, which would hide a broken token behind an empty screen."""
    from app.core.db_backend import _safe_user

    with pytest.raises(ValueError):
        _safe_user(hostile)


def test_the_deny_sentinel_cannot_collide_with_a_real_user_id():
    """The sentinel must not be spellable as a user id, or a crafted account
    could impersonate 'no caller' — or worse, match rows written under it."""
    import re

    assert not re.fullmatch(r"[A-Za-z0-9_.@-]{1,190}", NO_USER_CONTEXT), (
        "NO_USER_CONTEXT is a legal user_id shape — it could be registered"
    )
