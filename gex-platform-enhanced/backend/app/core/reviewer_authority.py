"""Who may approve a TEA base case or a pathway claim (19 Nov 2026).

The legacy approval routes (/api/v1/tea/base-case/{claim}/approve and /claim/{claim}/approve)
took the approver from the `x-demo-user` header or the request body: a caller signed in as A
could approve as B, and no project authority was checked. Now:

  - the approver is the SIGNED-IN user (the token, via the middleware); a body naming someone
    else is refused, never used;
  - authority is per PROJECT: an appointment recorded in `auth_user_project_roles`
    (actor_type), of a company other than the project's owner;
  - a TEST fixture account (auth_users.activated_by 'TEST_FIXTURE_%') produces a review
    labelled TEST: it never counts as an independent review, so it unlocks no promotion and
    no publication.

Every lookup fails CLOSED: a store error refuses the approval (503), it never grants it.
"""
from __future__ import annotations

from typing import Optional

TEST_MARKER = "TEST_FIXTURE_%"


class AuthorityError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _rows(sql: str, params: dict) -> list[dict]:
    from app.core.projects_store import _rows_strict
    try:
        return _rows_strict(sql, params)
    except Exception as exc:  # noqa: BLE001 — fail closed
        raise AuthorityError(503, "AUTHORITY_UNREADABLE", f"Reviewer authority could not be read ({exc}).")


def signed_in(payload: Optional[dict], body_approver: Optional[str]) -> str:
    uid = (payload or {}).get("user_id")
    if not uid:
        raise AuthorityError(401, "NOT_SIGNED_IN", "Sign in to approve.")
    if body_approver and body_approver not in (uid, (payload or {}).get("email")):
        raise AuthorityError(422, "APPROVER_NOT_ACCEPTED", "The approver is the signed-in user; a request may not "
                             "name someone else.")
    return uid


def is_test_account(user_id: str) -> bool:
    return bool(_rows("SELECT 1 FROM auth_users WHERE user_id = :u AND activated_by LIKE :m",
                      {"u": user_id, "m": TEST_MARKER}))


def project_owner(project_id: str) -> Optional[str]:
    rows = _rows("SELECT owner_tenant_id FROM projects WHERE project_id = :p", {"p": project_id})
    return rows[0]["owner_tenant_id"] if rows else None


def appointed_as(user_id: str, project_id: str, actor_types: tuple) -> set:
    rows = _rows("SELECT actor_type FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p",
                 {"u": user_id, "p": project_id})
    return {r["actor_type"] for r in rows} & set(actor_types)


def review_basis(*, payload: dict, project_id: str, actor_types: tuple) -> str:
    """INDEPENDENT, or TEST for a test fixture account, or AuthorityError."""
    uid = payload["user_id"]
    owner = project_owner(project_id)
    if owner is None:
        raise AuthorityError(404, "PROJECT_NOT_FOUND", "No such project.")
    company = payload.get("company_id") or payload.get("tenant_id")
    if company == owner:
        raise AuthorityError(403, "OWNER_CANNOT_APPROVE", "The project owner's company cannot approve here; an "
                             "owner's internal review is recorded on the calculation chain, labelled as such.")
    if not appointed_as(uid, project_id, actor_types):
        raise AuthorityError(403, "NOT_APPOINTED", f"Only a reviewer appointed on this project as "
                             f"{' or '.join(actor_types)} may approve.")
    return "TEST" if is_test_account(uid) else "INDEPENDENT"
