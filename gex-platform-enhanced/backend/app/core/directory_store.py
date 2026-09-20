"""
Staff directory — teams, roles, permission gates, and who holds what.

WHY THIS EXISTS
---------------
The Team screen read five Supabase tables straight from the browser under the
anon key baked into `frontend/src/lib/backendClient.ts`. Measured 2026-09-19:
all five answered an anonymous request — including `team_users`, which is 19
real people with `email`, `full_name`, `phone` and `organisation`. The anon key
is in the shipped bundle, so "anonymous" means anyone.

This module is the replacement store. See
`docs/supabase-cutover-endpoints.md` §3 (increment 1).

THE IDENTITY QUESTION, AND WHY THIS SCHEMA DOES NOT ANSWER IT
-------------------------------------------------------------
`team_users` (19 rows) and `auth_users` (17 rows) describe overlapping people
in two places — the dual-identity defect on the register. Folding the directory
into `auth_users` is the right end state (one place where somebody is
deactivated), but the fold needs an email-by-email reconciliation that is a
decision, not a refactor.

So `directory_members.auth_user_id` is **nullable and unenforced**: it records
the account a directory member corresponds to, where one is known.
`reconcile_with_auth_users()` fills it by email and returns what did not match,
which is the measurement that decision needs. Until it is taken, this table is
a directory, NOT an authority — nothing here grants access to anything. The
permission gates recorded here describe GEX's internal process; the platform's
actual access control remains ABAC + entitlements.

`directory_gate_status.member_id` is deliberately NOT called `user_id`, though
the JSON contract still emits `user_id` for the frontend's sake. In Supabase
that column pointed at `team_users.id` — not at an authenticated user — and a
column named `user_id` that is not a user id is exactly how the dual-identity
problem spread.

POSTGRES
--------
Refused, on purpose. These rows are personal data; a `CREATE TABLE IF NOT
EXISTS` here would produce an unprotected table on a database where 89 of 98
tables are under FORCED RLS. Creating the PII table as the one exception, with
no policy, would repeat the mistake this module exists to undo. The RLS policy
belongs in an Alembic migration alongside the other governance slices. The
directory follows `GOVERNANCE_DB_BACKEND` rather than introducing a ninth
backend switch.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app.core.config import settings
from app.core.db_backend import governance_is_postgres
from app.core.ecosystem_store import PostgresMigrationRequired

# The columns that are personal data. Withheld from a caller who is not GEX
# staff — omitted from the payload entirely, never nulled, because an absent
# key cannot be misread as "no phone number on file".
PII_FIELDS = ("email", "phone")


def _conn() -> sqlite3.Connection:
    # Path read per call, not cached at import: `isolated_store` swaps
    # settings.SQLITE_DB_PATH per test module and a cached path would pin the
    # store to the development database.
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if governance_is_postgres():
        raise PostgresMigrationRequired(
            "directory tables hold personal data and need RLS policies from an "
            "Alembic migration; refusing to create them unprotected"
        )
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS directory_teams (
                team_id         TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                primary_modules TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS directory_roles (
                role_id          TEXT PRIMARY KEY,
                role_code        TEXT NOT NULL,
                role_name        TEXT NOT NULL,
                permission_tier  TEXT NOT NULL DEFAULT '',
                is_default_admin INTEGER NOT NULL DEFAULT 0,
                team_id          TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS directory_members (
                member_id         TEXT PRIMARY KEY,
                auth_user_id      TEXT,
                full_name         TEXT NOT NULL,
                email             TEXT NOT NULL,
                phone             TEXT NOT NULL DEFAULT '',
                organisation      TEXT,
                status            TEXT NOT NULL DEFAULT 'ACTIVE',
                primary_team_id   TEXT NOT NULL,
                primary_role_id   TEXT NOT NULL,
                secondary_team_id TEXT,
                secondary_role_id TEXT
            );
            CREATE TABLE IF NOT EXISTS directory_gates (
                gate_id             TEXT PRIMARY KEY,
                gate_name           TEXT NOT NULL,
                trigger_description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS directory_gate_status (
                member_id TEXT NOT NULL,
                gate_id   TEXT NOT NULL,
                status    TEXT NOT NULL,
                PRIMARY KEY (member_id, gate_id)
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ── reads ────────────────────────────────────────────────────────────────────
# Ordering is server-side and matches the `.order()` calls the Supabase hook
# made, so the screen renders in the same sequence it does today: teams by name
# (the T01…T08 prefix surfaces in order), roles by role_code, members by
# full_name.

def list_teams() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT team_id, name, description, primary_modules "
            "FROM directory_teams ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r["team_id"], "name": r["name"],
             "description": r["description"],
             "primary_modules": r["primary_modules"]} for r in rows]


def list_roles() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT role_id, role_code, role_name, permission_tier, "
            "is_default_admin, team_id FROM directory_roles ORDER BY role_code"
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r["role_id"], "role_code": r["role_code"],
             "role_name": r["role_name"],
             "permission_tier": r["permission_tier"],
             "is_default_admin": bool(r["is_default_admin"]),
             "team_id": r["team_id"]} for r in rows]


def list_members(*, include_pii: bool) -> list[dict[str, Any]]:
    """
    The directory. `include_pii` is the caller's decision, made once in the
    route from the identity payload — this function does not inspect a request
    and cannot be talked into disclosure by one.
    """
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT member_id, full_name, email, phone, organisation, status, "
            "primary_team_id, primary_role_id, secondary_team_id, secondary_role_id "
            "FROM directory_members ORDER BY full_name"
        ).fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for r in rows:
        member = {
            "id": r["member_id"],
            "full_name": r["full_name"],
            "organisation": r["organisation"],
            "status": r["status"],
            "primary_team_id": r["primary_team_id"],
            "primary_role_id": r["primary_role_id"],
            "secondary_team_id": r["secondary_team_id"],
            "secondary_role_id": r["secondary_role_id"],
        }
        if include_pii:
            for field in PII_FIELDS:
                member[field] = r[field]
        out.append(member)
    return out


def list_gates() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT gate_id, gate_name, trigger_description "
            "FROM directory_gates ORDER BY gate_id"
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r["gate_id"], "gate_name": r["gate_name"],
             "trigger_description": r["trigger_description"]} for r in rows]


def list_gate_status() -> list[dict[str, Any]]:
    """`user_id` in the payload is the directory member id — see the module
    docstring. The name is kept because the frontend's `GateStatusRow` uses it
    and this increment changes transport, not shapes."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT member_id, gate_id, status FROM directory_gate_status "
            "ORDER BY member_id, gate_id"
        ).fetchall()
    finally:
        conn.close()
    return [{"user_id": r["member_id"], "gate_id": r["gate_id"],
             "status": r["status"]} for r in rows]


# ── writes: import only ──────────────────────────────────────────────────────

def upsert_team(team_id: str, name: str, description: str = "",
                primary_modules: str = "") -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO directory_teams (team_id, name, description, primary_modules) "
            "VALUES (?,?,?,?) ON CONFLICT(team_id) DO UPDATE SET "
            "name=excluded.name, description=excluded.description, "
            "primary_modules=excluded.primary_modules",
            (team_id, name, description, primary_modules))
        conn.commit()
    finally:
        conn.close()


def upsert_role(role_id: str, role_code: str, role_name: str,
                permission_tier: str = "", is_default_admin: bool = False,
                team_id: str = "") -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO directory_roles (role_id, role_code, role_name, "
            "permission_tier, is_default_admin, team_id) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(role_id) DO UPDATE SET role_code=excluded.role_code, "
            "role_name=excluded.role_name, permission_tier=excluded.permission_tier, "
            "is_default_admin=excluded.is_default_admin, team_id=excluded.team_id",
            (role_id, role_code, role_name, permission_tier,
             1 if is_default_admin else 0, team_id))
        conn.commit()
    finally:
        conn.close()


def upsert_member(member_id: str, full_name: str, email: str, phone: str = "",
                  organisation: Optional[str] = None, status: str = "ACTIVE",
                  primary_team_id: str = "", primary_role_id: str = "",
                  secondary_team_id: Optional[str] = None,
                  secondary_role_id: Optional[str] = None,
                  auth_user_id: Optional[str] = None) -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO directory_members (member_id, auth_user_id, full_name, "
            "email, phone, organisation, status, primary_team_id, primary_role_id, "
            "secondary_team_id, secondary_role_id) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(member_id) DO UPDATE SET full_name=excluded.full_name, "
            "email=excluded.email, phone=excluded.phone, "
            "organisation=excluded.organisation, status=excluded.status, "
            "primary_team_id=excluded.primary_team_id, "
            "primary_role_id=excluded.primary_role_id, "
            "secondary_team_id=excluded.secondary_team_id, "
            "secondary_role_id=excluded.secondary_role_id",
            (member_id, auth_user_id, full_name, email, phone, organisation,
             status, primary_team_id, primary_role_id, secondary_team_id,
             secondary_role_id))
        conn.commit()
    finally:
        conn.close()


def upsert_gate(gate_id: str, gate_name: str, trigger_description: str = "") -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO directory_gates (gate_id, gate_name, trigger_description) "
            "VALUES (?,?,?) ON CONFLICT(gate_id) DO UPDATE SET "
            "gate_name=excluded.gate_name, "
            "trigger_description=excluded.trigger_description",
            (gate_id, gate_name, trigger_description))
        conn.commit()
    finally:
        conn.close()


def set_gate_status(member_id: str, gate_id: str, status: str) -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO directory_gate_status (member_id, gate_id, status) "
            "VALUES (?,?,?) ON CONFLICT(member_id, gate_id) DO UPDATE SET "
            "status=excluded.status",
            (member_id, gate_id, status))
        conn.commit()
    finally:
        conn.close()


# ── the measurement the identity decision needs ──────────────────────────────

def _normalised_name(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def reconcile_with_auth_users() -> dict[str, Any]:
    """
    Match directory members to `auth_users` by email, filling `auth_user_id`.

    Returns the two mismatch lists — directory members with no account, and
    accounts with no directory entry — plus `name_match_candidates`, which is
    the measurement `docs/supabase-cutover-endpoints.md` §2 needs. Matching is
    case-insensitive on a stripped address; anything subtler is a judgement
    call for a human.

    NAMES ARE REPORTED, NEVER LINKED. The 2026-09-20 import found the same two
    people in both stores under different addresses (`felix@etfuels.com` vs
    `felix.leworthy@etfuels.com`), so an email-only reconciliation understates
    the overlap. But two people can share a name, and auto-linking identities
    on a name collision would hand one person another's account. Candidates are
    listed for a human to confirm; only an email match is written.

    Safe to re-run: it only ever sets `auth_user_id` from a live email match.
    """
    conn = _conn()
    try:
        members = conn.execute(
            "SELECT member_id, email, full_name FROM directory_members").fetchall()
        try:
            accounts = conn.execute(
                "SELECT user_id, email, user_name FROM auth_users").fetchall()
        except sqlite3.OperationalError:
            # No auth slice in this database — nothing to reconcile against.
            accounts = []

        by_email = {(a["email"] or "").strip().lower(): a["user_id"] for a in accounts}
        matched_user_ids: set[str] = set()
        unmatched: list[sqlite3.Row] = []

        for m in members:
            key = (m["email"] or "").strip().lower()
            user_id = by_email.get(key)
            if user_id:
                conn.execute(
                    "UPDATE directory_members SET auth_user_id=? WHERE member_id=?",
                    (user_id, m["member_id"]))
                matched_user_ids.add(user_id)
            else:
                unmatched.append(m)
        conn.commit()

        unmatched_accounts = [a for a in accounts
                              if a["user_id"] not in matched_user_ids]

        by_name: dict[str, list[sqlite3.Row]] = {}
        for a in unmatched_accounts:
            by_name.setdefault(_normalised_name(a["user_name"]), []).append(a)

        candidates = []
        for m in unmatched:
            for a in by_name.get(_normalised_name(m["full_name"]), []):
                candidates.append({
                    "member_id": m["member_id"],
                    "full_name": m["full_name"],
                    "directory_email": m["email"],
                    "auth_user_id": a["user_id"],
                    "auth_email": a["email"],
                })
    finally:
        conn.close()

    return {
        "members_without_account": sorted(m["member_id"] for m in unmatched),
        "accounts_without_directory_entry": sorted(a["user_id"] for a in unmatched_accounts),
        "name_match_candidates": sorted(candidates, key=lambda c: c["full_name"]),
    }
