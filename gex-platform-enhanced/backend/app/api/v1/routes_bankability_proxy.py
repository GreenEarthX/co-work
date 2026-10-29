"""
GEX Platform — Bankability Proxy Routes
=========================================
Mount in gex-platform-enhanced/backend/app/main.py:

    from app.api.v1.routes_bankability_proxy import router as bankability_proxy_router
    app.include_router(bankability_proxy_router, prefix="/api/v1/bankability", tags=["Bankability"])

Architecture:
    Frontend (React) -> Platform Backend (8000) /api/v1/bankability/* -> Engine (8001)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Optional

import httpx

from app.services.engine_auth import engine_auth_headers
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel
from app.core.abac import EVIDENCE_REVIEW_STATUSES, EVIDENCE_SUBMISSION_STATUSES
from app.core.config import settings

logger = logging.getLogger("gex.evidence")
router = APIRouter()

ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
DB_PATH = settings.SQLITE_DB_PATH
ENGINE_TIMEOUT = 10.0


class EvidenceUpdateRequest(BaseModel):
    project_id: str = "default"
    evidence_key: str
    new_status: str
    # IGNORED. Who acted comes from the bearer token, never from the body: this
    # field let a producer record "Independent Certifier" as the actor of its own
    # verification (Attack A, 2026-09-30). Accepted so older clients do not fail;
    # a value naming anyone but the caller is logged (_log_foreign_submitted_by).
    submitted_by: Optional[str] = None
    notes: Optional[str] = None
    # How far the underlying instrument has progressed — INTENT, INDICATIVE,
    # AGREED, EXECUTED or EFFECTIVE. Declared by the submitter; a reviewer may
    # confirm or lower it, never raise it. See _validate_evidence_write.
    maturity: Optional[str] = None
    # The document a VERIFIED attests to: the sha256 of a document on file for
    # this item (POST /evidence/document). Required for VERIFIED; any other
    # status may name one. See _document_on_file.
    document_sha256: Optional[str] = None


# Statuses a producer moves an item through, and statuses a reviewer sets —
# defined once in app.core.abac, where the middleware classifies a reviewer
# status as VERIFY. Maturity may be RAISED only on the producer side: the party
# asserting what an instrument is must not be the party that verifies it, and
# verification must never make a term sheet into a contract.
_PRODUCER_STATUSES = EVIDENCE_SUBMISSION_STATUSES
_REVIEWER_STATUSES = EVIDENCE_REVIEW_STATUSES


def _validate_evidence_write(evidence_key: str, new_status: Optional[str],
                             maturity: Optional[str], existing_maturity: Optional[str]) -> None:
    """Refuse writes the gate engine could only misread. Raises HTTPException(422)."""
    from app.core.bankability_engine import (
        GATE_REGISTRY, MATURITY_LEVELS, RETIRED_EVIDENCE,
    )

    retired = RETIRED_EVIDENCE.get(evidence_key)
    if retired:
        raise HTTPException(status_code=422, detail={
            "code": "EVIDENCE_KEY_RETIRED",
            "evidence_key": evidence_key,
            "replaced_by": retired["replaced_by"],
            "reason": retired["reason"],
            "message": (f"'{evidence_key}' was retired in evidence rules 3.0.0 and no gate "
                        f"scores it. Submit '{retired['replaced_by']}' instead."),
        })
    live = {k for g in GATE_REGISTRY for k in g.required_evidence}
    if evidence_key not in live:
        # An unknown key can never count toward any gate, so accepting it would
        # record evidence that looks filed and is invisible to every decision.
        raise HTTPException(status_code=422, detail={
            "code": "EVIDENCE_KEY_UNKNOWN",
            "evidence_key": evidence_key,
            "message": f"'{evidence_key}' is not an evidence item of any gate.",
        })
    if new_status is not None and new_status not in _PRODUCER_STATUSES | _REVIEWER_STATUSES:
        raise HTTPException(status_code=422, detail={
            "code": "EVIDENCE_STATUS_UNKNOWN",
            "new_status": new_status,
            "message": (f"'{new_status}' is not an evidence status. A misspelt VERIFIED "
                        f"would otherwise be stored and silently never count."),
        })
    if maturity is None:
        return
    if maturity not in MATURITY_LEVELS:
        raise HTTPException(status_code=422, detail={
            "code": "MATURITY_UNKNOWN",
            "maturity": maturity,
            "allowed": MATURITY_LEVELS,
            "message": f"'{maturity}' is not a maturity level.",
        })
    if new_status in _REVIEWER_STATUSES:
        if existing_maturity not in MATURITY_LEVELS:
            raise HTTPException(status_code=422, detail={
                "code": "MATURITY_MUST_BE_DECLARED_AT_SUBMISSION",
                "message": ("Maturity is declared by the submitter. A reviewer can confirm "
                            "or lower it, but cannot introduce it — resubmit the item with "
                            "its maturity declared."),
            })
        if MATURITY_LEVELS.index(maturity) > MATURITY_LEVELS.index(existing_maturity):
            raise HTTPException(status_code=422, detail={
                "code": "VERIFICATION_CANNOT_RAISE_MATURITY",
                "declared_maturity": existing_maturity,
                "requested_maturity": maturity,
                "message": (f"Declared as {existing_maturity}. Review can confirm that or "
                            f"lower it; raising it to {maturity} needs a new submission."),
            })


def _get_db():
    """
    Connection for the evidence/bankability slice — SQLite or PostgreSQL by
    configuration (EVIDENCE_DB_BACKEND). The SQL in this module is unchanged;
    the shim translates placeholders and sets the RLS tenant context.
    """
    from app.core.db_backend import evidence_connection, evidence_is_postgres

    conn = evidence_connection()
    if not evidence_is_postgres():
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_tables(conn):
    # SQLite only. On PostgreSQL the schema is owned by migrations 034 and 054,
    # and this DDL is not valid there — AUTOINCREMENT is SQLite syntax, and the
    # runtime role gex_app has no CREATE on schema public in any case.
    #
    # Found 2026-09-26: this ran unconditionally, so it raised
    # `syntax error at or near "AUTOINCREMENT"` on every call under
    # EVIDENCE_DB_BACKEND=postgres. Every function here calls it first, so every
    # evidence read and write on PostgreSQL failed — evaluate, update, list,
    # document upload, audit trail, health. The UI showed ABAC's 403 before the
    # handler ran, and the tests pin SQLite, so neither surfaced it.
    # Guarded by tests/test_evidence_pg_path.py, which runs against PostgreSQL.
    from app.core.db_backend import evidence_is_postgres
    if evidence_is_postgres():
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bankability_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL DEFAULT 'default',
            evidence_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            submitted_by TEXT, verified_by TEXT,
            submitted_at TEXT, verified_at TEXT,
            document_hash TEXT, notes TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            maturity TEXT,
            assignee_user_id TEXT, assigned_by TEXT, assigned_at TEXT, due_date TEXT,
            committed_at TEXT, committed_by TEXT,
            UNIQUE(project_id, evidence_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bankability_snapshots (
            project_id TEXT PRIMARY KEY,
            current_state TEXT NOT NULL,
            snapshot_json TEXT,
            evaluated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_project ON bankability_evidence(project_id)")
    # Documents backing evidence items — evidence without a document is a claim.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            evidence_key TEXT NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            stored_path TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)
    # Append-only status transition log — control functions audit transitions,
    # not states. Never UPDATEd, never DELETEd.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            evidence_key TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TEXT NOT NULL,
            document_sha256 TEXT,
            old_maturity TEXT,
            new_maturity TEXT,
            old_assignee TEXT,
            new_assignee TEXT,
            old_due_date TEXT,
            new_due_date TEXT
        )
    """)
    # Commitment cards (058) — structured terms behind offtake, EPC, schedule,
    # supply and model; replaced per card, history append-only.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commitment_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            card_type TEXT NOT NULL,
            terms_json TEXT NOT NULL,
            updated_by TEXT, updated_at TEXT,
            UNIQUE(project_id, card_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commitment_terms_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            card_type TEXT NOT NULL,
            old_json TEXT,
            new_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TEXT NOT NULL
        )
    """)
    # Maturity became load-bearing in evidence rules 3.0.0. On PostgreSQL the
    # columns come from migration 054 (this function has returned by now); this
    # covers a SQLite file created before it.
    # Assignment (055) likewise.
    for table, columns in (("bankability_evidence", ("maturity", "assignee_user_id", "assigned_by",
                                                     "assigned_at", "due_date", "committed_at",
                                                     "committed_by")),
                           ("evidence_events", ("old_maturity", "new_maturity",
                                                "old_assignee", "new_assignee",
                                                "old_due_date", "new_due_date"))):
        present = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in columns:
            if col not in present:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    conn.commit()


def _load_evidence(project_id="default"):
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute("SELECT * FROM bankability_evidence WHERE project_id = ?", (project_id,)).fetchall()
    conn.close()

    def _col(r, name):
        # Tolerant on read only: a failed read breaks the whole evaluation, and
        # a missing column means "not declared" / "not assigned" — the engine
        # fails an undeclared maturity closed.
        try:
            return r[name]
        except (KeyError, IndexError):
            return None

    return [{"key": r["evidence_key"], "status": r["status"], "submitted_by": r["submitted_by"],
             "verified_by": r["verified_by"], "submitted_at": r["submitted_at"],
             "verified_at": r["verified_at"], "document_hash": r["document_hash"],
             "notes": r["notes"], "maturity": _col(r, "maturity"),
             "assignee_user_id": _col(r, "assignee_user_id"), "due_date": _col(r, "due_date"),
             "committed_at": _col(r, "committed_at")}
            for r in rows]


def _existing_maturity(project_id, evidence_key):
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT maturity FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?",
        (project_id, evidence_key),
    ).fetchone()
    conn.close()
    return row["maturity"] if row else None


def _upsert_evidence(project_id, evidence_key, status, actor, notes=None,
                     document_sha256=None, maturity=None):
    """Write one evidence item and its append-only audit event.

    `actor` is the AUTHENTICATED user id — never a name from a request body. It
    is the event's actor, the submitter of a SUBMITTED and the verifier of a
    VERIFIED. The body's submitted_by used to fill all three, so a producer's
    own verification was recorded under a certifier's name (Attack A).
    """
    if not actor:
        raise ValueError("an evidence write needs the authenticated user as its actor")
    conn = _get_db()
    _ensure_tables(conn)
    old = conn.execute(
        "SELECT status, maturity FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?",
        (project_id, evidence_key),
    ).fetchone()
    old_status = old["status"] if old else None
    old_maturity = old["maturity"] if old else None
    new_maturity = maturity if maturity is not None else old_maturity
    # The submitter is who a reviewer must be independent of; the verifier, and
    # the document verified, are what a lender reads. verified_by describes the
    # CURRENT verification, so any other status clears it — the event log keeps
    # the history. document_hash is the last document any write named.
    submitter = actor if status == "SUBMITTED" else None
    verifier = actor if status == "VERIFIED" else None
    conn.execute("""
        INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, submitted_at,
                                          verified_by, verified_at, document_hash, notes, maturity,
                                          updated_at)
        VALUES (?, ?, ?, ?, CASE WHEN ? IS NULL THEN NULL ELSE datetime('now') END,
                ?, CASE WHEN ? IS NULL THEN NULL ELSE datetime('now') END, ?, ?, ?,
                datetime('now'))
        ON CONFLICT(project_id, evidence_key)
        DO UPDATE SET status=excluded.status,
            submitted_by=COALESCE(excluded.submitted_by, bankability_evidence.submitted_by),
            submitted_at=COALESCE(excluded.submitted_at, bankability_evidence.submitted_at),
            verified_by=excluded.verified_by,
            verified_at=excluded.verified_at,
            document_hash=COALESCE(excluded.document_hash, bankability_evidence.document_hash),
            notes=COALESCE(excluded.notes, bankability_evidence.notes),
            maturity=COALESCE(excluded.maturity, bankability_evidence.maturity),
            updated_at=datetime('now')
    """, (project_id, evidence_key, status, submitter, submitter, verifier, verifier,
          document_sha256, notes, maturity))
    # Append-only audit: every status transition AND every maturity change is
    # recorded with its actor. Maturity is load-bearing from rules 3.0.0, so a
    # change from INTENT to EXECUTED that left the status alone must still leave
    # a trace — otherwise the most consequential edit would be the invisible one.
    # So must every write that names a document: a second upload, or a second
    # reviewer verifying the same item, changes no status but is an attestation.
    if old_status != status or old_maturity != new_maturity or document_sha256:
        conn.execute(
            "INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, "
            "document_sha256, old_maturity, new_maturity) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)",
            (project_id, evidence_key, old_status, status, actor,
             document_sha256, old_maturity, new_maturity),
        )
    conn.commit()
    conn.close()


def _get_project_state(project_id="default"):
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute("SELECT current_state FROM bankability_snapshots WHERE project_id = ?", (project_id,)).fetchone()
    conn.close()
    return row["current_state"] if row else None


def _store_snapshot(project_id, state, snapshot_json):
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute("DELETE FROM bankability_snapshots WHERE project_id = ?", (project_id,))
    conn.execute("""
        INSERT INTO bankability_snapshots (project_id, current_state, snapshot_json, evaluated_at)
        VALUES (?, ?, ?, datetime('now'))
    """, (project_id, state, snapshot_json))
    conn.commit()
    conn.close()


def _physical_payload(project_id: str) -> dict:
    """
    Power model + phase + financing model for the engine's gate scoping,
    severity escalation, and financing-waived gates. Reads the EFFECTIVE
    context (DB override written via PATCH /projects/{id}/context, falling
    back to the code seed).
    """
    try:
        from app.core.project_registry import get_effective_context
        ctx = get_effective_context(project_id)
        if ctx:
            payload = {
                "power_model": ctx.power_model,
                "project_phase": ctx.phase,
                "financing_model": ctx.financing_model,
            }
            # A contested or rejected premise is not used: the engine gets the
            # protective one (project finance; no power model = all items).
            from app.core.premises import protective_overrides
            try:
                payload.update(protective_overrides(project_id))
            except Exception as exc:  # noqa: BLE001 — fail closed: protective premises
                logger.warning("premise overrides unreadable for %s (%s); using protective premises",
                               project_id, exc)
                payload.update({"power_model": None, "financing_model": "PROJECT_FINANCE"})
            return payload
    except Exception:
        pass
    return {"power_model": None, "project_phase": None, "financing_model": None}


# ── Applicability — nobody is asked for evidence the project does not need ──

_NOT_APPLICABLE_MESSAGE = {
    "POWER_MODEL": "does not apply to this project's power model",
    "FINANCING_MODEL": "protects a lender and does not apply to balance-sheet funding",
}


def _inapplicable(project_id: str, evidence_key: str) -> str | None:
    """POWER_MODEL / FINANCING_MODEL when the item does not apply to the project's
    declared premise; None when it does. Same rule as the engine's
    not_applicable_reason (tests/test_gate_registries_agree.py)."""
    from app.core.bankability_engine import inapplicability

    ctx = _physical_payload(project_id)
    return inapplicability(evidence_key, ctx.get("power_model"), ctx.get("financing_model"))


# ── Assignment — a named person owns each evidence request (migration 055) ──

def _account_directory(user_ids) -> dict:
    """user_id -> {name, business_function, company_id, account_state} from the
    auth store. Auth tables carry no RLS, so this resolves regardless of tenant.
    Tolerant: a name lookup must never break a gate evaluation."""
    ids = sorted({u for u in user_ids if u})
    if not ids:
        return {}
    try:
        from app.core.auth import auth_db_connection
        conn = auth_db_connection()
        try:
            rows = conn.execute(
                "SELECT user_id, user_name, business_function, company_id, account_state "
                f"FROM auth_users WHERE user_id IN ({','.join('?' for _ in ids)})", tuple(ids),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return {}
    return {r["user_id"]: {"name": r["user_name"], "business_function": r["business_function"],
                           "company_id": r["company_id"], "account_state": r["account_state"]}
            for r in rows}


def _optional_actor(authorization: str | None) -> Optional[dict]:
    """The caller if a valid bearer is present, else None — for reads that only
    personalise (who may commit, who may reassign) and must not fail on it."""
    try:
        return _require_actor(authorization) if authorization else None
    except HTTPException:
        return None


# ── Review — separation of duties (Attack A, 2026-09-30) ─────────────────────
# A reviewer status is a VERIFY. ABAC R5 has already required a reviewer role
# and independence from the project's owner (abac.verification_refusal). What
# only the stored submission can answer is checked here: the reviewer is not
# the submitter, nor from the submitter's company.

def _independence_refusal(actor: dict, submitter: Optional[str],
                          account: Optional[dict]) -> Optional[tuple[int, str, str]]:
    """(http status, code, message) if `actor` may not review a submission by
    `submitter` (whose account is `account`), else None. Fails closed: no
    submission, or one naming no account, cannot be reviewed."""
    if not submitter:
        return 409, "NOTHING_SUBMITTED", "Nothing has been submitted for this item, so there is nothing to review."
    if submitter == actor.get("user_id"):
        return (403, "SUBMITTER_CANNOT_REVIEW",
                "You submitted this item. Someone independent of you and your company must review it.")
    if account is None:
        return (409, "SUBMITTER_NOT_IDENTIFIED",
                "The submission names no account on this platform, so the reviewer's independence "
                "cannot be checked. Its author must resubmit it.")
    if account.get("company_id") == actor.get("company_id"):
        return (403, "SUBMITTING_COMPANY_CANNOT_REVIEW",
                "Your company submitted this item. Someone independent of it must review it.")
    return None


def _require_independent_reviewer(actor: dict, project_id: str, evidence_key: str) -> None:
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT submitted_by FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?",
        (project_id, evidence_key),
    ).fetchone()
    conn.close()
    submitter = row["submitted_by"] if row else None
    account = _account_directory([submitter]).get(submitter) if submitter else None
    refusal = _independence_refusal(actor, submitter, account)
    if refusal:
        status, code, message = refusal
        raise HTTPException(status_code=status, detail={"code": code, "message": message})


def _document_on_file(project_id: str, evidence_key: str, new_status: str,
                      document_sha256: Optional[str]) -> Optional[str]:
    """The document this write names, provided it is on file for this very item.

    VERIFIED must name one: a verification attests to a document, and without
    this a producer verified 22 items with nothing attached (Attack A). Files
    arrive through POST /evidence/document, which stores them with their sha256;
    only a hash stored there for this project and item is accepted."""
    sha = (document_sha256 or "").strip().lower() or None
    if sha is None:
        if new_status == "VERIFIED":
            raise HTTPException(status_code=422, detail={
                "code": "VERIFIED_REQUIRES_A_DOCUMENT",
                "message": ("A verification attests to a document. Name the one you verified "
                            "(document_sha256, from GET /evidence/documents)."),
            })
        return None
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT sha256 FROM evidence_documents WHERE project_id = ? AND evidence_key = ? AND sha256 = ?",
        (project_id, evidence_key, sha),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=422, detail={
            "code": "DOCUMENT_NOT_ON_FILE",
            "message": "That document is not on file for this item. Upload it first (POST /evidence/document).",
        })
    return sha


def _log_foreign_submitted_by(submitted_by: Optional[str], actor: dict) -> None:
    """The body's submitted_by is never stored. One naming someone other than the
    caller is either a stale client or an attempt to put another person's name
    on this write — either way worth a line in the log."""
    if submitted_by and submitted_by not in {actor.get("user_id"), actor.get("email"), actor.get("user_name")}:
        logger.warning("evidence write: ignored submitted_by=%r; the actor recorded is user=%s",
                       submitted_by, actor.get("user_id"))


def _reviewable_keys(actor: Optional[dict], project_id: Optional[str], evidence: list) -> set:
    """Evidence keys this caller may take the reviewer side on: R5's verdict for
    the item's gate, then independence from its submitter — the two checks the
    write applies, so the screen offers Review, Verify and Reject exactly where
    the write accepts them. Tolerant: a failed lookup offers nothing."""
    submitted = [e for e in evidence if e.get("submitted_by")]
    if not actor or not project_id or not submitted:
        return set()
    from app.core.abac import ResourceAttributes, gate_for_evidence, reviewer_gates, verification_refusal
    from app.core.abac_middleware import ABACMiddleware
    from app.core.project_registry import get_project_profile, normalize_project_id

    try:
        pid = normalize_project_id(project_id)
        user = ABACMiddleware._user_from_payload(actor)
        if not reviewer_gates(user, pid):
            return set()   # not a reviewer on this project
        profile = get_project_profile(pid)
        accounts = _account_directory(e["submitted_by"] for e in submitted)
    except Exception:
        return set()
    owner = profile.owner_company_id if profile else ""
    by_gate: dict = {}
    keys = set()
    for e in submitted:
        gate = gate_for_evidence(e["key"])
        if gate not in by_gate:
            by_gate[gate] = verification_refusal(
                user, ResourceAttributes(project_id=pid, data_owner_company_id=owner, gate_id=gate))
        if by_gate[gate] is None and _independence_refusal(
                actor, e["submitted_by"], accounts.get(e["submitted_by"])) is None:
            keys.add(e["key"])
    return keys


def _reviewer_only_scope(actor: Optional[dict], project_id: Optional[str]) -> Optional[frozenset]:
    """The gates whose evidence this caller may see when its only access to the
    project is a reviewer assignment; None when nothing is withheld.

    Owner decision 2026-10-01: a reviewer reads the gate screen and the evidence
    of the gates it reviews, nothing else (ABAC R3 lets it reach the screen). A
    stakeholder sees what it always saw. Not tolerant on purpose: a scope that
    cannot be worked out fails the request rather than showing everything."""
    if not actor or not project_id:
        return None
    from app.core.abac import reviewer_gates
    from app.core.abac_middleware import ABACMiddleware
    from app.core.project_registry import get_project_profile, normalize_project_id

    pid = normalize_project_id(project_id)
    user = ABACMiddleware._user_from_payload(actor)
    gates = reviewer_gates(user, pid)
    if not gates:
        return None
    profile = get_project_profile(pid)
    if profile is not None and user.company_id in profile.stakeholder_company_ids:
        return None
    return gates


def _withhold_other_gates(gate: dict, scope: frozenset) -> None:
    """Keep only the items of the gates in `scope`. By item, not by the gate's
    own id: the item's gate is resolved the way ABAC resolves it."""
    from app.core.abac import gate_for_evidence, gate_number

    def keep(entry: dict) -> bool:
        return gate_number(gate_for_evidence(entry.get("key"))) in scope

    gate["evidence_detail"] = [i for i in gate.get("evidence_detail") or [] if keep(i)]
    if gate.get("maturity_shortfalls"):
        gate["maturity_shortfalls"] = [m for m in gate["maturity_shortfalls"] if keep(m)]


def _attach_assignments(snapshot: dict, evidence: list, actor: Optional[dict] = None,
                        project_id: Optional[str] = None) -> dict:
    """Add who owns each item, whether they have committed to a date, and whether
    it is overdue, to the engine's evidence_detail. The engine scores evidence;
    it does not know people or deadlines — this is the platform's.

    With an actor, also say what THIS caller may do: commit (only the assignee),
    reassign (the owning company or a platform admin) and review (an independent
    reviewer — see _reviewable_keys). The document hash is the platform's too:
    the engine does not pass it through, and a reviewer verifies by naming it."""
    from app.core.evidence_due_dates import OVERDUE, NOT_COMMITTED, commitment_state

    by_key = {e["key"]: e for e in evidence}
    people = _account_directory(e.get("assignee_user_id") for e in evidence)
    can_assign = False
    if actor and project_id:
        can_assign = bool(actor.get("is_platform_admin")) or actor.get("company_id") == _project_owner(project_id)
    reviewable = _reviewable_keys(actor, project_id, evidence)
    scope = _reviewer_only_scope(actor, project_id)
    gates = snapshot.get("gate_evaluations") or []
    for gate in (gates.values() if isinstance(gates, dict) else gates):
        if scope is not None:
            _withhold_other_gates(gate, scope)
        overdue = uncommitted = 0
        for item in gate.get("evidence_detail") or []:
            ev = by_key.get(item.get("key"))
            not_applicable = item.get("status") == "NOT_APPLICABLE"
            item["can_review"] = bool(ev) and not not_applicable and item.get("key") in reviewable
            if not ev:
                # No request raised yet. The owner can still assign one — the
                # assign endpoint creates it — unless the item does not apply.
                item["commitment"] = "UNASSIGNED"
                item["can_assign"] = can_assign and not not_applicable
                item["can_commit"] = False
                continue
            item["document_hash"] = ev.get("document_hash")
            uid = ev.get("assignee_user_id")
            item["assignee_user_id"] = uid
            item["assignee_name"] = (people.get(uid) or {}).get("name") if uid else None
            item["assignee_function"] = (people.get(uid) or {}).get("business_function") if uid else None
            item["due_date"] = ev.get("due_date")
            item["committed_at"] = ev.get("committed_at")
            item["request_note"] = ev.get("notes")
            if not_applicable:
                # A request raised for an item the project does not need: it is
                # not open work, cannot be committed to, and counts nowhere. The
                # owner may withdraw it; the row itself stays as the record.
                item["commitment"], item["days_overdue"] = "NOT_REQUIRED", 0
                item["can_commit"] = item["can_assign"] = False
                item["can_withdraw"] = can_assign and bool(uid)
                continue
            state, days = commitment_state({**ev, "status": item.get("status", ev.get("status"))})
            item["commitment"], item["days_overdue"] = state, days
            item["can_commit"] = bool(actor and uid and actor.get("user_id") == uid and state != "DONE")
            item["can_assign"] = can_assign
            overdue += state == OVERDUE
            uncommitted += state == NOT_COMMITTED
        gate["overdue_count"], gate["uncommitted_count"] = overdue, uncommitted
    return snapshot


def _load_terms(project_id: str) -> dict:
    """The terms the ENGINE may use: card fields whose value is the one confirmed
    on their contract token (app/core/contract_tokens.py, JML 2026-10-28). Held-
    back fields are absent, so the checks needing them read NOT_EVALUABLE and
    their gate UNRESOLVED. An unreadable token store fails closed: no terms."""
    from app.core.contract_tokens import confirmed_terms, engine_terms
    try:
        used, _ = engine_terms(_load_terms_raw(project_id), confirmed_terms(project_id))
        return used
    except Exception as exc:  # noqa: BLE001
        logger.warning("contract tokens unreadable for %s (%s): no terms reach the engine", project_id, exc)
        return {}


def _load_terms_raw(project_id: str) -> dict:
    """The project's commitment cards as typed, {card_type: terms}. Tolerant: a
    card that cannot be read is absent."""
    try:
        conn = _get_db()
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT card_type, terms_json FROM commitment_terms WHERE project_id = ?", (project_id,)
        ).fetchall()
        conn.close()
    except Exception:
        return {}
    out = {}
    for r in rows:
        try:
            out[r["card_type"]] = json.loads(r["terms_json"] or "{}")
        except (TypeError, ValueError):
            continue
    return out


def _engine_context(project_id: str) -> dict:
    """Everything the engine needs besides evidence: power, phase and financing
    model, and (rules 4.0.0) the commitment cards."""
    return {**_physical_payload(project_id), "terms": _load_terms(project_id)}


async def _call_engine(path, method="GET", json_data=None):
    url = f"{ENGINE_URL}/api/v1/bankability{path}"
    headers = engine_auth_headers()
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await (client.post(url, json=json_data, headers=headers) if method == "POST" else client.get(url, headers=headers))
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Engine error: {resp.text}")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Bankability engine unavailable (port 8001)")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Bankability engine timeout")


# ── One re-evaluation path (JML, 2026-10-28) ──────────────────────────────────
# Every change that can move a gate — evidence, a document, a premise, a
# contract term — re-evaluates the project HERE, stores the engine's snapshot
# and records what changed. A stored state that no longer matches its inputs
# ("stale state") was one of the loopholes: other modules read the stored state.

import time as _time

_RULES_CACHE: dict = {"at": 0.0, "rules": None}


async def engine_rules() -> dict:
    """The engine's rules (version, persona gates …), cached for a minute."""
    if _RULES_CACHE["rules"] is None or _time.monotonic() - _RULES_CACHE["at"] > 60:
        _RULES_CACHE["rules"] = await _call_engine("/rules")
        _RULES_CACHE["at"] = _time.monotonic()
    return _RULES_CACHE["rules"]


def stored_snapshot(project_id: str) -> tuple[Optional[dict], Optional[str]]:
    """The last stored engine snapshot and when it was taken, or (None, None)."""
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute("SELECT snapshot_json, evaluated_at FROM bankability_snapshots WHERE project_id = ?",
                       (project_id,)).fetchone()
    conn.close()
    if not row or not row["snapshot_json"]:
        return None, None
    try:
        return json.loads(row["snapshot_json"]), str(row["evaluated_at"])
    except (TypeError, ValueError):
        return None, None


def _drop_snapshot(project_id: str) -> None:
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute("DELETE FROM bankability_snapshots WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()


def _changes(old: Optional[dict], new: dict) -> dict:
    """State and per-gate determination changes between two snapshots."""
    before = {g["gate_id"]: g.get("determination") for g in (old or {}).get("gate_evaluations", [])}
    gates = [{"gate_id": g["gate_id"], "gate_name": g["gate_name"],
              "from": before.get(g["gate_id"]), "to": g.get("determination")}
             for g in new.get("gate_evaluations", []) if before.get(g["gate_id"]) != g.get("determination")]
    return {"from_state": (old or {}).get("current_state"), "to_state": new.get("current_state"),
            "state_changed": (old or {}).get("current_state") != new.get("current_state"),
            "gates": gates if old else [], "first_evaluation": old is None}


async def reevaluate(project_id: str, *, reason: str, actor: Optional[str] = None,
                     evidence: Optional[list] = None) -> dict:
    """Evaluate the project with the engine, store the snapshot, record changes.

    Returns {"snapshot", "changes"}. The event goes to the ledger even when
    nothing changed, so every re-evaluation and its cause can be traced.
    """
    old, _ = stored_snapshot(project_id)
    evidence = _load_evidence(project_id) if evidence is None else evidence
    try:
        snapshot = await _call_engine("/evaluate", method="POST", json_data={
            "project_id": project_id, "evidence": evidence,
            "previous_state": (old or {}).get("current_state"),
            **_engine_context(project_id),
        })
    except HTTPException:
        # The inputs changed and cannot be judged now: the old state must not
        # stand for them. Fail closed to "not evaluated"; the next read
        # re-evaluates (fresh_snapshot).
        _drop_snapshot(project_id)
        logger.warning("re-evaluation of %s failed (%s); stored state withdrawn", project_id, reason)
        raise
    _store_snapshot(project_id, snapshot.get("current_state", "SPECULATIVE"), json.dumps(snapshot))
    changes = _changes(old, snapshot)
    try:
        from app.core.event_store import append_event
        append_event(event_type="bankability.reevaluated", aggregate_type="project", aggregate_id=project_id,
                     data={"reason": reason, "rules_version": snapshot.get("rules_version"), **changes},
                     user_id=actor)
    except Exception as exc:  # noqa: BLE001 — the evaluation stands; the trace failure is logged
        logger.warning("re-evaluation of %s not recorded in the ledger: %s", project_id, exc)
    try:
        from app.core.bankability_reports import notify_changes
        notify_changes(project_id, changes, reason=reason, actor=actor, snapshot=snapshot)
    except Exception as exc:  # noqa: BLE001
        logger.warning("re-evaluation of %s: designated executives not notified: %s", project_id, exc)
    return {"snapshot": snapshot, "changes": changes}


async def fresh_snapshot(project_id: str) -> tuple[Optional[dict], Optional[str]]:
    """The stored snapshot, re-evaluated first if there is none or it was taken
    under other rules. On engine failure the stored one is returned as it is —
    its `evaluated_at` and `rules_version` tell the reader how old it is."""
    snap, at = stored_snapshot(project_id)
    try:
        current = (await engine_rules()).get("rules_version")
        if snap is None or snap.get("rules_version") != current:
            await reevaluate(project_id, reason="rules" if snap else "first_evaluation")
            snap, at = stored_snapshot(project_id)
    except HTTPException as exc:
        logger.warning("engine unavailable while refreshing %s: %s", project_id, exc.detail)
    return snap, at


def _persona_or_403(project_id: str, payload: dict, requested: Optional[str], persona_gates: dict) -> str:
    """The caller's persona from the TOKEN; a requested one only if it is narrower."""
    from app.core.engine_view import narrower_or_equal, persona_for
    from app.core.project_registry import get_project_profile

    profile = get_project_profile(project_id)
    allowed = persona_for(payload, profile.owner_company_id if profile else None)
    if requested and requested.upper() != allowed:
        if not narrower_or_equal(requested.upper(), allowed, persona_gates):
            raise HTTPException(status_code=403, detail={
                "code": "PERSONA_NOT_YOURS",
                "message": f"You see this project as {allowed}; {requested.upper()} would show gates outside your role."})
        return requested.upper()
    return allowed


@router.get("/evaluate")
async def evaluate_project(project_id: str = Query(...),
                           authorization: str | None = Header(default=None)):
    # project_id is required: its old default, "default", stored a snapshot for
    # a project that does not exist.
    actor = _require_actor(authorization)
    evidence = _load_evidence(project_id)
    result = await reevaluate(project_id, reason="requested", actor=actor.get("user_id"), evidence=evidence)
    return _attach_assignments(result["snapshot"], evidence, actor, project_id)


async def _persona_view(project_id: str, requested: Optional[str], authorization: Optional[str]) -> dict:
    """Persona-scoped evaluation. The persona comes from the token (2026-10-28):
    it was a parameter, and ?persona=EXECUTIVE showed any caller all twelve gates."""
    actor = _require_actor(authorization)
    rules = await engine_rules()
    persona = _persona_or_403(project_id, actor, requested, rules.get("persona_gates", {}))
    evidence = _load_evidence(project_id)
    view = await _call_engine("/evaluate/persona", method="POST", json_data={
        "project_id": project_id, "evidence": evidence, "persona": persona,
        "previous_state": _get_project_state(project_id), **_engine_context(project_id),
    })
    total = len(rules.get("persona_gates", {}).get("EXECUTIVE", []))
    seen = len(view.get("gate_evaluations", []))
    view["scope"] = {"persona": persona, "visible_gates": seen, "total_gates": total,
                     "note": None if seen == total else
                     f"The overall figure and the state cover all {total} gates; you see the {seen} that concern your role."}
    return _attach_assignments(view, evidence, actor, project_id)


@router.get("/evaluate/persona")
async def evaluate_for_persona(
    project_id: str = Query(...),
    persona: Optional[str] = Query(default=None, description="Optional; only a persona narrower than yours"),
    authorization: str | None = Header(default=None),
):
    return await _persona_view(project_id, persona, authorization)


@router.get("/projects/{project_id}/bankability/{persona}")
async def get_project_bankability_for_persona(project_id: str, persona: str,
                                              authorization: str | None = Header(default=None)):
    return await _persona_view(project_id, persona, authorization)


@router.get("/executive/portfolio")
async def get_executive_portfolio():
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT project_id, current_state, snapshot_json FROM bankability_snapshots"
    ).fetchall()
    conn.close()

    projects = []
    total_completion = 0.0
    projects_with_regressions = 0

    for row in rows:
        project_id = row["project_id"]
        evidence = _load_evidence(project_id)
        try:
            persona_view = await _call_engine("/evaluate/persona", method="POST", json_data={
                "project_id": project_id, "evidence": evidence,
                "persona": "EXECUTIVE", "previous_state": row["current_state"],
                **_engine_context(project_id),
            })
        except Exception:
            persona_view = json.loads(row["snapshot_json"]) if row["snapshot_json"] else {}

        completion = persona_view.get("overall_completion_pct", 0)
        total_completion += completion
        if persona_view.get("regression"):
            projects_with_regressions += 1

        capital_unlocks = persona_view.get("capital_unlocks", [])
        unlocked_count = sum(1 for c in capital_unlocks if c.get("is_unlocked"))

        projects.append({
            "project_id": project_id,
            "current_state": row["current_state"],
            "overall_completion": round(completion, 1),
            "capital_unlocks": capital_unlocks,
            "unlocked_count": unlocked_count,
            "gate_evaluations": persona_view.get("gate_evaluations", []),
            "regression": persona_view.get("regression"),
        })

    count = len(projects)
    avg_completion = round(total_completion / count, 1) if count > 0 else 0.0
    total_unlocked = sum(p["unlocked_count"] for p in projects)

    return {
        "portfolioSummary": {
            "total_projects": count,
            "total_portfolio_value": "N/A",
            "total_unlocked": f"{total_unlocked} capital types unlocked",
            "average_completion": avg_completion,
            "projects_with_regressions": projects_with_regressions,
            "capital_pipeline": [],
        },
        "projects": projects,
    }


@router.get("/gates")
async def get_gate_definitions():
    return await _call_engine("/gates")


@router.get("/rules")
async def get_rules():
    return await _call_engine("/rules")


@router.post("/evidence")
async def update_evidence(request: EvidenceUpdateRequest,
                          authorization: str | None = Header(default=None)):
    """Set one evidence item's status, as a submitter or as a reviewer.

    The actor is the bearer token's user, never the body. A reviewer status
    (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) is a VERIFY: ABAC R5 has
    required a reviewer role and independence from the project's owner before
    this runs; here the reviewer must also be independent of the submitter and
    the submitting company, and VERIFIED must name a document on file.
    """
    actor = _require_actor(authorization)
    _log_foreign_submitted_by(request.submitted_by, actor)
    _validate_evidence_write(
        request.evidence_key, request.new_status, request.maturity,
        _existing_maturity(request.project_id, request.evidence_key) if request.maturity else None,
    )
    if request.new_status in _REVIEWER_STATUSES:
        _require_independent_reviewer(actor, request.project_id, request.evidence_key)
    document = _document_on_file(request.project_id, request.evidence_key, request.new_status,
                                 request.document_sha256)
    _upsert_evidence(request.project_id, request.evidence_key, request.new_status, actor["user_id"],
                     request.notes, document_sha256=document, maturity=request.maturity)
    evidence = _load_evidence(request.project_id)
    result = await reevaluate(request.project_id, actor=actor["user_id"], evidence=evidence,
                              reason=f"evidence {request.evidence_key} -> {request.new_status}")
    return _attach_assignments(result["snapshot"], evidence, actor, request.project_id)


@router.get("/evidence")
async def list_evidence(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    return {"project_id": project_id, "evidence": evidence, "count": len(evidence)}



class EvidenceAssignRequest(BaseModel):
    project_id: str
    evidence_key: str
    assignee_user_id: Optional[str] = None   # None unassigns


class EvidenceCommitRequest(BaseModel):
    project_id: str
    evidence_key: str
    due_date: str                            # YYYY-MM-DD, today or later


def _project_owner(project_id: str) -> Optional[str]:
    from app.core.projects_store import fetch_project
    try:
        row = fetch_project(project_id)
    except Exception:
        return None
    return (row or {}).get("owner_tenant_id")


def _owner_gate(actor: dict, project_id: str) -> str:
    """The project's owning company, if the caller may manage its requests."""
    owner = _project_owner(project_id)
    if owner is None:
        raise HTTPException(status_code=404, detail={
            "code": "PROJECT_HAS_NO_OWNER",
            "message": f"'{project_id}' has no owning company, so there is no one to assign it to."})
    if not actor.get("is_platform_admin") and actor.get("company_id") != owner:
        raise HTTPException(status_code=403, detail={
            "code": "NOT_PROJECT_OWNER",
            "message": "Only the company that owns this project can assign its evidence requests."})
    return owner


@router.post("/evidence/assign")
async def assign_evidence(request: EvidenceAssignRequest,
                          authorization: str | None = Header(default=None)):
    """Name the person who must produce an evidence item.

    Only the company that owns the project (or a platform admin) may assign, and
    only to an ACTIVE account of that company: a request routed to another
    tenant would disclose the project to it. Creates the item as an open
    NOT_STARTED request if it has no row yet.

    Assignment CREATES a request; the assignee ACCEPTS it by committing to a date
    (POST /evidence/commit). So a reassignment clears the date and the
    commitment — a date is one person's word and does not pass to the next.
    Every change is audited.
    """
    actor = _require_actor(authorization)
    _validate_evidence_write(request.evidence_key, None, None, None)
    owner = _owner_gate(actor, request.project_id)
    reason = _inapplicable(request.project_id, request.evidence_key)
    if reason and request.assignee_user_id:
        # Withdrawing (assignee None) stays allowed: it is how a request raised
        # for an item the project does not need is taken back.
        raise HTTPException(status_code=422, detail={
            "code": "ITEM_NOT_APPLICABLE", "reason": reason,
            "message": f"'{request.evidence_key}' {_NOT_APPLICABLE_MESSAGE[reason]}, so there is "
                       "nothing to request. An existing request can only be withdrawn."})
    if request.assignee_user_id:
        person = _account_directory([request.assignee_user_id]).get(request.assignee_user_id)
        if not person or person["company_id"] != owner or person["account_state"] != "ACTIVE":
            raise HTTPException(status_code=422, detail={
                "code": "ASSIGNEE_NOT_AN_ACTIVE_ACCOUNT_OF_THE_OWNER",
                "message": "Assign to an active account of the company that owns the project."})

    who = actor.get("user_id") or actor.get("email") or "unknown"
    conn = _get_db()
    _ensure_tables(conn)
    old = conn.execute(
        "SELECT status, assignee_user_id, due_date FROM bankability_evidence "
        "WHERE project_id = ? AND evidence_key = ?",
        (request.project_id, request.evidence_key),
    ).fetchone()
    old_assignee = old["assignee_user_id"] if old else None
    changed = old is None or old_assignee != request.assignee_user_id
    if old and changed:
        conn.execute(
            "UPDATE bankability_evidence SET assignee_user_id = ?, due_date = NULL, committed_at = NULL, "
            "committed_by = NULL, assigned_by = ?, assigned_at = datetime('now'), updated_at = datetime('now') "
            "WHERE project_id = ? AND evidence_key = ?",
            (request.assignee_user_id, who, request.project_id, request.evidence_key))
    elif old is None:
        conn.execute(
            "INSERT INTO bankability_evidence (project_id, evidence_key, status, assignee_user_id, "
            "assigned_by, assigned_at, updated_at) "
            "VALUES (?, ?, 'NOT_STARTED', ?, ?, datetime('now'), datetime('now'))",
            (request.project_id, request.evidence_key, request.assignee_user_id, who))
    status = old["status"] if old else "NOT_STARTED"
    if changed:
        conn.execute(
            "INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, "
            "old_assignee, new_assignee, old_due_date, new_due_date) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, NULL)",
            (request.project_id, request.evidence_key, old["status"] if old else None, status, who,
             old_assignee, request.assignee_user_id, old["due_date"] if old else None))
    conn.commit()
    conn.close()
    return {"project_id": request.project_id, "evidence_key": request.evidence_key, "status": status,
            "assignee_user_id": request.assignee_user_id, "commitment": "NOT_COMMITTED"
            if request.assignee_user_id else "UNASSIGNED", "assigned_by": who}


@router.post("/evidence/commit")
async def commit_evidence(request: EvidenceCommitRequest,
                          authorization: str | None = Header(default=None)):
    """The assignee accepts a request by committing to a date — or moves it.

    Only the assignee can commit: a date set on someone's behalf is a date they
    never gave. Not even a platform admin can. The date must be today or later;
    moving a committed date is allowed and every change is audited, so a slipped
    date stays visible as a slip.
    """
    from app.core.evidence_due_dates import parse_commitment_date

    actor = _require_actor(authorization)
    try:
        parse_commitment_date(request.due_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "DUE_DATE_INVALID", "message": str(exc)
                            if "passed" in str(exc) else "due_date must be YYYY-MM-DD."})
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT status, assignee_user_id, due_date FROM bankability_evidence "
        "WHERE project_id = ? AND evidence_key = ?",
        (request.project_id, request.evidence_key),
    ).fetchone()
    if not row or not row["assignee_user_id"]:
        conn.close()
        raise HTTPException(status_code=409, detail={
            "code": "NOT_ASSIGNED", "message": "Nobody is assigned to this request yet."})
    if row["assignee_user_id"] != actor.get("user_id"):
        conn.close()
        raise HTTPException(status_code=403, detail={
            "code": "ONLY_THE_ASSIGNEE_CAN_COMMIT",
            "message": "Only the person assigned to this request can commit to a date for it."})
    if row["status"] == "VERIFIED":
        conn.close()
        raise HTTPException(status_code=409, detail={
            "code": "ALREADY_VERIFIED", "message": "This item is verified; there is nothing left to commit to."})
    reason = _inapplicable(request.project_id, request.evidence_key)
    if reason:
        conn.close()
        raise HTTPException(status_code=409, detail={
            "code": "ITEM_NOT_APPLICABLE", "reason": reason,
            "message": f"'{request.evidence_key}' {_NOT_APPLICABLE_MESSAGE[reason]}; there is nothing "
                       "to commit to. The project owner can withdraw the request."})
    who = actor["user_id"]
    conn.execute(
        "UPDATE bankability_evidence SET due_date = ?, committed_at = datetime('now'), committed_by = ?, "
        "updated_at = datetime('now') WHERE project_id = ? AND evidence_key = ?",
        (request.due_date, who, request.project_id, request.evidence_key))
    if row["due_date"] != request.due_date:
        conn.execute(
            "INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, "
            "old_assignee, new_assignee, old_due_date, new_due_date) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)",
            (request.project_id, request.evidence_key, row["status"], row["status"], who,
             who, who, row["due_date"], request.due_date))
    conn.commit()
    conn.close()
    return {"project_id": request.project_id, "evidence_key": request.evidence_key,
            "due_date": request.due_date, "committed_by": who, "commitment": "COMMITTED",
            "moved_from": row["due_date"]}


@router.get("/evidence/assignable")
async def list_assignable_accounts(project_id: str = Query(...),
                                   authorization: str | None = Header(default=None)):
    """Active accounts of the project's owning company — the only valid assignees."""
    actor = _require_actor(authorization)
    owner = _owner_gate(actor, project_id)
    try:
        from app.core.auth import auth_db_connection
        conn = auth_db_connection()
        try:
            rows = conn.execute(
                "SELECT user_id, user_name, business_function FROM auth_users "
                "WHERE company_id = ? AND account_state = 'ACTIVE' ORDER BY user_name",
                (owner,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    return {"project_id": project_id, "company_id": owner,
            "accounts": [{"user_id": r["user_id"], "name": r["user_name"],
                          "business_function": r["business_function"]} for r in rows]}


@router.get("/evidence/assigned-to-me")
async def list_my_evidence_requests(authorization: str | None = Header(default=None)):
    """Open evidence requests assigned to the caller, overdue first, then uncommitted.

    Requests on items the project does not need (its power model, or lender
    protection under balance-sheet funding) are not open work: they are listed
    apart under `not_required` and counted nowhere."""
    from app.core.bankability_engine import EVIDENCE_GATE_MAP
    from app.core.evidence_due_dates import commitment_state

    actor = _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT project_id, evidence_key, status, assignee_user_id, due_date, committed_at, notes, "
        "assigned_at FROM bankability_evidence "
        "WHERE assignee_user_id = ? AND status <> 'VERIFIED' ORDER BY project_id, evidence_key",
        (actor.get("user_id"),),
    ).fetchall()
    conn.close()
    order = {"OVERDUE": 0, "NOT_COMMITTED": 1, "COMMITTED": 2}
    out, not_required = [], []
    for r in rows:
        reason = _inapplicable(r["project_id"], r["evidence_key"])
        if reason:
            not_required.append({**dict(r), "gate_id": EVIDENCE_GATE_MAP.get(r["evidence_key"]),
                                 "commitment": "NOT_REQUIRED", "not_applicable_reason": reason})
            continue
        state, days = commitment_state(dict(r))
        out.append({**dict(r), "gate_id": EVIDENCE_GATE_MAP.get(r["evidence_key"]),
                    "commitment": state, "days_overdue": days})
    out.sort(key=lambda x: (order.get(x["commitment"], 3), -x["days_overdue"], x["due_date"] or ""))
    return {"user_id": actor.get("user_id"), "count": len(out),
            "overdue": sum(x["commitment"] == "OVERDUE" for x in out),
            "not_committed": sum(x["commitment"] == "NOT_COMMITTED" for x in out),
            "requests": out, "not_required": not_required}


# ── Commitment cards (rules 4.0.0) ───────────────────────────────────────────

class TermsWriteRequest(BaseModel):
    project_id: str
    card_type: str      # offtake | epc | schedule | supply | model
    terms: dict = {}    # replaces the card; {} clears it


@router.get("/terms")
async def get_commitment_terms(project_id: str = Query(...),
                               authorization: str | None = Header(default=None)):
    """The project's commitment cards, plus the field specification the UI
    renders its forms from (the same spec the engine reads). `can_edit` mirrors
    the write rule in put_commitment_terms, so the screen offers editing only to
    those the write will accept."""
    from app.core.bankability_engine import COMMITMENT_CARD_FIELDS, TERMS_CARD_GATE

    actor = _require_actor(authorization)
    owner = _project_owner(project_id)
    can_edit = owner is not None and (bool(actor.get("is_platform_admin")) or actor.get("company_id") == owner)
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT card_type, terms_json, updated_by, updated_at FROM commitment_terms WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    conn.close()
    cards = {}
    for r in rows:
        try:
            terms = json.loads(r["terms_json"] or "{}")
        except (TypeError, ValueError):
            terms = {}
        cards[r["card_type"]] = {"terms": terms, "updated_by": r["updated_by"], "updated_at": r["updated_at"]}
    return {"project_id": project_id, "cards": cards, "can_edit": can_edit,
            "card_fields": COMMITMENT_CARD_FIELDS, "card_gates": TERMS_CARD_GATE}


@router.put("/terms")
async def put_commitment_terms(request: TermsWriteRequest,
                               authorization: str | None = Header(default=None)):
    """Replace one commitment card. Only the company that owns the project (or a
    platform admin) may write its cards — they are the producer's statement of
    what it has signed and been promised. Every change is audited, old and new."""
    from app.core.commitment_terms import TermsValidationError, validate_card

    actor = _require_actor(authorization)
    _owner_gate(actor, request.project_id)
    try:
        clean = validate_card(request.card_type, request.terms)
    except TermsValidationError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "TERMS_INVALID", "problems": exc.problems,
            "message": "The card was not saved: " + "; ".join(exc.problems)})

    who = actor.get("user_id") or actor.get("email") or "unknown"
    new_json = json.dumps(clean, sort_keys=True)
    conn = _get_db()
    _ensure_tables(conn)
    old = conn.execute(
        "SELECT terms_json FROM commitment_terms WHERE project_id = ? AND card_type = ?",
        (request.project_id, request.card_type),
    ).fetchone()
    old_json = old["terms_json"] if old else None
    if old is None:
        conn.execute(
            "INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (request.project_id, request.card_type, new_json, who))
    elif old_json != new_json:
        conn.execute(
            "UPDATE commitment_terms SET terms_json = ?, updated_by = ?, updated_at = datetime('now') "
            "WHERE project_id = ? AND card_type = ?",
            (new_json, who, request.project_id, request.card_type))
    if old_json != new_json:
        conn.execute(
            "INSERT INTO commitment_terms_events (project_id, card_type, old_json, new_json, actor, at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (request.project_id, request.card_type, old_json, new_json, who))
    conn.commit()
    conn.close()
    reevaluation = None
    if old_json != new_json:
        # Every changed contract records a new VERSION on its token; until the
        # counterparty (or appointed reviewer) confirms it, the changed fields do
        # not reach the engine.
        from app.core.contract_tokens import record_versions
        try:
            record_versions(request.project_id, _load_terms_raw(request.project_id), who, actor.get("company_id"))
        except Exception as exc:  # noqa: BLE001 — fail closed: an unrecorded version is never confirmed
            logger.warning("card saved for %s but its token version was not recorded: %s", request.project_id, exc)
        # A term change can pass or fail a cross-contract check: re-evaluate now.
        # The card is saved either way; an engine outage withdraws the stored
        # state (fail closed) rather than leaving it standing for old terms.
        try:
            reevaluation = (await reevaluate(request.project_id, reason=f"terms {request.card_type}",
                                             actor=who))["changes"]
        except HTTPException as exc:
            reevaluation = {"error": exc.detail, "state_withdrawn": True}
    return {"project_id": request.project_id, "card_type": request.card_type, "terms": clean,
            "changed": old_json != new_json, "updated_by": who, "reevaluation": reevaluation}


@router.get("/terms/events")
async def list_commitment_terms_events(project_id: str = Query(...),
                                       authorization: str | None = Header(default=None)):
    """Append-only history of card changes."""
    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT card_type, old_json, new_json, actor, at FROM commitment_terms_events "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 200",
        (project_id,),
    ).fetchall()
    conn.close()
    return {"project_id": project_id, "events": [dict(r) for r in rows]}


# ── Evidence documents — evidence without a document is a claim ─────────────

EVIDENCE_DOCS_DIR = os.getenv("GEX_EVIDENCE_DOCS_DIR", "data/evidence_docs")
_MAX_DOC_BYTES = 25 * 1024 * 1024  # 25 MB


def _require_actor(authorization: str | None) -> dict:
    from app.core.auth import get_user_payload_from_token
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return get_user_payload_from_token(authorization.split(" ", 1)[1].strip())
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/evidence/document")
async def upload_evidence_document(
    project_id: str = Form(...),
    evidence_key: str = Form(...),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    """
    Attach a document to an evidence item. Stores the file with its sha256,
    records the upload in evidence_documents, moves the item to SUBMITTED,
    and logs the transition (actor + document hash) in evidence_events.
    """
    import hashlib
    from pathlib import Path

    actor = _require_actor(authorization)
    # Validate before touching disk: evidence_key names a directory below, and
    # an unknown or retired key would store a file no gate can ever see.
    _validate_evidence_write(evidence_key, None, None, None)
    content = await file.read()
    if len(content) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds 25 MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Empty file")

    sha = hashlib.sha256(content).hexdigest()
    safe_name = os.path.basename(file.filename or "document.bin")
    dest_dir = Path(EVIDENCE_DOCS_DIR) / project_id / evidence_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{sha[:12]}_{safe_name}"
    dest.write_bytes(content)

    # The user id, as on every evidence write — the uploader becomes the
    # submitter, and a reviewer's independence is checked against that id.
    who = actor["user_id"]
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute(
        "INSERT INTO evidence_documents (project_id, evidence_key, filename, sha256, size_bytes, stored_path, uploaded_by, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (project_id, evidence_key, safe_name, sha, len(content), str(dest), who),
    )
    conn.commit()
    conn.close()

    # Document arrival moves the item to SUBMITTED (never auto-VERIFIED —
    # verification is a separate, human transition).
    _upsert_evidence(project_id, evidence_key, "SUBMITTED", who, document_sha256=sha)
    # A new document returns a verified item to SUBMITTED, which can lower the
    # state: re-evaluate now, not at the next unrelated write.
    try:
        await reevaluate(project_id, reason=f"document {evidence_key}", actor=who)
    except HTTPException as exc:
        logger.warning("document stored for %s but re-evaluation failed: %s", project_id, exc.detail)

    return {
        "project_id": project_id,
        "evidence_key": evidence_key,
        "filename": safe_name,
        "sha256": sha,
        "size_bytes": len(content),
        "status": "SUBMITTED",
        "uploaded_by": who,
    }


@router.get("/evidence/documents")
async def list_evidence_documents(
    project_id: str = Query(...),
    evidence_key: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Documents on file for a project's evidence items (metadata + hashes)."""
    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    if evidence_key:
        rows = conn.execute(
            "SELECT evidence_key, filename, sha256, size_bytes, uploaded_by, uploaded_at FROM evidence_documents "
            "WHERE project_id = ? AND evidence_key = ? ORDER BY id DESC",
            (project_id, evidence_key),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT evidence_key, filename, sha256, size_bytes, uploaded_by, uploaded_at FROM evidence_documents "
            "WHERE project_id = ? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    conn.close()
    return {"project_id": project_id, "documents": [dict(r) for r in rows]}


@router.get("/evidence/document/{sha256}/download")
async def download_evidence_document(sha256: str, authorization: str | None = Header(default=None)):
    """Serve a stored evidence document by content hash (auth required)."""
    from fastapi.responses import FileResponse

    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT filename, stored_path FROM evidence_documents WHERE sha256 = ? ORDER BY id DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    conn.close()
    if not row or not os.path.exists(row["stored_path"]):
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(row["stored_path"], filename=row["filename"])


@router.get("/evidence/events")
async def list_evidence_events(
    project_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Append-only evidence audit trail: status transitions, maturity changes and reassignments."""
    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT evidence_key, old_status, new_status, actor, at, document_sha256, "
        "old_maturity, new_maturity, old_assignee, new_assignee, old_due_date, new_due_date "
        "FROM evidence_events "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 500",
        (project_id,),
    ).fetchall()
    conn.close()
    return {"project_id": project_id, "events": [dict(r) for r in rows]}

# REMOVED 2026-09-23 — POST /evidence/seed
# ------------------------------------------
# This endpoint wrote 52 fabricated evidence rows per call, as `demo_seed` with
# the note "Seeded demo", straight into `bankability_evidence` — the table the
# gates, the bankability state and the capital unlocks are computed from. Its
# `project_id` was a query parameter with no allow-list, so it seeded REAL
# projects as readily as the placeholder one.
#
# Measured before removal: 125 of 127 evidence rows in PostgreSQL were
# `demo_seed`, and three `bankability_snapshots` had been computed from them —
# a completion percentage and a risk classification derived entirely from
# invented evidence, presented in the same UI as the two real rows.
#
# A demo fixture belongs in a test or a clearly-labelled sandbox, never behind
# an HTTP verb that writes the system of record. If a seeded project is needed
# for a demonstration, seed it into a throwaway database, not this one.

@router.get("/regression/check")
async def check_regression(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    previous_state = _get_project_state(project_id)
    return await _call_engine("/regression/check", method="POST", json_data={
        "project_id": project_id, "evidence": evidence, "previous_state": previous_state,
        **_engine_context(project_id),
    })


@router.get("/health")
async def health_check():
    db_ok = engine_ok = False
    try:
        conn = _get_db(); _ensure_tables(conn); conn.close(); db_ok = True
    except Exception: pass
    try:
        r = await _call_engine("/health"); engine_ok = r.get("status") == "healthy"
    except Exception: pass
    return {"status": "healthy" if db_ok and engine_ok else "degraded",
            "platform_db": "ok" if db_ok else "error", "engine": "ok" if engine_ok else "unreachable"}



def verify_by_counterparty(project_id: str, keys: tuple, actor: dict, *, note: str) -> list[str]:
    """The counterparty's confirmation on a contract token verifies the
    contract's own instrument evidence (JML 2026-10-28): each key that was
    SUBMITTED with a document on file, by someone independent of the
    counterparty's company. Returns the keys verified."""
    conn = _get_db()
    _ensure_tables(conn)
    rows = {r["evidence_key"]: dict(r) for r in conn.execute(
        "SELECT evidence_key, status, submitted_by, document_hash FROM bankability_evidence WHERE project_id = ?",
        (project_id,)).fetchall()}
    conn.close()
    done = []
    for key in keys:
        row = rows.get(key)
        if not row or row["status"] != "SUBMITTED" or not row["document_hash"]:
            continue
        account = _account_directory([row["submitted_by"]]).get(row["submitted_by"]) if row["submitted_by"] else None
        if _independence_refusal(actor, row["submitted_by"], account):
            continue
        _upsert_evidence(project_id, key, "VERIFIED", actor["user_id"], note, document_sha256=row["document_hash"])
        done.append(key)
    return done
