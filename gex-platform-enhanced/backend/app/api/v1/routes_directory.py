"""
Staff directory — the backend replacement for five anonymous Supabase reads.

Increment 1 of `docs/supabase-cutover-endpoints.md`. `useTeamData` fetched
`teams`, `roles`, `team_users`, `permission_gates` and `user_gate_status`
directly from PostgREST under the anon key shipped in the bundle. Measured
2026-09-19: all five answered an unauthenticated request, `team_users`
including 19 people's email and phone numbers.

THE TWO RULES THIS ROUTER EXISTS TO KEEP

1. No identity, no directory. Anonymous callers get 401 — from the app-wide
   `require_authenticated` dependency in `main.py`, and again from the local
   check here, because a router that is safe only while it is mounted in one
   particular app is not safe.

2. The internal directory is for GEX staff, full stop. **Corrected 2026-09-20**
   after a live check: the first version admitted any authenticated caller to
   the org chart, withholding only addresses. That let an ETFuels counterparty
   read GEX's teams, roles and permission gates. The rule is that no user of a
   paying customer may read GEX's internal directory **in any instance**, so a
   non-staff caller now gets **403 and no rows at all**.

   Scoping by organisation instead was considered and rejected on the data:
   `organisation` is null in 14 of the 19 directory rows and holds values like
   "QA Verified" in others, so a match would silently admit people it could not
   classify. Fail closed.

   `has_platform_admin_access` is the check, and it is the same one
   `assert_activator_is_gex_staff` makes — in this codebase GEX staff *is*
   `is_platform_admin`. One call, not two that could drift apart.

3. The redaction rule stays, underneath the access rule. `email` and `phone`
   are OMITTED — not nulled — for a reader without staff rights. Today nobody
   reaches the store without them, so the path is defence in depth: if read
   access is ever widened (to a caller's own organisation, say), addresses do
   not leak by default with it. `tests/test_directory_endpoints.py` pins the
   store-level redaction directly, so it cannot rot unnoticed.

The three endpoints mirror how the hook actually fetches: `/overview` replaces
five parallel round trips with one, and `/members` and `/gate-status` exist
because the hook exposes exactly those two as individual refetches.

Shapes are the frontend's existing `TeamRow`, `RoleRow`, `TeamUserRow`,
`PermissionGate` and `GateStatusRow`, unchanged — this increment moves the
transport, not the contract.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.core import directory_store
from app.core.auth import has_platform_admin_access

router = APIRouter()


def _payload(request: Request) -> dict[str, Any]:
    """The authenticated identity, or 401. Defence in depth: `main.py` already
    applies `require_authenticated` app-wide."""
    payload = getattr(request.state, "auth_user_payload", None)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return payload


def _require_gex_staff(request: Request) -> dict[str, Any]:
    """
    403 for anyone who is not GEX staff. A customer's user may not read GEX's
    internal directory at all — not the names, not the teams, not the gates.
    """
    payload = _payload(request)
    if not has_platform_admin_access(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The GEX internal directory is not readable outside GEX staff",
        )
    return payload


@router.get("/overview")
def directory_overview(request: Request) -> dict[str, Any]:
    """Everything the Team screen needs, in one call."""
    include_pii = has_platform_admin_access(_require_gex_staff(request))
    return {
        "teams": directory_store.list_teams(),
        "roles": directory_store.list_roles(),
        "members": directory_store.list_members(include_pii=include_pii),
        "gates": directory_store.list_gates(),
        "gate_statuses": directory_store.list_gate_status(),
        "personal_data_included": include_pii,
    }


@router.get("/members")
def directory_members(request: Request) -> list[dict[str, Any]]:
    """The directory alone — the hook's `refetchUsers`."""
    return directory_store.list_members(
        include_pii=has_platform_admin_access(_require_gex_staff(request)))


@router.get("/gate-status")
def directory_gate_status(request: Request) -> list[dict[str, Any]]:
    """Gate holdings alone — the hook's `refetchGateStatuses`. It carries no
    addresses, but it maps GEX people to internal process gates, which is
    exactly the internal structure rule 2 exists to keep in."""
    _require_gex_staff(request)
    return directory_store.list_gate_status()
