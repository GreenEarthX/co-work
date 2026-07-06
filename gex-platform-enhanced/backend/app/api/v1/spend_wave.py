"""
spend_wave.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

SPEND_WAVE entity — pre-FID annual time-phased spend by capital layer.
Every drawdown of development capital is logged here before FID, broken
down by year and capital layer. The equity-first-loss invariant ensures
that senior / ECA / DFI tranches are never drawn before FID — only equity,
grants, and bridge can absorb pre-FID risk.

Design principles (from GEX Bridge Document v3.0):
  - Equity absorbs first loss: senior/DFI capital cannot be deployed pre-FID
  - Every spend line ties to a development_packages record (package_id FK)
  - Annual phasing feeds cash-flow waterfall projections
  - Pre-FID spend is a de-risking exercise, not a construction draw

Integration points:
  - FK to development_packages.package_id (development_packages.py)
  - FK to capital tranches via tranche_id (capital_bridge.py)
  - Feeds pre-COD metrics engine (pre_cod_metrics.py)
  - Feeds waterfall model (gex_pf_engine/waterfall.py)

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

router = APIRouter(prefix="/api/v1/spend-wave", tags=["spend-wave"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class CapitalLayer(str, Enum):
    EQUITY_SEED    = "EQUITY_SEED"
    EQUITY_SPONSOR = "EQUITY_SPONSOR"
    GRANT          = "GRANT"
    BRIDGE         = "BRIDGE"
    DFI_EIB        = "DFI_EIB"
    DFI_KFW        = "DFI_KFW"
    DFI_IFC        = "DFI_IFC"
    DFI_BPI        = "DFI_BPI"
    DFI_DFC        = "DFI_DFC"
    DFI_AFDB       = "DFI_AFDB"
    SENIOR         = "SENIOR"
    ECA            = "ECA"


class PhaseAtDrawdown(str, Enum):
    FEL_1 = "FEL_1"
    FEL_2 = "FEL_2"
    FEED  = "FEED"
    FID   = "FID"


# Capital layers that are NOT permitted before FID
POST_FID_ONLY_LAYERS = {
    CapitalLayer.SENIOR,
    CapitalLayer.ECA,
    CapitalLayer.DFI_EIB,
    CapitalLayer.DFI_KFW,
    CapitalLayer.DFI_IFC,
    CapitalLayer.DFI_BPI,
    CapitalLayer.DFI_DFC,
    CapitalLayer.DFI_AFDB,
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SpendWaveCreate(BaseModel):
    project_id:        str
    package_id:        str = Field(..., description="FK to development_packages")
    year:              int = Field(..., ge=2020, le=2050)
    amount_drawn:      float = Field(..., gt=0, description="Amount in EUR")
    capital_layer:     CapitalLayer
    tranche_id:        Optional[str] = Field(None, description="FK to capital tranches")
    phase_at_drawdown: PhaseAtDrawdown
    fid_year:          int = Field(..., description="FID year for equity-first-loss invariant check")


class SpendWaveUpdate(BaseModel):
    amount_drawn:      Optional[float] = Field(None, gt=0)
    capital_layer:     Optional[CapitalLayer] = None
    tranche_id:        Optional[str] = None
    phase_at_drawdown: Optional[PhaseAtDrawdown] = None
    fid_year:          Optional[int] = None
    changed_by:        str = Field(..., description="Actor ID making the change")


class SpendWaveResponse(BaseModel):
    spend_wave_id:     str
    project_id:        str
    package_id:        str
    year:              int
    amount_drawn:      float
    capital_layer:     str
    tranche_id:        Optional[str]
    phase_at_drawdown: str
    fid_year:          int
    equity_first_loss: bool
    version:           int
    created_at:        str
    updated_at:        str


class SpendWaveSummary(BaseModel):
    project_id:                str
    total_spend:               float
    total_pre_fid_spend:       float
    by_year:                   dict   # year → total amount
    by_capital_layer:          dict   # capital_layer → total amount
    by_year_and_layer:         dict   # year → { capital_layer → amount }
    equity_first_loss_compliant: bool  # True if no post-FID-only layers drawn pre-FID
    violations:                list[str]


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

def get_db():
    # check_same_thread=False: FastAPI runs sync endpoints across threadpool
    # workers; a request's dependency and endpoint can land on different
    # threads. Connection stays per-request, not shared concurrently.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Create spend_waves table + spend_wave_events audit table.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spend_waves (
            spend_wave_id      TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            package_id         TEXT NOT NULL,
            year               INTEGER NOT NULL,
            amount_drawn       REAL NOT NULL,
            capital_layer      TEXT NOT NULL,
            tranche_id         TEXT,
            phase_at_drawdown  TEXT NOT NULL,
            fid_year           INTEGER NOT NULL,
            equity_first_loss  INTEGER NOT NULL DEFAULT 0,
            version            INTEGER NOT NULL DEFAULT 1,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_project ON spend_waves(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_year ON spend_waves(year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_layer ON spend_waves(capital_layer)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_package ON spend_waves(package_id)")

    # Audit table — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spend_wave_events (
            event_id       TEXT PRIMARY KEY,
            spend_wave_id  TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swe_spend_wave ON spend_wave_events(spend_wave_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(conn, spend_wave_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM spend_wave_events "
        "WHERE spend_wave_id=? ORDER BY created_at DESC LIMIT 1",
        (spend_wave_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "spend_wave_id": spend_wave_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO spend_wave_events
        (event_id, spend_wave_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), spend_wave_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _enforce_equity_first_loss(capital_layer: CapitalLayer, year: int, fid_year: int):
    """
    CRITICAL SYSTEM INVARIANT — equity-first-loss rule.
    Senior, ECA, and DFI tranches cannot be drawn before FID year.
    Equity absorbs first loss; senior lenders do not take development risk.
    """
    if capital_layer in POST_FID_ONLY_LAYERS and year < fid_year:
        raise HTTPException(400,
            f"Equity-first-loss violation: {capital_layer.value} cannot be drawn "
            f"in year {year} (before FID year {fid_year}). "
            f"Only EQUITY_SEED, EQUITY_SPONSOR, GRANT, and BRIDGE are permitted "
            f"pre-FID. Senior, ECA, and DFI tranches require FID to have passed."
        )


def _compute_equity_first_loss(year: int, fid_year: int) -> bool:
    """equity_first_loss = True if year <= fid_year - 1"""
    return year <= fid_year - 1


def _row_to_response(row) -> dict:
    return {
        "spend_wave_id":     row["spend_wave_id"],
        "project_id":        row["project_id"],
        "package_id":        row["package_id"],
        "year":              row["year"],
        "amount_drawn":      row["amount_drawn"],
        "capital_layer":     row["capital_layer"],
        "tranche_id":        row["tranche_id"],
        "phase_at_drawdown": row["phase_at_drawdown"],
        "fid_year":          row["fid_year"],
        "equity_first_loss": bool(row["equity_first_loss"]),
        "version":           row["version"],
        "created_at":        row["created_at"],
        "updated_at":        row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=SpendWaveResponse, status_code=201)
def create_spend_wave(sw: SpendWaveCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a spend wave record — pre-FID annual time-phased spend.
    Enforces equity-first-loss invariant: senior/ECA/DFI cannot be drawn pre-FID.
    """
    # Enforce equity-first-loss invariant
    _enforce_equity_first_loss(sw.capital_layer, sw.year, sw.fid_year)

    spend_wave_id = str(uuid.uuid4())
    now = _now()
    equity_first_loss = _compute_equity_first_loss(sw.year, sw.fid_year)

    db.execute("""
        INSERT INTO spend_waves
        (spend_wave_id, project_id, package_id, year, amount_drawn,
         capital_layer, tranche_id, phase_at_drawdown, fid_year,
         equity_first_loss, version, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        spend_wave_id, sw.project_id, sw.package_id, sw.year,
        sw.amount_drawn, sw.capital_layer.value, sw.tranche_id,
        sw.phase_at_drawdown.value, sw.fid_year,
        1 if equity_first_loss else 0,
        1, now, now
    ))
    _log_event(db, spend_wave_id, sw.project_id, "spend_wave.created",
               sw.project_id, new_val=f"{sw.capital_layer.value} {sw.year} {sw.amount_drawn}")
    db.commit()

    row = db.execute("SELECT * FROM spend_waves WHERE spend_wave_id=?", (spend_wave_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{spend_wave_id}", response_model=SpendWaveResponse)
def get_spend_wave(spend_wave_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM spend_waves WHERE spend_wave_id=?", (spend_wave_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Spend wave {spend_wave_id} not found")
    return _row_to_response(row)


@router.get("/project/{project_id}", response_model=list[SpendWaveResponse])
def list_spend_waves(
    project_id: str,
    year: Optional[int] = Query(None),
    capital_layer: Optional[CapitalLayer] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """List all spend wave records for a project with optional year/capital_layer filters."""
    query = "SELECT * FROM spend_waves WHERE project_id=?"
    params: list = [project_id]

    if year is not None:
        query += " AND year=?"
        params.append(year)
    if capital_layer is not None:
        query += " AND capital_layer=?"
        params.append(capital_layer.value)

    query += " ORDER BY year ASC, capital_layer ASC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/project/{project_id}/summary", response_model=SpendWaveSummary)
def spend_wave_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Aggregate spend wave view:
      - Total spend by year, by capital layer, and cross-tabulated
      - Total pre-FID spend
      - Equity-first-loss compliance check with violation details
    """
    rows = db.execute(
        "SELECT * FROM spend_waves WHERE project_id=? ORDER BY year ASC",
        (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No spend wave records found for project {project_id}")

    total_spend = sum(r["amount_drawn"] for r in rows)

    by_year: dict = {}
    for r in rows:
        y = str(r["year"])
        by_year[y] = by_year.get(y, 0) + r["amount_drawn"]

    by_layer: dict = {}
    for r in rows:
        by_layer[r["capital_layer"]] = by_layer.get(r["capital_layer"], 0) + r["amount_drawn"]

    by_year_and_layer: dict = {}
    for r in rows:
        y = str(r["year"])
        if y not in by_year_and_layer:
            by_year_and_layer[y] = {}
        by_year_and_layer[y][r["capital_layer"]] = (
            by_year_and_layer[y].get(r["capital_layer"], 0) + r["amount_drawn"]
        )

    # Pre-FID spend: rows where equity_first_loss is true (year <= fid_year - 1)
    total_pre_fid = sum(r["amount_drawn"] for r in rows if r["equity_first_loss"])

    # Compliance check — scan for any post-FID-only layers drawn pre-FID
    violations = []
    for r in rows:
        if r["capital_layer"] in {l.value for l in POST_FID_ONLY_LAYERS} and r["year"] < r["fid_year"]:
            violations.append(
                f"{r['capital_layer']} drawn in {r['year']} before FID year {r['fid_year']} "
                f"(spend_wave_id={r['spend_wave_id']})"
            )

    return SpendWaveSummary(
        project_id=project_id,
        total_spend=total_spend,
        total_pre_fid_spend=total_pre_fid,
        by_year=by_year,
        by_capital_layer=by_layer,
        by_year_and_layer=by_year_and_layer,
        equity_first_loss_compliant=len(violations) == 0,
        violations=violations,
    )


@router.delete("/{spend_wave_id}")
def delete_spend_wave(spend_wave_id: str, deleted_by: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Soft delete via event log — marks the record as deleted in the audit trail.
    The row remains for audit purposes; hard deletes are never permitted.
    """
    row = db.execute("SELECT * FROM spend_waves WHERE spend_wave_id=?", (spend_wave_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Spend wave {spend_wave_id} not found")

    now = _now()
    _log_event(db, spend_wave_id, row["project_id"], "spend_wave.deleted",
               deleted_by, field="status",
               old_val="active", new_val="deleted",
               justification="Administrative deletion")
    db.execute("DELETE FROM spend_waves WHERE spend_wave_id=?", (spend_wave_id,))
    db.commit()
    return {"status": "deleted", "spend_wave_id": spend_wave_id}
