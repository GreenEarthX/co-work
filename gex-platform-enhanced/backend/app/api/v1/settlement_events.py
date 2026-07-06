"""
settlement_events.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Cash-leg settlement records for matched contracts. Every trade on the
platform produces a settlement event that tracks the flow of funds between
buyer and seller. Settlement events are the financial proof layer that
complements the token provenance chain.

Design principles:
  - contract matched -> settlement created (PENDING)
  - bank confirms wire -> CONFIRMED (payment_reference attached)
  - reconciliation clears -> RECONCILED (auditable end-state)
  - disputed at any point -> DISPUTED (requires manual resolution)

Integration points:
  - FK to contracts_sqlite.py (contract_id)
  - FK to tokens_sqlite.py (token_id)
  - Feeds carbon_attribution.py (settlement_id is required for attribution)
  - Feeds sovereign_instruments.py (settlement proves capital flow for D4N swaps)
  - Event log feeds event_store.py / event_bus.py

ABAC alignment (abac.py):
  - PRODUCER / OFFTAKER: read own settlements
  - FINANCE: read + confirm settlements
  - COMPLIANCE: read + reconcile
  - EXECUTIVE: read-only aggregate

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

router = APIRouter(prefix="/api/v1/settlements", tags=["settlement-events"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class SettlementStatus(str, Enum):
    PENDING     = "PENDING"
    CONFIRMED   = "CONFIRMED"
    RECONCILED  = "RECONCILED"
    DISPUTED    = "DISPUTED"


class SettlementType(str, Enum):
    SPOT     = "SPOT"
    FORWARD  = "FORWARD"
    PARTIAL  = "PARTIAL"


# State machine: PENDING -> CONFIRMED -> RECONCILED  (or PENDING -> DISPUTED)
VALID_TRANSITIONS = {
    SettlementStatus.PENDING:    [SettlementStatus.CONFIRMED, SettlementStatus.DISPUTED],
    SettlementStatus.CONFIRMED:  [SettlementStatus.RECONCILED],
    SettlementStatus.RECONCILED: [],
    SettlementStatus.DISPUTED:   [],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SettlementCreate(BaseModel):
    contract_id:           str = Field(..., description="FK to contracts")
    project_id:            str
    token_id:              str = Field(..., description="FK to tokens")
    counterparty_buyer_id: str
    counterparty_seller_id: str
    settlement_type:       SettlementType
    volume_kg:             float = Field(..., gt=0)
    price_per_kg:          float
    total_amount:          float
    currency:              str = Field(default="EUR", description="ISO 4217 currency code")
    payment_reference:     Optional[str] = Field(None, description="Bank ref when confirmed")
    settlement_date:       Optional[str] = Field(None, description="ISO date")
    matrix_thread_id:      Optional[str] = Field(None, description="Element-Matrix room thread for settlement comms")
    changed_by:            str


class SettlementResponse(BaseModel):
    settlement_id:          str
    contract_id:            str
    project_id:             str
    token_id:               str
    counterparty_buyer_id:  str
    counterparty_seller_id: str
    settlement_type:        str
    settlement_status:      str
    volume_kg:              float
    price_per_kg:           float
    total_amount:           float
    currency:               str
    payment_reference:      Optional[str]
    settlement_date:        Optional[str]
    matrix_thread_id:       Optional[str]
    audit_hash:             str
    version:                int
    created_at:             str
    updated_at:             str


class SettlementProjectSummary(BaseModel):
    project_id:                str
    total_settlements:         int
    total_settled_volume_kg:   float
    total_settled_amount:      float
    by_status:                 dict   # status -> count
    by_counterparty_buyer:     dict   # buyer_id -> total_amount
    by_counterparty_seller:    dict   # seller_id -> total_amount


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Create SETTLEMENT_EVENTS table.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settlement_events (
            settlement_id          TEXT PRIMARY KEY,
            contract_id            TEXT NOT NULL,
            project_id             TEXT NOT NULL,
            token_id               TEXT NOT NULL,
            counterparty_buyer_id  TEXT NOT NULL,
            counterparty_seller_id TEXT NOT NULL,
            settlement_type        TEXT NOT NULL,
            settlement_status      TEXT NOT NULL DEFAULT 'PENDING',
            volume_kg              REAL NOT NULL,
            price_per_kg           REAL NOT NULL,
            total_amount           REAL NOT NULL,
            currency               TEXT NOT NULL DEFAULT 'EUR',
            payment_reference      TEXT,
            settlement_date        TEXT,
            matrix_thread_id       TEXT,
            audit_hash             TEXT NOT NULL,
            version                INTEGER NOT NULL DEFAULT 1,
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_se_contract ON settlement_events(contract_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_se_project ON settlement_events(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_se_status ON settlement_events(settlement_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_se_token ON settlement_events(token_id)")

    # Audit table — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settlement_event_log (
            event_id       TEXT PRIMARY KEY,
            settlement_id  TEXT NOT NULL,
            project_id     TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            field_changed  TEXT,
            old_value      TEXT,
            new_value      TEXT,
            changed_by     TEXT NOT NULL,
            justification  TEXT,
            event_hash     TEXT NOT NULL,
            prev_hash      TEXT,
            created_at     TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sel_settlement ON settlement_event_log(settlement_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_settlement(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_event(conn, settlement_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM settlement_event_log "
        "WHERE settlement_id=? ORDER BY created_at DESC LIMIT 1",
        (settlement_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "settlement_id": settlement_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO settlement_event_log
        (event_id, settlement_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), settlement_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "settlement_id":          row["settlement_id"],
        "contract_id":            row["contract_id"],
        "project_id":             row["project_id"],
        "token_id":               row["token_id"],
        "counterparty_buyer_id":  row["counterparty_buyer_id"],
        "counterparty_seller_id": row["counterparty_seller_id"],
        "settlement_type":        row["settlement_type"],
        "settlement_status":      row["settlement_status"],
        "volume_kg":              row["volume_kg"],
        "price_per_kg":           row["price_per_kg"],
        "total_amount":           row["total_amount"],
        "currency":               row["currency"],
        "payment_reference":      row["payment_reference"],
        "settlement_date":        row["settlement_date"],
        "matrix_thread_id":       row["matrix_thread_id"] if "matrix_thread_id" in row.keys() else None,
        "audit_hash":             row["audit_hash"],
        "version":                row["version"],
        "created_at":             row["created_at"],
        "updated_at":             row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=SettlementResponse, status_code=201)
def create_settlement(s: SettlementCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a settlement event for a matched contract.
    Initial status is always PENDING.
    Fires event: settlement.created
    """
    settlement_id = str(uuid.uuid4())
    now = _now()

    content = {
        "settlement_id": settlement_id,
        "contract_id": s.contract_id,
        "project_id": s.project_id,
        "token_id": s.token_id,
        "volume_kg": s.volume_kg,
        "total_amount": s.total_amount,
        "created_at": now,
    }
    audit_hash = _hash_settlement(content)

    db.execute("""
        INSERT INTO settlement_events
        (settlement_id, contract_id, project_id, token_id,
         counterparty_buyer_id, counterparty_seller_id,
         settlement_type, settlement_status, volume_kg, price_per_kg,
         total_amount, currency, payment_reference, settlement_date,
         matrix_thread_id, audit_hash, version, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        settlement_id, s.contract_id, s.project_id, s.token_id,
        s.counterparty_buyer_id, s.counterparty_seller_id,
        s.settlement_type.value, SettlementStatus.PENDING.value,
        s.volume_kg, s.price_per_kg, s.total_amount, s.currency,
        s.payment_reference, s.settlement_date, s.matrix_thread_id,
        audit_hash, 1, now, now
    ))
    _log_event(db, settlement_id, s.project_id, "settlement.created",
               s.changed_by, new_val=s.contract_id)
    db.commit()

    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{settlement_id}", response_model=SettlementResponse)
def get_settlement(settlement_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement {settlement_id} not found")
    return _row_to_response(row)


@router.get("/contract/{contract_id}", response_model=list[SettlementResponse])
def list_by_contract(contract_id: str, db: sqlite3.Connection = Depends(get_db)):
    """All settlements for a contract."""
    rows = db.execute(
        "SELECT * FROM settlement_events WHERE contract_id=? ORDER BY created_at DESC",
        (contract_id,)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/project/{project_id}", response_model=list[SettlementResponse])
def list_by_project(
    project_id: str,
    status: Optional[SettlementStatus] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """All settlements for a project with optional status filter."""
    query = "SELECT * FROM settlement_events WHERE project_id=?"
    params: list = [project_id]
    if status:
        query += " AND settlement_status=?"
        params.append(status.value)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.post("/{settlement_id}/confirm", response_model=SettlementResponse)
def confirm_settlement(
    settlement_id: str,
    payment_reference: str = Query(..., description="Bank payment reference"),
    changed_by: str = Query(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance settlement to CONFIRMED. Requires payment_reference.
    Fires event: settlement.confirmed
    """
    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement {settlement_id} not found")

    current = SettlementStatus(row["settlement_status"])
    if SettlementStatus.CONFIRMED not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(400,
            f"Invalid transition: {current.value} -> CONFIRMED. "
            f"Valid next states: {[s.value for s in VALID_TRANSITIONS.get(current, [])]}"
        )

    now = _now()
    new_hash = _hash_settlement({
        "settlement_id": settlement_id,
        "status": "CONFIRMED",
        "payment_reference": payment_reference,
        "confirmed_at": now,
    })

    db.execute("""
        UPDATE settlement_events
        SET settlement_status=?, payment_reference=?, audit_hash=?,
            version=version+1, updated_at=?
        WHERE settlement_id=?
    """, (SettlementStatus.CONFIRMED.value, payment_reference, new_hash, now, settlement_id))

    _log_event(db, settlement_id, row["project_id"], "settlement.confirmed",
               changed_by, field="settlement_status",
               old_val=current.value, new_val=SettlementStatus.CONFIRMED.value)
    db.commit()

    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{settlement_id}/reconcile", response_model=SettlementResponse)
def reconcile_settlement(
    settlement_id: str,
    changed_by: str = Query(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance settlement to RECONCILED. Must be CONFIRMED first.
    Fires event: settlement.reconciled
    """
    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement {settlement_id} not found")

    current = SettlementStatus(row["settlement_status"])
    if SettlementStatus.RECONCILED not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(400,
            f"Invalid transition: {current.value} -> RECONCILED. "
            f"Valid next states: {[s.value for s in VALID_TRANSITIONS.get(current, [])]}"
        )

    now = _now()
    new_hash = _hash_settlement({
        "settlement_id": settlement_id,
        "status": "RECONCILED",
        "reconciled_at": now,
    })

    db.execute("""
        UPDATE settlement_events
        SET settlement_status=?, audit_hash=?, version=version+1, updated_at=?
        WHERE settlement_id=?
    """, (SettlementStatus.RECONCILED.value, new_hash, now, settlement_id))

    _log_event(db, settlement_id, row["project_id"], "settlement.reconciled",
               changed_by, field="settlement_status",
               old_val=current.value, new_val=SettlementStatus.RECONCILED.value)
    db.commit()

    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{settlement_id}/dispute", response_model=SettlementResponse)
def dispute_settlement(
    settlement_id: str,
    reason: str = Query(..., min_length=10, description="Dispute reason"),
    changed_by: str = Query(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Mark settlement as DISPUTED. Only valid from PENDING.
    Fires event: settlement.disputed
    """
    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement {settlement_id} not found")

    current = SettlementStatus(row["settlement_status"])
    if SettlementStatus.DISPUTED not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(400,
            f"Invalid transition: {current.value} -> DISPUTED. "
            f"Valid next states: {[s.value for s in VALID_TRANSITIONS.get(current, [])]}"
        )

    now = _now()
    new_hash = _hash_settlement({
        "settlement_id": settlement_id,
        "status": "DISPUTED",
        "reason": reason,
        "disputed_at": now,
    })

    db.execute("""
        UPDATE settlement_events
        SET settlement_status=?, audit_hash=?, version=version+1, updated_at=?
        WHERE settlement_id=?
    """, (SettlementStatus.DISPUTED.value, new_hash, now, settlement_id))

    _log_event(db, settlement_id, row["project_id"], "settlement.disputed",
               changed_by, field="settlement_status",
               old_val=current.value, new_val=SettlementStatus.DISPUTED.value,
               justification=reason)
    db.commit()

    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{settlement_id}/link-matrix", response_model=SettlementResponse)
def link_matrix_thread(
    settlement_id: str,
    matrix_thread_id: str = Query(..., description="Element-Matrix room/thread ID"),
    changed_by: str = Query(...),
    db: sqlite3.Connection = Depends(get_db),
):
    """Link a settlement event to an Element-Matrix communication thread."""
    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement {settlement_id} not found")

    now = _now()
    db.execute(
        "UPDATE settlement_events SET matrix_thread_id=?, updated_at=? WHERE settlement_id=?",
        (matrix_thread_id, now, settlement_id),
    )
    _log_event(db, settlement_id, row["project_id"], "settlement.matrix_linked",
               changed_by, field="matrix_thread_id", new_val=matrix_thread_id)
    db.commit()

    row = db.execute("SELECT * FROM settlement_events WHERE settlement_id=?", (settlement_id,)).fetchone()
    return _row_to_response(row)


@router.get("/project/{project_id}/summary", response_model=SettlementProjectSummary)
def project_settlement_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Aggregate settlement view for a project.
    Total settled volume/amount, breakdown by status, by counterparty.
    """
    rows = db.execute(
        "SELECT * FROM settlement_events WHERE project_id=?", (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No settlements found for project {project_id}")

    total_volume = sum(r["volume_kg"] for r in rows)
    total_amount = sum(r["total_amount"] for r in rows)

    by_status: dict = {}
    for r in rows:
        by_status[r["settlement_status"]] = by_status.get(r["settlement_status"], 0) + 1

    by_buyer: dict = {}
    for r in rows:
        by_buyer[r["counterparty_buyer_id"]] = by_buyer.get(r["counterparty_buyer_id"], 0) + r["total_amount"]

    by_seller: dict = {}
    for r in rows:
        by_seller[r["counterparty_seller_id"]] = by_seller.get(r["counterparty_seller_id"], 0) + r["total_amount"]

    return SettlementProjectSummary(
        project_id=project_id,
        total_settlements=len(rows),
        total_settled_volume_kg=total_volume,
        total_settled_amount=total_amount,
        by_status=by_status,
        by_counterparty_buyer=by_buyer,
        by_counterparty_seller=by_seller,
    )
