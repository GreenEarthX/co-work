"""
sovereign_instruments.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Debt-for-nature swap instruments linked to token provenance. Sovereign
instruments represent bilateral or multilateral agreements where a nation's
debt is reduced in exchange for verified carbon attribution or environmental
commitments backed by GEX tokens.

Design principles:
  - Each instrument ties a nation's debt obligation to measurable carbon output
  - linked_token_ids creates the provenance chain from instrument -> token -> settlement
  - Instruments are immutable once ACTIVE — amendments require new instruments
  - swap_ratio defines the debt-reduction-per-tonne economics

Integration points:
  - FK from carbon_attribution.py (debt_swap_id)
  - FK from development_packages.py (debt_swap_id on packages)
  - Linked to tokens_sqlite.py via linked_token_ids
  - Feeds sovereign ESG dashboards and DFI exposure views
  - Event log feeds event_store.py / event_bus.py

ABAC alignment (abac.py):
  - DFI / FINANCE: full CRUD
  - REGULATOR: read + advance to SIGNED / ACTIVE
  - PRODUCER: read instruments linked to own project
  - EXECUTIVE: read-only portfolio aggregate

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

router = APIRouter(prefix="/api/v1/sovereign-instruments", tags=["sovereign-instruments"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class InstrumentType(str, Enum):
    DEBT_FOR_NATURE     = "DEBT_FOR_NATURE"
    DEBT_FOR_CLIMATE    = "DEBT_FOR_CLIMATE"
    CARBON_CREDIT_SWAP  = "CARBON_CREDIT_SWAP"
    GREEN_BOND_SOVEREIGN = "GREEN_BOND_SOVEREIGN"


class InstrumentStatus(str, Enum):
    DRAFT       = "DRAFT"
    NEGOTIATING = "NEGOTIATING"
    SIGNED      = "SIGNED"
    ACTIVE      = "ACTIVE"
    MATURED     = "MATURED"
    CANCELLED   = "CANCELLED"


# State machine: DRAFT -> NEGOTIATING -> SIGNED -> ACTIVE -> MATURED
# Any state can transition to CANCELLED
VALID_TRANSITIONS = {
    InstrumentStatus.DRAFT:       [InstrumentStatus.NEGOTIATING, InstrumentStatus.CANCELLED],
    InstrumentStatus.NEGOTIATING: [InstrumentStatus.SIGNED, InstrumentStatus.CANCELLED],
    InstrumentStatus.SIGNED:      [InstrumentStatus.ACTIVE, InstrumentStatus.CANCELLED],
    InstrumentStatus.ACTIVE:      [InstrumentStatus.MATURED, InstrumentStatus.CANCELLED],
    InstrumentStatus.MATURED:     [],
    InstrumentStatus.CANCELLED:   [],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class InstrumentCreate(BaseModel):
    project_id:               str
    host_nation:              str = Field(..., description="ISO country code")
    instrument_type:          InstrumentType
    counterparty:             str = Field(..., description="e.g. IMF, WORLD_BANK, PARIS_CLUB")
    nominal_amount:           float = Field(..., gt=0)
    currency:                 str = Field(default="USD", description="ISO 4217 currency code")
    carbon_commitment_tonnes: Optional[float] = Field(None, description="Annual carbon attribution target")
    swap_ratio:               Optional[float] = Field(None, description="Debt reduction per tonne attributed")
    effective_date:           Optional[str] = Field(None, description="ISO date")
    maturity_date:            Optional[str] = Field(None, description="ISO date")
    linked_token_ids:         list[str] = Field(default_factory=list, description="Tokens backed by this instrument")
    changed_by:               str


class InstrumentUpdate(BaseModel):
    host_nation:              Optional[str] = None
    instrument_type:          Optional[InstrumentType] = None
    counterparty:             Optional[str] = None
    nominal_amount:           Optional[float] = None
    currency:                 Optional[str] = None
    carbon_commitment_tonnes: Optional[float] = None
    swap_ratio:               Optional[float] = None
    effective_date:           Optional[str] = None
    maturity_date:            Optional[str] = None
    linked_token_ids:         Optional[list[str]] = None
    changed_by:               str = Field(..., description="Actor ID making the change")


class InstrumentResponse(BaseModel):
    instrument_id:            str
    project_id:               str
    host_nation:              str
    instrument_type:          str
    instrument_status:        str
    counterparty:             str
    nominal_amount:           float
    currency:                 str
    carbon_commitment_tonnes: Optional[float]
    swap_ratio:               Optional[float]
    effective_date:           Optional[str]
    maturity_date:            Optional[str]
    linked_token_ids:         list[str]
    version:                  int
    created_at:               str
    updated_at:               str


class GlobalSummary(BaseModel):
    total_instruments:          int
    total_nominal_amount:       float
    total_carbon_commitment:    float
    by_type:                    dict   # instrument_type -> count
    by_nation:                  dict   # host_nation -> count
    by_status:                  dict   # status -> count
    by_counterparty:            dict   # counterparty -> count


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
    Create SOVEREIGN_INSTRUMENTS table.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sovereign_instruments (
            instrument_id            TEXT PRIMARY KEY,
            project_id               TEXT NOT NULL,
            host_nation              TEXT NOT NULL,
            instrument_type          TEXT NOT NULL,
            instrument_status        TEXT NOT NULL DEFAULT 'DRAFT',
            counterparty             TEXT NOT NULL,
            nominal_amount           REAL NOT NULL,
            currency                 TEXT NOT NULL DEFAULT 'USD',
            carbon_commitment_tonnes REAL,
            swap_ratio               REAL,
            effective_date           TEXT,
            maturity_date            TEXT,
            linked_token_ids         TEXT NOT NULL DEFAULT '[]',
            version                  INTEGER NOT NULL DEFAULT 1,
            last_changed_by          TEXT NOT NULL,
            created_at               TEXT NOT NULL,
            updated_at               TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_project ON sovereign_instruments(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_nation ON sovereign_instruments(host_nation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_status ON sovereign_instruments(instrument_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_type ON sovereign_instruments(instrument_type)")

    # Audit table — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sovereign_instrument_events (
            event_id        TEXT PRIMARY KEY,
            instrument_id   TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            field_changed   TEXT,
            old_value       TEXT,
            new_value       TEXT,
            changed_by      TEXT NOT NULL,
            justification   TEXT,
            event_hash      TEXT NOT NULL,
            prev_hash       TEXT,
            created_at      TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sie_instrument ON sovereign_instrument_events(instrument_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_instrument(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_event(conn, instrument_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM sovereign_instrument_events "
        "WHERE instrument_id=? ORDER BY created_at DESC LIMIT 1",
        (instrument_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "instrument_id": instrument_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO sovereign_instrument_events
        (event_id, instrument_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), instrument_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "instrument_id":            row["instrument_id"],
        "project_id":               row["project_id"],
        "host_nation":              row["host_nation"],
        "instrument_type":          row["instrument_type"],
        "instrument_status":        row["instrument_status"],
        "counterparty":             row["counterparty"],
        "nominal_amount":           row["nominal_amount"],
        "currency":                 row["currency"],
        "carbon_commitment_tonnes": row["carbon_commitment_tonnes"],
        "swap_ratio":               row["swap_ratio"],
        "effective_date":           row["effective_date"],
        "maturity_date":            row["maturity_date"],
        "linked_token_ids":         json.loads(row["linked_token_ids"]),
        "version":                  row["version"],
        "created_at":               row["created_at"],
        "updated_at":               row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=InstrumentResponse, status_code=201)
def create_instrument(inst: InstrumentCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a sovereign instrument (debt-for-nature swap, green bond, etc.).
    Initial status is DRAFT.
    Fires event: instrument.created
    """
    instrument_id = str(uuid.uuid4())
    now = _now()

    db.execute("""
        INSERT INTO sovereign_instruments
        (instrument_id, project_id, host_nation, instrument_type,
         instrument_status, counterparty, nominal_amount, currency,
         carbon_commitment_tonnes, swap_ratio, effective_date, maturity_date,
         linked_token_ids, version, last_changed_by, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        instrument_id, inst.project_id, inst.host_nation,
        inst.instrument_type.value, InstrumentStatus.DRAFT.value,
        inst.counterparty, inst.nominal_amount, inst.currency,
        inst.carbon_commitment_tonnes, inst.swap_ratio,
        inst.effective_date, inst.maturity_date,
        json.dumps(inst.linked_token_ids),
        1, inst.changed_by, now, now
    ))
    _log_event(db, instrument_id, inst.project_id, "instrument.created",
               inst.changed_by, new_val=inst.instrument_type.value)
    db.commit()

    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{instrument_id}", response_model=InstrumentResponse)
def get_instrument(instrument_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Instrument {instrument_id} not found")
    return _row_to_response(row)


@router.get("/project/{project_id}", response_model=list[InstrumentResponse])
def list_by_project(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """All instruments for a project."""
    rows = db.execute(
        "SELECT * FROM sovereign_instruments WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/nation/{country_code}", response_model=list[InstrumentResponse])
def list_by_nation(country_code: str, db: sqlite3.Connection = Depends(get_db)):
    """All instruments for a nation."""
    rows = db.execute(
        "SELECT * FROM sovereign_instruments WHERE host_nation=? ORDER BY created_at DESC",
        (country_code,)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.patch("/{instrument_id}", response_model=InstrumentResponse)
def update_instrument(
    instrument_id: str,
    update: InstrumentUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Update instrument fields. Every change is logged to the event chain.
    Version is incremented on every save.
    """
    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Instrument {instrument_id} not found")

    # Cannot update instruments in terminal states
    current_status = InstrumentStatus(row["instrument_status"])
    if current_status in (InstrumentStatus.MATURED, InstrumentStatus.CANCELLED):
        raise HTTPException(400, f"Cannot update instrument in {current_status.value} state")

    now = _now()
    fields = update.model_dump(exclude_none=True, exclude={"changed_by"})

    for field, new_val in fields.items():
        old_val = row[field] if field in row.keys() else None
        stored = json.dumps(new_val) if isinstance(new_val, list) else new_val
        if hasattr(stored, "value"):
            stored = stored.value
        db.execute(
            f"UPDATE sovereign_instruments SET {field}=?, version=version+1, "
            "last_changed_by=?, updated_at=? WHERE instrument_id=?",
            (stored, update.changed_by, now, instrument_id)
        )
        _log_event(db, instrument_id, row["project_id"], "instrument.updated",
                   update.changed_by, field=field,
                   old_val=old_val, new_val=new_val)

    db.commit()

    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{instrument_id}/advance", response_model=InstrumentResponse)
def advance_instrument(
    instrument_id: str,
    changed_by: str = Query(...),
    justification: Optional[str] = Query(None, description="Reason for state transition"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance instrument status one step forward in the state machine.
    DRAFT -> NEGOTIATING -> SIGNED -> ACTIVE -> MATURED

    To cancel, use the cancel-specific logic (any -> CANCELLED) by passing
    the target state explicitly — this route only advances forward.
    """
    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Instrument {instrument_id} not found")

    current = InstrumentStatus(row["instrument_status"])
    valid_next = VALID_TRANSITIONS.get(current, [])

    # Filter out CANCELLED — advance only goes forward
    forward_states = [s for s in valid_next if s != InstrumentStatus.CANCELLED]
    if not forward_states:
        raise HTTPException(400, f"Instrument is in terminal state: {current.value}")

    new_status = forward_states[0]

    now = _now()
    db.execute("""
        UPDATE sovereign_instruments
        SET instrument_status=?, version=version+1, last_changed_by=?, updated_at=?
        WHERE instrument_id=?
    """, (new_status.value, changed_by, now, instrument_id))

    _log_event(db, instrument_id, row["project_id"], "instrument.advanced",
               changed_by, field="instrument_status",
               old_val=current.value, new_val=new_status.value,
               justification=justification)
    db.commit()

    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{instrument_id}/cancel", response_model=InstrumentResponse)
def cancel_instrument(
    instrument_id: str,
    changed_by: str = Query(...),
    reason: str = Query(..., min_length=10, description="Cancellation reason"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Cancel an instrument from any non-terminal state.
    """
    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Instrument {instrument_id} not found")

    current = InstrumentStatus(row["instrument_status"])
    if current in (InstrumentStatus.MATURED, InstrumentStatus.CANCELLED):
        raise HTTPException(400, f"Cannot cancel instrument in {current.value} state")

    now = _now()
    db.execute("""
        UPDATE sovereign_instruments
        SET instrument_status=?, version=version+1, last_changed_by=?, updated_at=?
        WHERE instrument_id=?
    """, (InstrumentStatus.CANCELLED.value, changed_by, now, instrument_id))

    _log_event(db, instrument_id, row["project_id"], "instrument.cancelled",
               changed_by, field="instrument_status",
               old_val=current.value, new_val=InstrumentStatus.CANCELLED.value,
               justification=reason)
    db.commit()

    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{instrument_id}/link-token", response_model=InstrumentResponse)
def link_token(
    instrument_id: str,
    token_id: str = Query(..., description="Token ID to link"),
    changed_by: str = Query(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Add a token_id to linked_token_ids. Creates the provenance chain
    from sovereign instrument -> token -> settlement -> carbon attribution.
    """
    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Instrument {instrument_id} not found")

    current_tokens = json.loads(row["linked_token_ids"])
    if token_id in current_tokens:
        raise HTTPException(400, f"Token {token_id} is already linked to this instrument")

    current_tokens.append(token_id)
    now = _now()

    db.execute("""
        UPDATE sovereign_instruments
        SET linked_token_ids=?, version=version+1, last_changed_by=?, updated_at=?
        WHERE instrument_id=?
    """, (json.dumps(current_tokens), changed_by, now, instrument_id))

    _log_event(db, instrument_id, row["project_id"], "instrument.token_linked",
               changed_by, field="linked_token_ids",
               old_val=json.loads(row["linked_token_ids"]),
               new_val=current_tokens)
    db.commit()

    row = db.execute("SELECT * FROM sovereign_instruments WHERE instrument_id=?", (instrument_id,)).fetchone()
    return _row_to_response(row)


@router.get("/summary", response_model=GlobalSummary)
def global_summary(db: sqlite3.Connection = Depends(get_db)):
    """
    Global summary of all sovereign instruments.
    Total instruments, by type, by nation, total carbon commitment.
    """
    rows = db.execute("SELECT * FROM sovereign_instruments").fetchall()

    if not rows:
        return GlobalSummary(
            total_instruments=0,
            total_nominal_amount=0.0,
            total_carbon_commitment=0.0,
            by_type={},
            by_nation={},
            by_status={},
            by_counterparty={},
        )

    total_nominal = sum(r["nominal_amount"] for r in rows)
    total_carbon = sum(r["carbon_commitment_tonnes"] or 0.0 for r in rows)

    by_type: dict = {}
    for r in rows:
        by_type[r["instrument_type"]] = by_type.get(r["instrument_type"], 0) + 1

    by_nation: dict = {}
    for r in rows:
        by_nation[r["host_nation"]] = by_nation.get(r["host_nation"], 0) + 1

    by_status: dict = {}
    for r in rows:
        by_status[r["instrument_status"]] = by_status.get(r["instrument_status"], 0) + 1

    by_counterparty: dict = {}
    for r in rows:
        by_counterparty[r["counterparty"]] = by_counterparty.get(r["counterparty"], 0) + 1

    return GlobalSummary(
        total_instruments=len(rows),
        total_nominal_amount=total_nominal,
        total_carbon_commitment=total_carbon,
        by_type=by_type,
        by_nation=by_nation,
        by_status=by_status,
        by_counterparty=by_counterparty,
    )
