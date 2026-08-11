"""
evidence_ledger.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Cross-cutting append-only evidence hash chain. Every piece of evidence
submitted to the platform (technical reports, cost estimates, certifications,
counterparty due diligence, sovereign instruments) is recorded in an
immutable ledger with SHA-256 chain integrity.

Design principles:
  - Append-only: no updates or deletes — evidence is permanent
  - Hash chain: each entry links to the previous via prev_hash
  - Chain verification: walk the chain to detect tampering
  - Category × State grid: feeds the EvidenceDensityTile frontend primitive

Integration points:
  - development_packages.py: evidence_refs link here
  - dfi_criteria.py: evidence_ref links here when criterion status=MET
  - bankability_engine.py: verification_state weights feed effective_score
  - provenance.py: export audit trail references this ledger
  - EvidenceDensityTile.tsx (frontend): /density endpoint feeds the 7×4 grid

SQLite pattern: matches development_packages.py conventions.
"""

import sqlite3
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence-ledger"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class EvidenceCategory(str, Enum):
    TECHNICAL     = "TECHNICAL"
    COST          = "COST"
    REVENUE       = "REVENUE"
    CERTIFICATION = "CERTIFICATION"
    EXECUTION     = "EXECUTION"
    COUNTERPARTY  = "COUNTERPARTY"
    SOVEREIGN     = "SOVEREIGN"


# Assurance axis — imported, NOT redefined (ADR 2026-07-29). This module used to
# declare its own identical copy; one definition, one meaning.
from app.core.verification import VerificationState  # noqa: E402


class ClaimState(str, Enum):
    """
    Lifecycle axis — mirrors the truth-stack ClaimState (the canonical evidence
    vocabulary in app/core/vocabulary.py).

    Deliberately SEPARATE from VerificationState: they are orthogonal.
    VerificationState answers "how well-checked is this artifact" (and carries
    the gate-scoring weight). ClaimState answers "what is the status of the
    assertion it supports". An artifact can be AUDITED and SUPERSEDED at the
    same time — both true, on different axes. Collapsing them loses information.
    """

    ASSERTED   = "asserted"
    SUBMITTED  = "submitted"
    VERIFIED   = "verified"
    SATISFIED  = "satisfied"
    WAIVED     = "waived"
    EXPIRED    = "expired"
    REJECTED   = "rejected"
    FAILED     = "failed"
    SUPERSEDED = "superseded"


# Claim states that no longer support a gate (F2 — the ledger can now record these).
CLAIM_TERMINAL_INVALID = frozenset({
    ClaimState.EXPIRED, ClaimState.REJECTED, ClaimState.FAILED, ClaimState.SUPERSEDED,
})


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class EvidenceCreate(BaseModel):
    project_id: str
    entity_type: str = Field(..., description="e.g. PACKAGE, TOKEN, TRANCHE, CONTRACT")
    entity_id: str = Field(..., description="FK to the entity")
    category: EvidenceCategory
    document_ref: str = Field(..., description="File/upload reference")
    verification_state: VerificationState = VerificationState.UNVERIFIED
    claim_state: ClaimState = ClaimState.ASSERTED
    reviewer_id: Optional[str] = None
    submitted_by: str
    verified_by: Optional[str] = Field(
        None,
        description="Who moved assurance beyond UNVERIFIED. Required for "
                    "SUBMITTED/CONFIRMED/AUDITED, and must differ from submitted_by.",
    )
    valid_until: Optional[str] = Field(
        None, description="ISO date after which this evidence lapses (F2/R3)."
    )
    superseded_by: Optional[str] = Field(
        None, description="evidence_id of the entry that replaces this one."
    )


class EvidenceResponse(BaseModel):
    evidence_id: str
    project_id: str
    entity_type: str
    entity_id: str
    category: str
    document_ref: str
    verification_state: str
    claim_state: str
    reviewer_id: Optional[str]
    submitted_by: str
    verified_by: Optional[str]
    valid_until: Optional[str]
    superseded_by: Optional[str]
    hash: str
    prev_hash: Optional[str]
    timestamp: str
    chain_intact: bool
    # Presentation comes from the canonical registry — never hardcoded here.
    verification_label: Optional[str] = None
    claim_label: Optional[str] = None
    is_currently_valid: Optional[bool] = None


class DensityCell(BaseModel):
    category: str
    state: str
    count: int


class DensityGrid(BaseModel):
    project_id: str
    grid: list[DensityCell]
    total_evidence: int


class ChainVerification(BaseModel):
    project_id: str
    total_entries: int
    chain_intact: bool
    broken_at: Optional[str] = Field(None, description="evidence_id where chain broke, if any")


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

def get_db():
    """
    Connection for the hash-chained ledger — SQLite or PostgreSQL by
    configuration (EVIDENCE_DB_BACKEND).

    The chain itself is backend-agnostic: _compute_hash/_verify_single are pure
    functions over row values, so the same digest is produced either side. That
    is verified, not assumed — tests/test_evidence_slice.py builds a chain in
    PostgreSQL, validates it, then tampers and confirms detection.
    """
    from app.core.db_backend import evidence_connection, evidence_is_postgres

    conn = evidence_connection()
    if not evidence_is_postgres():
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Create the evidence_ledger table (append-only, no update/delete).

    SQLite only. On PostgreSQL the schema is owned by alembic (migration 034),
    which also enables RLS — a CREATE TABLE IF NOT EXISTS here would either
    no-op or, worse, create an unprotected table without policies.
    """
    from app.core.db_backend import evidence_is_postgres

    if evidence_is_postgres():
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_ledger (
            evidence_id        TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            entity_type        TEXT NOT NULL,
            entity_id          TEXT NOT NULL,
            category           TEXT NOT NULL,
            document_ref       TEXT NOT NULL,
            -- Assurance axis: how well-checked the artifact is (drives gate weight)
            verification_state TEXT NOT NULL DEFAULT 'UNVERIFIED',
            -- Lifecycle axis: status of the assertion the artifact supports (F2)
            claim_state        TEXT NOT NULL DEFAULT 'asserted',
            reviewer_id        TEXT,
            submitted_by       TEXT NOT NULL,
            -- Custody: who moved assurance forward. Mandatory above UNVERIFIED
            -- and inside the hash — chain of custody without the custodian is
            -- not chain of custody (F3).
            verified_by        TEXT,
            -- Expiry / supersession, so the immutable store can record them (F2/R3)
            valid_until        TEXT,
            superseded_by      TEXT,
            hash               TEXT NOT NULL,
            prev_hash          TEXT,
            timestamp          TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_project ON evidence_ledger(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_entity ON evidence_ledger(entity_type, entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_category ON evidence_ledger(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_state ON evidence_ledger(verification_state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_timestamp ON evidence_ledger(timestamp)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_hash(evidence_id: str, entity_id: str, category: str,
                  document_ref: str, prev_hash: Optional[str], timestamp: str,
                  verification_state: str = "", claim_state: str = "",
                  submitted_by: str = "", verified_by: Optional[str] = None) -> str:
    """
    SHA-256 hash chain.

    The digest covers the assurance state, the claim state, and BOTH actors —
    not just the document reference (ADR 2026-07-29). Previously an entry's
    verification_state or submitted_by could be edited in place without
    breaking the chain, which made the tamper-evidence partial: the artifact
    was protected, the assurance claim about it was not.
    """
    content = (
        f"{evidence_id}{entity_id}{category}{document_ref}"
        f"{prev_hash or ''}{timestamp}"
        f"{verification_state}{claim_state}{submitted_by}{verified_by or ''}"
    )
    return hashlib.sha256(content.encode()).hexdigest()


def _verify_single(row, expected_prev_hash: Optional[str]) -> bool:
    """Verify a single entry's hash and chain link."""
    computed = _compute_hash(
        row["evidence_id"], row["entity_id"], row["category"],
        row["document_ref"], row["prev_hash"], row["timestamp"],
        row["verification_state"], row["claim_state"],
        row["submitted_by"], row["verified_by"],
    )
    if computed != row["hash"]:
        return False
    if row["prev_hash"] != expected_prev_hash:
        return False
    return True


def _is_lapsed(valid_until: Optional[str], now: Optional[str] = None) -> bool:
    """True once the validity date has passed — a controlled document past
    revalidation is invalid, not merely old (R3)."""
    if not valid_until:
        return False
    return (now or _now()) > valid_until


def _row_to_response(row, chain_intact: bool = True) -> dict:
    from app.core.vocabulary import display_label

    claim = row["claim_state"]
    lapsed = _is_lapsed(row["valid_until"])
    return {
        "evidence_id": row["evidence_id"],
        "project_id": row["project_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "category": row["category"],
        "document_ref": row["document_ref"],
        "verification_state": row["verification_state"],
        "claim_state": claim,
        "reviewer_id": row["reviewer_id"],
        "submitted_by": row["submitted_by"],
        "verified_by": row["verified_by"],
        "valid_until": row["valid_until"],
        "superseded_by": row["superseded_by"],
        "hash": row["hash"],
        "prev_hash": row["prev_hash"],
        "timestamp": row["timestamp"],
        "chain_intact": chain_intact,
        "verification_label": display_label("evidence_state", claim),
        "claim_label": display_label("evidence_state", claim),
        # Lapsed evidence stops supporting a gate even before an EXPIRED entry
        # is appended — expiry propagates rather than waiting to be noticed.
        "is_currently_valid": (
            not lapsed
            and ClaimState(claim) not in CLAIM_TERMINAL_INVALID
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=EvidenceResponse, status_code=201)
def append_evidence(ev: EvidenceCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Append new evidence entry to the ledger. Append-only — no updates or deletes.
    Hash chain links each entry to the previous one for tamper detection.
    """
    evidence_id = str(uuid.uuid4())
    now = _now()

    # ── Custody rules (F3 / R2, ADR 2026-07-29) ──────────────────────────────
    # Assurance beyond UNVERIFIED is a claim about who checked the artifact.
    # Recording it without the checker is what made chain of custody incomplete.
    if ev.verification_state != VerificationState.UNVERIFIED and not ev.verified_by:
        raise HTTPException(
            400,
            f"verification_state={ev.verification_state.value} requires verified_by — "
            "an assurance level cannot be recorded without the party asserting it.",
        )
    # Segregation of duties: the submitter cannot be their own verifier.
    if ev.verified_by and ev.verified_by == ev.submitted_by:
        raise HTTPException(
            400,
            "verified_by must differ from submitted_by (segregation of duties).",
        )

    # Get previous hash for chain continuity (project-scoped chain)
    prev = db.execute(
        "SELECT hash FROM evidence_ledger WHERE project_id=? ORDER BY timestamp DESC LIMIT 1",
        (ev.project_id,)
    ).fetchone()
    prev_hash = prev["hash"] if prev else None

    entry_hash = _compute_hash(
        evidence_id, ev.entity_id, ev.category.value,
        ev.document_ref, prev_hash, now,
        ev.verification_state.value, ev.claim_state.value,
        ev.submitted_by, ev.verified_by,
    )

    db.execute("""
        INSERT INTO evidence_ledger
        (evidence_id, project_id, entity_type, entity_id, category,
         document_ref, verification_state, claim_state, reviewer_id, submitted_by,
         verified_by, valid_until, superseded_by, hash, prev_hash, timestamp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        evidence_id, ev.project_id, ev.entity_type, ev.entity_id,
        ev.category.value, ev.document_ref, ev.verification_state.value,
        ev.claim_state.value, ev.reviewer_id, ev.submitted_by,
        ev.verified_by, ev.valid_until, ev.superseded_by,
        entry_hash, prev_hash, now
    ))
    db.commit()

    row = db.execute("SELECT * FROM evidence_ledger WHERE evidence_id=?", (evidence_id,)).fetchone()
    return _row_to_response(row, chain_intact=True)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(evidence_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Get single evidence entry with chain verification."""
    row = db.execute("SELECT * FROM evidence_ledger WHERE evidence_id=?", (evidence_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Evidence {evidence_id} not found")

    # Verify this entry's hash
    computed = _compute_hash(
        row["evidence_id"], row["entity_id"], row["category"],
        row["document_ref"], row["prev_hash"], row["timestamp"]
    )
    chain_intact = (computed == row["hash"])

    return _row_to_response(row, chain_intact=chain_intact)


@router.get("/entity/{entity_type}/{entity_id}", response_model=list[EvidenceResponse])
def list_entity_evidence(
    entity_type: str,
    entity_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """All evidence for a specific entity (package, token, tranche, contract)."""
    rows = db.execute(
        "SELECT * FROM evidence_ledger WHERE entity_type=? AND entity_id=? ORDER BY timestamp ASC",
        (entity_type, entity_id)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/project/{project_id}", response_model=list[EvidenceResponse])
def list_project_evidence(
    project_id: str,
    category: Optional[EvidenceCategory] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """All evidence for a project, with optional category filter."""
    query = "SELECT * FROM evidence_ledger WHERE project_id=?"
    params: list = [project_id]

    if category:
        query += " AND category=?"; params.append(category.value)

    query += " ORDER BY timestamp ASC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/project/{project_id}/density", response_model=DensityGrid)
def evidence_density(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Returns a 7x4 grid (7 categories x 4 verification states) with counts.
    Feeds the EvidenceDensityTile frontend component (Appendix E.5).
    """
    rows = db.execute(
        "SELECT category, verification_state, COUNT(*) as cnt "
        "FROM evidence_ledger WHERE project_id=? "
        "GROUP BY category, verification_state",
        (project_id,)
    ).fetchall()

    # Build full 7x4 grid — include zero-count cells
    grid = []
    for cat in EvidenceCategory:
        for state in VerificationState:
            count = 0
            for r in rows:
                if r["category"] == cat.value and r["verification_state"] == state.value:
                    count = r["cnt"]
                    break
            grid.append(DensityCell(category=cat.value, state=state.value, count=count))

    total = sum(cell.count for cell in grid)
    return DensityGrid(project_id=project_id, grid=grid, total_evidence=total)


@router.get("/project/{project_id}/verify-chain", response_model=ChainVerification)
def verify_chain(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Walk entire evidence chain for a project and verify integrity.
    Returns chain_intact=True if all hashes and prev_hash links are valid.
    """
    rows = db.execute(
        "SELECT * FROM evidence_ledger WHERE project_id=? ORDER BY timestamp ASC",
        (project_id,)
    ).fetchall()

    if not rows:
        return ChainVerification(
            project_id=project_id,
            total_entries=0,
            chain_intact=True,
            broken_at=None
        )

    expected_prev = None
    for row in rows:
        if not _verify_single(row, expected_prev):
            return ChainVerification(
                project_id=project_id,
                total_entries=len(rows),
                chain_intact=False,
                broken_at=row["evidence_id"]
            )
        expected_prev = row["hash"]

    return ChainVerification(
        project_id=project_id,
        total_entries=len(rows),
        chain_intact=True,
        broken_at=None
    )
