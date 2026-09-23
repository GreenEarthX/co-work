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
from typing import Any, NamedTuple, Optional

# Grants visibility of every tenant's rows. Not a company — an escalation.
PLATFORM_ADMIN = "PLATFORM_ADMIN"

# What a connection gets when no caller can be established. Matches no
# tenant-scoped RLS policy, so the absence of identity reveals nothing.
NO_TENANT_CONTEXT = "__no_tenant_context__"

# The same idea one axis down, for OWNER-SCOPED tables (canvas documents, a
# user's plants, their equipment equations). An owner policy compared against
# this matches nothing.
#
# The COLONS are load-bearing. `_safe_user` accepts `[A-Za-z0-9_.@-]`, so a
# sentinel spelled `__no_user_context__` would be a legal user_id shape — and a
# value that can be spelled can be registered, or written into an owner column,
# and would then match every row filed under "no caller". A colon is outside
# that whitelist, so this string cannot be a user id, by construction rather
# than by convention. (`NO_TENANT_CONTEXT` predates this and is still spellable
# under the company whitelist; it is not changed here because altering the
# tenant sentinel is a separate, wider change.)
NO_USER_CONTEXT = "__no:user:context__"

_current_company: ContextVar[Optional[str]] = ContextVar(
    "gex_current_company", default=None
)

# Deliberately a SECOND variable rather than a field on the first. The tenant
# answers "which company's rows", the user answers "whose own rows", and the
# two are not interchangeable: PLATFORM_ADMIN is a tenant escalation and has no
# meaning here. An admin is still exactly one user, so an owner-scoped policy
# must not widen because the caller happens to be staff — that would make
# `is_platform_admin` a silent read of everyone's private work.
_current_user: ContextVar[Optional[str]] = ContextVar(
    "gex_current_user", default=None
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


def user_from_payload(payload: Optional[dict]) -> Optional[str]:
    """The single rule for turning a verified payload into an owner identity.

    `user_id`, never `email` and never the directory's `member_id`: those are
    three different identifiers for a person and the platform already paid for
    conflating them once. Owner columns (`canvas_blobs.owner_user_id`,
    `user_plants.owner_user_id`) hold `auth_users.user_id`, so that is what an
    owner policy must be able to compare against.

    Unlike `company_from_payload` there is no `is_platform_admin` branch. Staff
    are not a user; they are a user who is also staff.
    """
    if not payload:
        return None
    return payload.get("user_id") or None


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


def set_current_user(user_id: Optional[str]) -> Token:
    """Bind the owner identity for this request."""
    return _current_user.set(user_id)


def reset_current_user(token: Token) -> None:
    """Unbind, in a `finally` — same reasoning as `reset_current_company`."""
    try:
        _current_user.reset(token)
    except ValueError:
        pass


def current_user() -> Optional[str]:
    """The bound user, or None if there is no authenticated caller."""
    return _current_user.get()


class BoundIdentity(NamedTuple):
    """The tokens for one request's bindings. Both are reset together: a
    request that unbound its tenant but kept its user — or the reverse — would
    leave a pooled worker holding half an identity."""
    company: Token
    user: Token


def bind_from_request(request: Any) -> BoundIdentity:
    """Derive tenant AND user from the request and bind both.

    One derivation, one payload, one place — the same reason this module exists
    for the tenant. Returns the tokens to pass to `reset_identity`.
    """
    payload = payload_from_request(request)
    return BoundIdentity(
        company=set_current_company(company_from_payload(payload)),
        user=set_current_user(user_from_payload(payload)),
    )


def reset_identity(tokens: Optional[BoundIdentity]) -> None:
    """Unbind both, in a `finally`. Tolerates None so the caller does not have
    to know whether binding got as far as happening."""
    if tokens is None:
        return
    reset_current_company(tokens.company)
    reset_current_user(tokens.user)
