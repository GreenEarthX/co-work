"""
drawdown_schedule.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

DRAWDOWN_SCHEDULE entity — post-FID quarterly milestone-linked drawdowns.
Once a project passes FID, capital is released in tranches tied to
construction milestones, IE sign-offs, and conditions precedent.

Design principles (from GEX Bridge Document v3.0):
  - Every drawdown ties to a construction milestone or certification event
  - State machine: REQUESTED → APPROVED → DISBURSED → RECONCILED (forward only)
  - DISBURSED requires milestone evidence; RECONCILED requires IE sign-off
  - Conditions Precedent (CPs) must be satisfied before drawdown approval
  - FX rate captured at drawdown for multi-currency tranches

Integration points:
  - FK to capital tranches via tranche_id (capital_bridge.py)
  - milestone_evidence_ref links to evidence chain (audit.py)
  - ie_signoff_ref links to IE attestation records
  - Feeds waterfall model (gex_pf_engine/waterfall.py)
  - Feeds pre-COD metrics engine (pre_cod_metrics.py)

SQLite pattern: matches development_packages.py / tokens_sqlite.py conventions.
"""

import sqlite3
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/drawdown-schedule", tags=["drawdown-schedule"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class DrawdownStatus(str, Enum):
    REQUESTED  = "REQUESTED"
    APPROVED   = "APPROVED"
    DISBURSED  = "DISBURSED"
    RECONCILED = "RECONCILED"


class MilestoneTrigger(str, Enum):
    EPC_PROGRESS_25   = "EPC_PROGRESS_25"
    EPC_PROGRESS_50   = "EPC_PROGRESS_50"
    EPC_PROGRESS_75   = "EPC_PROGRESS_75"
    CERT_MILESTONE    = "CERT_MILESTONE"
    PERMIT_CONFIRM    = "PERMIT_CONFIRM"
    EQUIPMENT_AWARD   = "EQUIPMENT_AWARD"
    IE_SIGNOFF        = "IE_SIGNOFF"
    PERFORMANCE_TEST  = "PERFORMANCE_TEST"
    COD_ACHIEVED      = "COD_ACHIEVED"
    OTHER             = "OTHER"


# State machine: valid forward transitions only
VALID_STATUS_TRANSITIONS = {
    DrawdownStatus.REQUESTED:  [DrawdownStatus.APPROVED],
    DrawdownStatus.APPROVED:   [DrawdownStatus.DISBURSED],
    DrawdownStatus.DISBURSED:  [DrawdownStatus.RECONCILED],
    DrawdownStatus.RECONCILED: [],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class DrawdownCreate(BaseModel):
    project_id:             str
    tranche_id:             str = Field(..., description="FK to capital tranches")
    quarter:                str = Field(..., pattern=r"^\d{4}-Q[1-4]$", description="Format YYYY-Qn")
    amount:                 float = Field(..., gt=0, description="EUR equivalent")
    amount_native:          Optional[float] = Field(None, description="Amount in tranche currency")
    fx_rate_used:           Optional[float] = Field(None, description="FX rate if currency != EUR")
    milestone_trigger:      MilestoneTrigger
    milestone_evidence_ref: Optional[str] = Field(None, description="FK to evidence")
    ie_signoff_ref:         Optional[str] = Field(None, description="FK to IE attestation")
    cps_satisfied:          list[str] = Field(default_factory=list, description="Conditions Precedent IDs")
    changed_by:             str = Field(..., description="Actor ID making the change")


class DrawdownResponse(BaseModel):
    drawdown_id:            str
    project_id:             str
    tranche_id:             str
    quarter:                str
    amount:                 float
    amount_native:          Optional[float]
    fx_rate_used:           Optional[float]
    milestone_trigger:      str
    milestone_evidence_ref: Optional[str]
    ie_signoff_ref:         Optional[str]
    cps_satisfied:          list[str]
    drawdown_status:        str
    changed_by:             str
    version:                int
    created_at:             str
    updated_at:             str


class StatusAdvance(BaseModel):
    changed_by:             str = Field(..., description="Actor ID advancing the status")
    justification:          str = Field(..., min_length=10, description="Reason for status advance")
    milestone_evidence_ref: Optional[str] = Field(None, description="Required for DISBURSED")
    ie_signoff_ref:         Optional[str] = Field(None, description="Required for RECONCILED")


class DrawdownSummary(BaseModel):
    project_id:             str
    total_drawn:            float
    total_scheduled:        float
    by_tranche:             dict  # tranche_id → { drawn, scheduled, count }
    by_quarter:             dict  # quarter → { drawn, scheduled, count }
    by_status:              dict  # status → count
    by_milestone:           dict  # milestone_trigger → count


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
    Create drawdown_schedules table + drawdown_schedule_events audit table.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drawdown_schedules (
            drawdown_id            TEXT PRIMARY KEY,
            project_id             TEXT NOT NULL,
            tranche_id             TEXT NOT NULL,
            quarter                TEXT NOT NULL,
            amount                 REAL NOT NULL,
            amount_native          REAL,
            fx_rate_used           REAL,
            milestone_trigger      TEXT NOT NULL,
            milestone_evidence_ref TEXT,
            ie_signoff_ref         TEXT,
            cps_satisfied          TEXT NOT NULL DEFAULT '[]',
            drawdown_status        TEXT NOT NULL DEFAULT 'REQUESTED',
            changed_by             TEXT NOT NULL,
            version                INTEGER NOT NULL DEFAULT 1,
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_project ON drawdown_schedules(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_tranche ON drawdown_schedules(tranche_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_quarter ON drawdown_schedules(quarter)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_status ON drawdown_schedules(drawdown_status)")

    # Audit table — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drawdown_schedule_events (
            event_id       TEXT PRIMARY KEY,
            drawdown_id    TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dse_drawdown ON drawdown_schedule_events(drawdown_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(conn, drawdown_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM drawdown_schedule_events "
        "WHERE drawdown_id=? ORDER BY created_at DESC LIMIT 1",
        (drawdown_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "drawdown_id": drawdown_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO drawdown_schedule_events
        (event_id, drawdown_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), drawdown_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "drawdown_id":            row["drawdown_id"],
        "project_id":             row["project_id"],
        "tranche_id":             row["tranche_id"],
        "quarter":                row["quarter"],
        "amount":                 row["amount"],
        "amount_native":          row["amount_native"],
        "fx_rate_used":           row["fx_rate_used"],
        "milestone_trigger":      row["milestone_trigger"],
        "milestone_evidence_ref": row["milestone_evidence_ref"],
        "ie_signoff_ref":         row["ie_signoff_ref"],
        "cps_satisfied":          json.loads(row["cps_satisfied"]),
        "drawdown_status":        row["drawdown_status"],
        "changed_by":             row["changed_by"],
        "version":                row["version"],
        "created_at":             row["created_at"],
        "updated_at":             row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=DrawdownResponse, status_code=201)
def create_drawdown(dd: DrawdownCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a drawdown schedule record — post-FID quarterly milestone-linked drawdown.
    Initial status is REQUESTED.
    """
    drawdown_id = str(uuid.uuid4())
    now = _now()

    db.execute("""
        INSERT INTO drawdown_schedules
        (drawdown_id, project_id, tranche_id, quarter, amount,
         amount_native, fx_rate_used, milestone_trigger,
         milestone_evidence_ref, ie_signoff_ref, cps_satisfied,
         drawdown_status, changed_by, version, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        drawdown_id, dd.project_id, dd.tranche_id, dd.quarter,
        dd.amount, dd.amount_native, dd.fx_rate_used,
        dd.milestone_trigger.value,
        dd.milestone_evidence_ref, dd.ie_signoff_ref,
        json.dumps(dd.cps_satisfied),
        DrawdownStatus.REQUESTED.value,
        dd.changed_by, 1, now, now
    ))
    _log_event(db, drawdown_id, dd.project_id, "drawdown.created",
               dd.changed_by, new_val=f"{dd.tranche_id} {dd.quarter} {dd.amount}")
    db.commit()

    row = db.execute("SELECT * FROM drawdown_schedules WHERE drawdown_id=?", (drawdown_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{drawdown_id}", response_model=DrawdownResponse)
def get_drawdown(drawdown_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM drawdown_schedules WHERE drawdown_id=?", (drawdown_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Drawdown {drawdown_id} not found")
    return _row_to_response(row)


@router.get("/project/{project_id}", response_model=list[DrawdownResponse])
def list_drawdowns(
    project_id: str,
    tranche_id: Optional[str] = Query(None),
    status: Optional[DrawdownStatus] = Query(None),
    quarter: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """List all drawdown records for a project with optional filters."""
    query = "SELECT * FROM drawdown_schedules WHERE project_id=?"
    params: list = [project_id]

    if tranche_id is not None:
        query += " AND tranche_id=?"
        params.append(tranche_id)
    if status is not None:
        query += " AND drawdown_status=?"
        params.append(status.value)
    if quarter is not None:
        query += " AND quarter=?"
        params.append(quarter)

    query += " ORDER BY quarter ASC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.post("/{drawdown_id}/advance", response_model=DrawdownResponse)
def advance_drawdown_status(
    drawdown_id: str,
    advance: StatusAdvance,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance drawdown status through the state machine.
    REQUESTED → APPROVED → DISBURSED → RECONCILED (forward only).

    Guards:
      - DISBURSED requires milestone_evidence_ref to be set
      - RECONCILED requires ie_signoff_ref to be set
    """
    row = db.execute("SELECT * FROM drawdown_schedules WHERE drawdown_id=?", (drawdown_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Drawdown {drawdown_id} not found")

    current = DrawdownStatus(row["drawdown_status"])
    valid_next = VALID_STATUS_TRANSITIONS.get(current, [])

    if not valid_next:
        raise HTTPException(400,
            f"Drawdown {drawdown_id} is in terminal state {current.value}. "
            f"No further transitions are permitted."
        )

    # There is only one valid next state in each case
    new_status = valid_next[0]

    # State-specific guards
    if new_status == DrawdownStatus.DISBURSED:
        # Check milestone evidence — use provided ref or existing one on record
        evidence_ref = advance.milestone_evidence_ref or row["milestone_evidence_ref"]
        if not evidence_ref:
            raise HTTPException(400,
                "Cannot advance to DISBURSED: milestone_evidence_ref is required. "
                "Provide evidence of milestone completion before disbursement."
            )
        # Update the evidence ref if provided
        if advance.milestone_evidence_ref:
            db.execute(
                "UPDATE drawdown_schedules SET milestone_evidence_ref=? WHERE drawdown_id=?",
                (advance.milestone_evidence_ref, drawdown_id)
            )

    if new_status == DrawdownStatus.RECONCILED:
        # Check IE sign-off — use provided ref or existing one on record
        signoff_ref = advance.ie_signoff_ref or row["ie_signoff_ref"]
        if not signoff_ref:
            raise HTTPException(400,
                "Cannot advance to RECONCILED: ie_signoff_ref is required. "
                "Independent Engineer sign-off must be recorded before reconciliation."
            )
        # Update the IE signoff ref if provided
        if advance.ie_signoff_ref:
            db.execute(
                "UPDATE drawdown_schedules SET ie_signoff_ref=? WHERE drawdown_id=?",
                (advance.ie_signoff_ref, drawdown_id)
            )

    now = _now()
    db.execute("""
        UPDATE drawdown_schedules
        SET drawdown_status=?, version=version+1, changed_by=?, updated_at=?
        WHERE drawdown_id=?
    """, (new_status.value, advance.changed_by, now, drawdown_id))

    _log_event(
        db, drawdown_id, row["project_id"],
        "drawdown.status_advanced",
        advance.changed_by,
        field="drawdown_status",
        old_val=current.value,
        new_val=new_status.value,
        justification=advance.justification
    )
    db.commit()

    row = db.execute("SELECT * FROM drawdown_schedules WHERE drawdown_id=?", (drawdown_id,)).fetchone()
    return _row_to_response(row)


@router.get("/project/{project_id}/summary", response_model=DrawdownSummary)
def drawdown_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Aggregate drawdown view:
      - Total drawn (DISBURSED + RECONCILED) vs total scheduled (all records)
      - Breakdown by tranche, by quarter, by status, by milestone trigger
    """
    rows = db.execute(
        "SELECT * FROM drawdown_schedules WHERE project_id=? ORDER BY quarter ASC",
        (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No drawdown records found for project {project_id}")

    drawn_statuses = {DrawdownStatus.DISBURSED.value, DrawdownStatus.RECONCILED.value}
    total_scheduled = sum(r["amount"] for r in rows)
    total_drawn = sum(r["amount"] for r in rows if r["drawdown_status"] in drawn_statuses)

    by_tranche: dict = {}
    for r in rows:
        tid = r["tranche_id"]
        if tid not in by_tranche:
            by_tranche[tid] = {"drawn": 0.0, "scheduled": 0.0, "count": 0}
        by_tranche[tid]["scheduled"] += r["amount"]
        by_tranche[tid]["count"] += 1
        if r["drawdown_status"] in drawn_statuses:
            by_tranche[tid]["drawn"] += r["amount"]

    by_quarter: dict = {}
    for r in rows:
        q = r["quarter"]
        if q not in by_quarter:
            by_quarter[q] = {"drawn": 0.0, "scheduled": 0.0, "count": 0}
        by_quarter[q]["scheduled"] += r["amount"]
        by_quarter[q]["count"] += 1
        if r["drawdown_status"] in drawn_statuses:
            by_quarter[q]["drawn"] += r["amount"]

    by_status: dict = {}
    for r in rows:
        by_status[r["drawdown_status"]] = by_status.get(r["drawdown_status"], 0) + 1

    by_milestone: dict = {}
    for r in rows:
        by_milestone[r["milestone_trigger"]] = by_milestone.get(r["milestone_trigger"], 0) + 1

    return DrawdownSummary(
        project_id=project_id,
        total_drawn=total_drawn,
        total_scheduled=total_scheduled,
        by_tranche=by_tranche,
        by_quarter=by_quarter,
        by_status=by_status,
        by_milestone=by_milestone,
    )
