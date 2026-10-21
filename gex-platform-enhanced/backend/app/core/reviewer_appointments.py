"""
Reviewer appointments — who may verify evidence on a project.
=============================================================
Owner decision 2026-10-21 (JML): **GEX staff appoint, on the instruction of a
named party** — the lender, grant body, investor or insurer whose decision
relies on the gate. GEX administers the appointment, as it vets accounts; it
still verifies nothing itself.

Why this module exists: verification requires an ASSIGNED reviewer
(abac.reviewer_gates — the role on the project AND the project among the
user's assigned audits), and on PostgreSQL the reviewer's company also needs a
project_access row or RLS refuses its write. Until now only the account seeding
in core/auth.py wrote those records, so no reviewer could be appointed and no
evidence could be verified on any project.

An appointment writes three records in ONE transaction:
    auth_user_project_roles   (user, project, reviewer role)
    auth_users.assigned_audits_json   += project
    project_access   (project, company, role, access_role='REVIEWER')   PostgreSQL only

Refusals — every one fails closed:
    the role is not a reviewer role (abac.REVIEWER_GATES)
    no instructing party, or no sha256 of the instruction document
    the project, or its owner, is unknown
    the appointee is unknown or not ACTIVE
    the appointer appoints itself
    the appointee belongs to the project owner's company   (owner never verifies)
    the instructing party is the project owner             (owner never picks its verifier)
    the appointee is GEX staff or a GEX account            (GEX verifies nothing)
    the appointment already exists
    PostgreSQL: the appointee's company is not a registered tenant

The functions here take a connection and never commit: the route commits after
the audit event is written, and tests can roll back.

The appointment takes effect at the reviewer's next sign-in: the access token
carries roles and assigned audits from the moment it was issued.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.abac import REVIEWER_GATES
from app.core.project_registry import company_slug

REVIEWER_ROLES: frozenset[str] = frozenset(at.value for at in REVIEWER_GATES)
ACCESS_ROLE = "REVIEWER"
GEX_COMPANY_ID = "greenearthx"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class AppointmentRefused(Exception):
    status: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def gates_for(role: str) -> list[str]:
    from app.core.abac import ActorType

    return sorted(REVIEWER_GATES[ActorType(role)], key=lambda g: int(g[1:]))


def _account(conn, user_id: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM auth_users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def _audits(account: dict) -> list[str]:
    try:
        return list(json.loads(account.get("assigned_audits_json") or "[]"))
    except (TypeError, ValueError):
        return []


def _has_role(conn, user_id: str, project_id: str, role: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM auth_user_project_roles WHERE user_id = ? AND project_id = ? AND actor_type = ?",
        (user_id, project_id, role),
    ).fetchone() is not None


def appoint(conn, *, project_id: str, owner_company_id: Optional[str], appointee_user_id: str,
            role: str, appointer: dict, instructed_by: str, instruction_sha256: str,
            write_project_access: bool) -> dict[str, Any]:
    """Validate and write one appointment. Raises AppointmentRefused; never commits."""
    role = (role or "").strip().upper()
    if role not in REVIEWER_ROLES:
        raise AppointmentRefused(422, "NOT_A_REVIEWER_ROLE",
                                 f"{role or 'This role'} does not verify evidence. Reviewer roles: "
                                 + ", ".join(sorted(REVIEWER_ROLES)) + ".")
    instructed_by = (instructed_by or "").strip()
    if not instructed_by:
        raise AppointmentRefused(422, "INSTRUCTING_PARTY_REQUIRED",
                                 "Name the party that instructed this appointment: the lender, grant body, "
                                 "investor or insurer whose decision relies on the gate.")
    sha = (instruction_sha256 or "").strip().lower()
    if not _SHA256.match(sha):
        raise AppointmentRefused(422, "INSTRUCTION_DOCUMENT_REQUIRED",
                                 "Give the sha256 of the instruction document (64 hexadecimal characters).")
    if not owner_company_id:
        raise AppointmentRefused(404, "PROJECT_NOT_FOUND",
                                 f"{project_id!r} is unknown or has no owning company.")

    appointee = _account(conn, appointee_user_id)
    if appointee is None:
        raise AppointmentRefused(404, "APPOINTEE_NOT_FOUND", f"No account {appointee_user_id!r}.")
    if appointee.get("account_state") != "ACTIVE":
        raise AppointmentRefused(409, "APPOINTEE_NOT_ACTIVE",
                                 f"The account is {appointee.get('account_state')}; only a vetted, ACTIVE "
                                 "account can be appointed.")
    if appointee_user_id == appointer.get("user_id"):
        raise AppointmentRefused(403, "CANNOT_APPOINT_YOURSELF",
                                 "Separation of duties: the appointer cannot appoint itself.")
    company = appointee.get("company_id")
    if company == owner_company_id:
        raise AppointmentRefused(403, "OWNER_CANNOT_REVIEW",
                                 "The company that owns the project cannot review its own evidence.")
    if company_slug(instructed_by) == owner_company_id:
        raise AppointmentRefused(403, "OWNER_CANNOT_INSTRUCT",
                                 "The project owner cannot choose who verifies its evidence. The instruction "
                                 "must come from the party whose decision relies on the gate.")
    if company == GEX_COMPANY_ID or bool(appointee.get("is_platform_admin")):
        raise AppointmentRefused(403, "GEX_VERIFIES_NOTHING",
                                 "GEX enforces the evidence standard and verifies nothing itself; a GEX "
                                 "account cannot be appointed as a reviewer.")
    audits = _audits(appointee)
    if _has_role(conn, appointee_user_id, project_id, role) and project_id in audits:
        raise AppointmentRefused(409, "ALREADY_APPOINTED",
                                 f"{appointee_user_id} is already appointed as {role} on {project_id}.")
    if write_project_access and conn.execute(
            "SELECT 1 FROM tenants WHERE company_id = ?", (company,)).fetchone() is None:
        raise AppointmentRefused(409, "REVIEWER_COMPANY_NOT_REGISTERED",
                                 f"The reviewer's company {company!r} is not a registered organisation, so "
                                 "it cannot be given access to the project. Register it first.")

    if not _has_role(conn, appointee_user_id, project_id, role):
        conn.execute("INSERT INTO auth_user_project_roles (user_id, project_id, actor_type) VALUES (?, ?, ?)",
                     (appointee_user_id, project_id, role))
    if project_id not in audits:
        conn.execute("UPDATE auth_users SET assigned_audits_json = ? WHERE user_id = ?",
                     (json.dumps(audits + [project_id]), appointee_user_id))
    if write_project_access and conn.execute(
            "SELECT 1 FROM project_access WHERE project_id = ? AND company_id = ? AND actor_type = ? "
            "AND access_role = ?", (project_id, company, role, ACCESS_ROLE)).fetchone() is None:
        conn.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) "
                     "VALUES (?, ?, ?, ?, ?)", (project_id, company, role, ACCESS_ROLE, appointer.get("user_id")))

    return {"project_id": project_id, "user_id": appointee_user_id, "user_name": appointee.get("user_name"),
            "company_id": company, "role": role, "gates": gates_for(role),
            "instructed_by": instructed_by, "instruction_sha256": sha,
            "appointed_by": appointer.get("user_id"), "effective": "at the reviewer's next sign-in"}


def revoke(conn, *, project_id: str, appointee_user_id: str, role: str,
           write_project_access: bool) -> dict[str, Any]:
    """Remove one appointment. The project leaves the assigned audits only when the
    user holds no other reviewer role on it, and the company's REVIEWER access row
    goes only when no colleague still holds that role there. Never commits."""
    role = (role or "").strip().upper()
    if role not in REVIEWER_ROLES or not _has_role(conn, appointee_user_id, project_id, role):
        raise AppointmentRefused(404, "NOT_APPOINTED",
                                 f"{appointee_user_id} is not appointed as {role or '?'} on {project_id}.")
    appointee = _account(conn, appointee_user_id) or {}
    conn.execute("DELETE FROM auth_user_project_roles WHERE user_id = ? AND project_id = ? AND actor_type = ?",
                 (appointee_user_id, project_id, role))
    still_reviewer = any(_has_role(conn, appointee_user_id, project_id, r) for r in REVIEWER_ROLES)
    audits = _audits(appointee)
    if not still_reviewer and project_id in audits:
        conn.execute("UPDATE auth_users SET assigned_audits_json = ? WHERE user_id = ?",
                     (json.dumps([a for a in audits if a != project_id]), appointee_user_id))
    company = appointee.get("company_id")
    if write_project_access and company:
        colleague = conn.execute(
            "SELECT 1 FROM auth_user_project_roles r JOIN auth_users u ON u.user_id = r.user_id "
            "WHERE r.project_id = ? AND r.actor_type = ? AND u.company_id = ?",
            (project_id, role, company)).fetchone()
        if colleague is None:
            conn.execute("DELETE FROM project_access WHERE project_id = ? AND company_id = ? AND actor_type = ? "
                         "AND access_role = ?", (project_id, company, role, ACCESS_ROLE))
    return {"project_id": project_id, "user_id": appointee_user_id, "company_id": company, "role": role,
            "still_assigned": still_reviewer}


def list_appointments(conn, project_id: str) -> list[dict[str, Any]]:
    """Current reviewers on a project: a reviewer role AND the project among the audits."""
    placeholders = ", ".join("?" for _ in REVIEWER_ROLES)
    rows = conn.execute(
        "SELECT r.user_id, r.actor_type, u.user_name, u.company_id, u.company_name, u.assigned_audits_json "
        f"FROM auth_user_project_roles r JOIN auth_users u ON u.user_id = r.user_id "
        f"WHERE r.project_id = ? AND r.actor_type IN ({placeholders}) ORDER BY r.actor_type, r.user_id",
        (project_id, *sorted(REVIEWER_ROLES))).fetchall()
    out = []
    for row in rows:
        row = dict(row)
        if project_id not in _audits(row):
            continue   # a role without the assignment verifies nothing
        out.append({"user_id": row["user_id"], "user_name": row["user_name"], "company_id": row["company_id"],
                    "company_name": row["company_name"], "role": row["actor_type"],
                    "gates": gates_for(row["actor_type"])})
    return out
