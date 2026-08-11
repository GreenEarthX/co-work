"""
Project-scoped finance entitlements (Ticket 1a).
================================================
Replaces the global FINANCE_REVIEW capability with a per-project, auditable,
revocable grant. Sensitive project-finance screens/endpoints (DSCR sensitivity,
price decomposition, drawdown/CP timeline) authorise a user iff:

    is_finance_role(identity)                      # standing role entitlement
    OR active project-scoped FINANCE_REVIEW grant  # explicit per-project grant

Standing finance roles (entitled across the projects ABAC already lets them see):
    business_function ∈ {FINANCE_TREASURY, EXECUTIVE}
    service_type      ∈ {BANK, DFI, INSURER}

Everyone else (Engineering, Operations, Commercial, Logistics, Certifier, Legal)
is denied UNLESS explicitly granted FINANCE_REVIEW *for that specific project*.

DEV-ONLY fallback: a global FINANCE_REVIEW capability is honoured only when
GEX_DEV_GLOBAL_FINANCE_REVIEW=1 AND the environment is not production. It is OFF
by default and must never silently grant all-project access in production.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from app.core.config import settings

# ── DB path (mirrors app.core.auth) ──────────────────────────────────────────
DB_PATH = settings.SQLITE_DB_PATH

# ── Standing role entitlement sets ───────────────────────────────────────────
FINANCE_FUNCTIONS = {"FINANCE_TREASURY", "EXECUTIVE"}
FINANCE_SERVICE_TYPES = {"BANK", "DFI", "INSURER"}
FINANCE_REVIEW = "FINANCE_REVIEW"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    """
    Slice-6b-1 connection — SQLite or PostgreSQL by configuration
    (ENTITLEMENT_DB_BACKEND). The SQL is unchanged; the shim translates
    placeholders and sets the RLS tenant context.
    """
    from app.core.db_backend import PLATFORM_ADMIN, entitlement_connection

    # Explicit admin: entitlement rows are read WHILE deciding what a caller
    # may see, so they cannot be filtered by that decision without circularity.
    return entitlement_connection(company_id=PLATFORM_ADMIN)


def init_entitlements_db() -> None:
    """
    Create the entitlement + audit tables. Call from main.py startup.

    SQLite only — on PostgreSQL the schema is owned by alembic (migration 037),
    which also declares the action CHECK and the RLS policies. Creating the
    tables from here would bypass both.
    """
    from app.core.db_backend import entitlement_is_postgres

    if entitlement_is_postgres():
        return
    conn = _conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_entitlements (
                entitlement_id TEXT PRIMARY KEY,
                user_id        TEXT NOT NULL,
                project_id     TEXT NOT NULL,
                capability     TEXT NOT NULL DEFAULT 'FINANCE_REVIEW',
                granted_by     TEXT NOT NULL,
                granted_at     TEXT NOT NULL,
                reason         TEXT,
                expires_at     TEXT,
                revoked_at     TEXT,
                revoked_by     TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fe_user_proj "
            "ON finance_entitlements(user_id, project_id, capability)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entitlement_audit (
                audit_id   TEXT PRIMARY KEY,
                at         TEXT NOT NULL,
                action     TEXT NOT NULL,   -- granted | revoked | access_allowed | access_denied
                user_id    TEXT,
                project_id TEXT,
                actor      TEXT,            -- who performed the action
                basis      TEXT,            -- role | project_entitlement | dev_global | none
                detail     TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _audit(action: str, *, user_id: str | None, project_id: str | None,
           actor: str | None = None, basis: str | None = None, detail: str | None = None) -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO entitlement_audit (audit_id, at, action, user_id, project_id, actor, basis, detail) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), _iso(_now()), action, user_id, project_id, actor, basis, detail),
        )
        conn.commit()
    finally:
        conn.close()


# ── Status computation ───────────────────────────────────────────────────────
def _row_status(row: sqlite3.Row, now: datetime) -> str:
    if row["revoked_at"]:
        return "revoked"
    if row["expires_at"]:
        try:
            if datetime.fromisoformat(row["expires_at"]) <= now:
                return "expired"
        except ValueError:
            pass
    return "active"


# ── Grant / revoke ───────────────────────────────────────────────────────────
def grant_entitlement(
    *, user_id: str, project_id: str, granted_by: str,
    capability: str = FINANCE_REVIEW, reason: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    eid = str(uuid.uuid4())
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO finance_entitlements "
            "(entitlement_id, user_id, project_id, capability, granted_by, granted_at, reason, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (eid, user_id, project_id, capability, granted_by, _iso(_now()), reason, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    _audit("granted", user_id=user_id, project_id=project_id, actor=granted_by,
           basis="project_entitlement", detail=f"{capability}; reason={reason}; expires_at={expires_at}")
    return get_entitlement(eid)  # type: ignore[return-value]


def revoke_entitlement(entitlement_id: str, *, revoked_by: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM finance_entitlements WHERE entitlement_id=?", (entitlement_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE finance_entitlements SET revoked_at=?, revoked_by=? WHERE entitlement_id=?",
            (_iso(_now()), revoked_by, entitlement_id),
        )
        conn.commit()
    finally:
        conn.close()
    _audit("revoked", user_id=row["user_id"], project_id=row["project_id"], actor=revoked_by,
           basis="project_entitlement", detail=entitlement_id)
    return get_entitlement(entitlement_id)


def get_entitlement(entitlement_id: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM finance_entitlements WHERE entitlement_id=?", (entitlement_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(row)
    d["status"] = _row_status(row, _now())
    return d


def list_entitlements(*, user_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM finance_entitlements WHERE 1=1"
    args: list[Any] = []
    if user_id:
        q += " AND user_id=?"; args.append(user_id)
    if project_id:
        q += " AND project_id=?"; args.append(project_id)
    q += " ORDER BY granted_at DESC"
    conn = _conn()
    try:
        rows = conn.execute(q, args).fetchall()
    finally:
        conn.close()
    now = _now()
    out = []
    for r in rows:
        d = dict(r); d["status"] = _row_status(r, now); out.append(d)
    return out


def has_active_project_entitlement(user_id: str, project_id: str, capability: str = FINANCE_REVIEW) -> bool:
    """True iff the user holds an ACTIVE (not revoked, not expired) grant for this project."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM finance_entitlements WHERE user_id=? AND project_id=? AND capability=?",
            (user_id, project_id, capability),
        ).fetchall()
    finally:
        conn.close()
    now = _now()
    return any(_row_status(r, now) == "active" for r in rows)


# ── Standing role check ──────────────────────────────────────────────────────
def is_finance_role(*, business_function: str | None, service_type: str | None) -> bool:
    """Role ELIGIBILITY only — not authorization. Must be paired with a project
    relationship (see has_project_relationship). Role alone never grants access."""
    return (business_function in FINANCE_FUNCTIONS) or (service_type in FINANCE_SERVICE_TYPES)


def has_project_relationship(company_id: str | None, project_id: str | None) -> bool:
    """
    True iff the user's company has a real relationship to THIS project — owner,
    associated company, mandated lender, or mandated insurer — per the canonical
    project registry. Also validates the project exists (unknown id → False).
    """
    if not company_id or not project_id:
        return False
    try:
        from app.core.project_registry import get_project_profile, company_slug
    except Exception:
        return False
    profile = get_project_profile(project_id)
    if not profile:
        return False  # unknown / invalid project_id
    cid = company_slug(company_id)
    related = (
        profile.stakeholder_company_ids        # owner + associated
        | profile.mandated_lender_ids
        | profile.mandated_insurer_ids
    )
    return cid in related


def project_exists(project_id: str | None) -> bool:
    try:
        from app.core.project_registry import get_project_profile
        return get_project_profile(project_id) is not None
    except Exception:
        return False


def _dev_global_enabled() -> bool:
    """Dev-only fallback flag. OFF by default; force-OFF in production."""
    env = os.getenv("GEX_ENV", "development").lower()
    if env in {"production", "prod"}:
        return False
    return os.getenv("GEX_DEV_GLOBAL_FINANCE_REVIEW", "0") == "1"


# ── The authorisation decision ───────────────────────────────────────────────
def check_finance_access(
    *, user_id: str, company_id: str | None, project_id: str | None,
    business_function: str | None, service_type: str | None,
    capabilities: list[str] | None = None,
) -> tuple[bool, str, str]:
    """
    Authorization for sensitive project-finance content.

        allowed = active project-scoped FINANCE_REVIEW grant
                  OR (qualified finance role AND relationship to THIS project)
                  OR (DEV-ONLY global FINANCE_REVIEW)

    Role ELIGIBILITY alone never grants access — a Bank/DFI/Insurer/Finance user
    sees a project only where it owns, is associated with, or is a mandated
    lender/insurer for that specific project, or holds an explicit grant.

    Returns (allowed, basis, reason).
    basis ∈ {project_entitlement, role+relationship, dev_global, none}.
    project_id is REQUIRED; it is validated against the project registry.
    """
    caps = capabilities or []

    # Project context is mandatory and must be a real project.
    if not project_id:
        return False, "none", "project context required (sensitive views are project-scoped)"

    # 1) Explicit project-scoped grant — works for anyone (incl. external reviewers).
    if has_active_project_entitlement(user_id, project_id, FINANCE_REVIEW):
        return True, "project_entitlement", f"active FINANCE_REVIEW grant for {project_id}"

    # 2) Qualified finance role AND a real relationship to THIS project.
    if is_finance_role(business_function=business_function, service_type=service_type):
        if not project_exists(project_id):
            return False, "none", f"unknown project_id '{project_id}'"
        if has_project_relationship(company_id, project_id):
            return True, "role+relationship", f"finance role with project relationship ({company_id}→{project_id})"
        return False, "none", f"finance role but no relationship/mandate/grant for {project_id}"

    # 3) DEV-ONLY global fallback (never in production).
    if FINANCE_REVIEW in caps and _dev_global_enabled():
        return True, "dev_global", "DEV-ONLY global FINANCE_REVIEW capability (not valid in production)"

    return False, "none", "no project-scoped grant; not a finance role with a relationship to this project"


def log_access(*, allowed: bool, user_id: str, project_id: str | None, basis: str, reason: str, route: str) -> None:
    """Audit a sensitive-screen / endpoint access decision."""
    _audit(
        "access_allowed" if allowed else "access_denied",
        user_id=user_id, project_id=project_id, actor=user_id, basis=basis,
        detail=f"route={route}; {reason}",
    )
