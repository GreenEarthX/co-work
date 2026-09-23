"""
KYC / KYB store — the record GEX vets, held where GEX can vet it.
=================================================================
Replaces `frontend/src/features/kyc/kycState.ts`, which kept all of this in
`localStorage`: the ~45-field profile, and the KYB record including legal name,
registration number, VAT id, registered address and beneficial owners. In a
browser that meant the data was lost on a new device, invisible to the backend,
and unreviewable — while `auth_users.kyc_status` said VERIFIED for 19 of 20
accounts.

PROVENANCE
----------
Every row says where its values came from: SEED, EXTERNAL_PRIOR (OSINT, an
open-source publication, the geomap database), CLIENT_ASSERTED or VERIFIED.
Migration 051 enforces the vocabulary with a CHECK, and enforces that
`verified_by`/`verified_at` are NULL unless the row is VERIFIED.

Seeding plausible values into a pre-production platform is legitimate. A seeded
value that claims to be verified is not, and this module will not write one:
`verify()` is the only path to VERIFIED and it requires a verifier.

STORE
-----
Follows `GOVERNANCE_DB_BACKEND`, like the staff directory — the other store of
personal data, vetted by the same people, under the same slice. The connection
binds both identity axes, which 051's policies need: `kyc_profiles` admits the
SUBJECT or PLATFORM_ADMIN (KYC exists to be reviewed; a canvas does not), and
the KYB tables are company-scoped.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.db_backend import governance_connection, governance_is_postgres

PROVENANCE = ("SEED", "EXTERNAL_PRIOR", "CLIENT_ASSERTED", "VERIFIED")

KYB_STATUSES = ("none", "pending_colleague", "completed")


class KycError(ValueError):
    """Refused. Distinct from a database error so a route can answer 422."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    return governance_connection()


def _check_provenance(provenance: str) -> str:
    if provenance not in PROVENANCE:
        raise KycError(
            f"provenance must be one of {', '.join(PROVENANCE)}, not {provenance!r}")
    if provenance == "VERIFIED":
        # VERIFIED is not something a writer may simply assert about itself.
        raise KycError(
            "VERIFIED is not settable here — it records that GEX checked the "
            "submission against a document. Use verify(), which names the "
            "verifier and the time")
    return provenance


# ── KYC profile (the subject's own submission) ──────────────────────────────

def get_profile(user_id: str) -> Optional[dict[str, Any]]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT user_id, company_id, kyc_role, profile_json, completed, "
            "provenance, source_ref, submitted_at, verified_by, verified_at, "
            "created_at, updated_at FROM kyc_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    out = dict(row)
    out["profile"] = json.loads(out.pop("profile_json") or "{}")
    out["completed"] = bool(out["completed"])
    return out


def upsert_profile(user_id: str, company_id: str, *, profile: dict[str, Any],
                   kyc_role: Optional[str] = None, completed: bool = False,
                   provenance: str = "CLIENT_ASSERTED",
                   source_ref: Optional[str] = None) -> dict[str, Any]:
    """Write the subject's profile.

    Editing a profile RESETS provenance to what the writer says it is and drops
    any verification: a record that changed after it was checked has not been
    checked. 051's CHECK constraint enforces the same thing at the database.
    """
    _check_provenance(provenance)
    now = _now()
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO kyc_profiles
               (user_id, company_id, kyc_role, profile_json, completed,
                provenance, source_ref, submitted_at, verified_by, verified_at,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?,?)
               ON CONFLICT (user_id) DO UPDATE SET
                 company_id = excluded.company_id,
                 kyc_role = COALESCE(excluded.kyc_role, kyc_profiles.kyc_role),
                 profile_json = excluded.profile_json,
                 completed = excluded.completed,
                 provenance = excluded.provenance,
                 source_ref = excluded.source_ref,
                 submitted_at = excluded.submitted_at,
                 verified_by = NULL,
                 verified_at = NULL,
                 updated_at = excluded.updated_at""",
            (user_id, company_id, kyc_role, json.dumps(profile, sort_keys=True),
             1 if completed else 0, provenance, source_ref, now, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_profile(user_id) or {}


def verify(user_id: str, *, verified_by: str) -> dict[str, Any]:
    """Record that GEX checked this submission. The only path to VERIFIED."""
    if not (verified_by or "").strip():
        raise KycError("verified_by is required — a verification with no verifier "
                       "is the thing this column exists to prevent")
    if verified_by == user_id:
        raise KycError("a subject cannot verify their own KYC submission")
    now = _now()
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE kyc_profiles SET provenance = 'VERIFIED', verified_by = ?, "
            "verified_at = ?, updated_at = ? WHERE user_id = ?",
            (verified_by, now, now, user_id),
        )
        if getattr(cur, "rowcount", 0) == 0:
            raise KycError(f"no KYC profile for {user_id!r} to verify")
        conn.commit()
    finally:
        conn.close()
    return get_profile(user_id) or {}


# ── KYB (the legal entity) ──────────────────────────────────────────────────

def get_kyb(company_id: str) -> Optional[dict[str, Any]]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM kyb_records WHERE company_id = ?", (company_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def upsert_kyb(company_id: str, *, legal_name: str, registration_number: str,
               country: str, registered_address: str, responsible_name: str,
               responsible_email: str, vat_id: Optional[str] = None,
               beneficial_owners: Optional[str] = None,
               responsible_job_title: Optional[str] = None,
               status: str = "completed",
               provenance: str = "CLIENT_ASSERTED",
               source_ref: Optional[str] = None) -> dict[str, Any]:
    _check_provenance(provenance)
    if status not in KYB_STATUSES:
        raise KycError(f"status must be one of {', '.join(KYB_STATUSES)}")
    now = _now()
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO kyb_records
               (company_id, legal_name, registration_number, country, vat_id,
                registered_address, beneficial_owners, responsible_name,
                responsible_email, responsible_job_title, status, provenance,
                source_ref, verified_by, verified_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?)
               ON CONFLICT (company_id) DO UPDATE SET
                 legal_name = excluded.legal_name,
                 registration_number = excluded.registration_number,
                 country = excluded.country,
                 vat_id = excluded.vat_id,
                 registered_address = excluded.registered_address,
                 beneficial_owners = excluded.beneficial_owners,
                 responsible_name = excluded.responsible_name,
                 responsible_email = excluded.responsible_email,
                 responsible_job_title = excluded.responsible_job_title,
                 status = excluded.status,
                 provenance = excluded.provenance,
                 source_ref = excluded.source_ref,
                 verified_by = NULL,
                 verified_at = NULL,
                 updated_at = excluded.updated_at""",
            (company_id, legal_name, registration_number, country, vat_id,
             registered_address, beneficial_owners, responsible_name,
             responsible_email, responsible_job_title, status, provenance,
             source_ref, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_kyb(company_id) or {}


# ── KYB colleague invitations ───────────────────────────────────────────────

def list_invitations(company_id: str) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kyb_invitations WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def create_invitation(company_id: str, *, email: str, company_name: str,
                      invited_by: str, invited_by_name: Optional[str] = None,
                      company_domain: Optional[str] = None) -> dict[str, Any]:
    if not (email or "").strip():
        raise KycError("email is required")
    now = _now()
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO kyb_invitations
               (invitation_id, company_id, email, company_name, company_domain,
                invited_by, invited_by_name, accepted_at, created_at)
               VALUES (?,?,?,?,?,?,?,NULL,?)
               ON CONFLICT (company_id, email) DO UPDATE SET
                 company_name = excluded.company_name,
                 company_domain = excluded.company_domain,
                 invited_by = excluded.invited_by,
                 invited_by_name = excluded.invited_by_name""",
            (f"kybinv_{uuid.uuid4().hex[:12]}", company_id, email.strip(),
             company_name, company_domain, invited_by, invited_by_name, now),
        )
        conn.commit()
    finally:
        conn.close()
    return next((i for i in list_invitations(company_id) if i["email"] == email.strip()), {})


def accept_invitation(company_id: str, email: str) -> int:
    """Mark an invitation accepted. Returns how many rows changed.

    The row is kept, not deleted: who invited whom, and when it was taken up,
    is part of how a company's users came to exist. The browser version simply
    dropped it from an array.
    """
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE kyb_invitations SET accepted_at = ? "
            "WHERE company_id = ? AND LOWER(email) = LOWER(?) AND accepted_at IS NULL",
            (_now(), company_id, email),
        )
        n = getattr(cur, "rowcount", 0) or 0
        conn.commit()
        return n
    finally:
        conn.close()


def init_db() -> None:
    """Migration 051 owns these tables and their policies on PostgreSQL.

    There is no SQLite fallback schema here on purpose: this is regulated
    personal data, and the pattern this codebase already settled is that such a
    table is never created by the runtime. If the tables are missing, run the
    migration.
    """
    if governance_is_postgres():
        return
    raise RuntimeError(
        "kyc_store requires GOVERNANCE_DB_BACKEND=postgres: KYC/KYB is "
        "regulated personal data and its RLS policies come from migration 051")
