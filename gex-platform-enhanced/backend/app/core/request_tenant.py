"""
The authenticated caller's tenant, for the duration of one request.
===================================================================
There are two ways application code reaches the database:

    Depends(get_db)        SQLAlchemy   — 109 call sites
    *_connection()         the shim     —  64 call sites

Both must scope to the SAME tenant, derived the SAME way, or "tenant isolation"
means two different things depending on which path a route happens to use. This
module is that single derivation, plus the request-scoped carrier the shim needs
(it has no `Request` to read).

TWO DEFECTS THIS MODULE CLOSES (found 2026-08-10)
-------------------------------------------------
1. The shim had no way to learn the caller at all. Every accessor defaulted to
   PLATFORM_ADMIN and not one of the 64 call sites overrode it, so on the day
   the switches flipped, all 64 would have read every tenant's rows. The default
   is now a deny sentinel; this module is how a real tenant reaches it.

2. `ABACMiddleware` set `request.state.auth_user_payload`, but
   `db/session.py::_company_id_from_request` read `request.state.user_payload` —
   a different attribute. `route_security` sets both, but it is imported in only
   three places. So for most of the 109 SQLAlchemy sites the payload was never
   found and the tenant resolved to 'GUEST'.

   Under today's `gex_user` (SUPERUSER, BYPASSRLS) neither defect is visible:
   RLS is not evaluated at all. Under `gex_app`, defect 1 exposes everything and
   defect 2 hides everything. They would have been discovered as an outage and a
   breach respectively, on the same afternoon.

`payload_from_request` therefore reads BOTH names, and stays that way until one
of them is retired deliberately.

PROPAGATION
-----------
`ABACMiddleware` is a Starlette `BaseHTTPMiddleware`, which runs the downstream
app in a child task. A child task copies the context at spawn time, so a value
set in `dispatch` before `call_next` IS visible downstream — but a value set
downstream is NOT visible back in the middleware. Setting flows down only, which
is the direction needed here. This is asserted end-to-end in
`tests/test_request_tenant.py` rather than assumed, because it depends on
Starlette internals.

Work that outlives the request — background tasks, manually spawned threads —
does not inherit it, and so falls back to the deny sentinel. That is correct: a
job with no caller has no tenant.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Optional

# Grants visibility of every tenant's rows. Not a company — an escalation.
PLATFORM_ADMIN = "PLATFORM_ADMIN"

# What a connection gets when no caller can be established. Matches no
# tenant-scoped RLS policy, so the absence of identity reveals nothing.
NO_TENANT_CONTEXT = "__no_tenant_context__"

_current_company: ContextVar[Optional[str]] = ContextVar(
    "gex_current_company", default=None
)


def payload_from_request(request: Any) -> Optional[dict]:
    """The verified JWT payload, under whichever attribute set it.

    `ABACMiddleware` writes `auth_user_payload`; `route_security` writes both.
    Reading only one of them was defect 2 above.
    """
    state = getattr(request, "state", None)
    if state is None:
        return None
    return (getattr(state, "user_payload", None)
            or getattr(state, "auth_user_payload", None))


def company_from_payload(payload: Optional[dict]) -> Optional[str]:
    """The single rule for turning a verified payload into a tenant.

    `is_platform_admin` maps to full visibility, so it is an authorization
    decision carried in a token — see the handoff's open items.
    """
    if not payload:
        return None
    if payload.get("is_platform_admin"):
        return PLATFORM_ADMIN
    return payload.get("company_id") or None


def set_current_company(company_id: Optional[str]) -> Token:
    """Bind the tenant for this request. Pass the token to `reset_current_company`."""
    return _current_company.set(company_id)


def reset_current_company(token: Token) -> None:
    """Unbind, in a `finally`. Without this a pooled worker could serve the next
    request with the previous caller's tenant still bound."""
    try:
        _current_company.reset(token)
    except ValueError:
        # Token belongs to a different context (the reset is happening in
        # another task). The context dies with that task, so nothing leaks.
        pass


def current_company() -> Optional[str]:
    """The bound tenant, or None if there is no authenticated caller."""
    return _current_company.get()


def bind_from_request(request: Any) -> Token:
    """Derive the tenant from the request and bind it. Returns the reset token."""
    return set_current_company(company_from_payload(payload_from_request(request)))
