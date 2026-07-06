"""
mass_balance.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Mass-balance lot ledger. Every tokenised molecule traces back to a
production lot. This module prevents double-counting by tracking volume
allocated from each lot and rejecting allocations that would exceed
the lot's total production.

Tokens reference lots via their mass_balance_lot_id field (tokens_sqlite.py).

Design principles:
  - Lot created when production batch is confirmed
  - Tokens allocate volume from the lot (deduct remaining)
  - Allocation rejected if remaining < requested (exhaustion guard)
  - Append-only allocation log for audit trail

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

router = APIRouter(prefix="/api/v1/mass-balance", tags=["mass-balance"])


class LotStatus(str, Enum):
    OPEN       = "OPEN"
    EXHAUSTED  = "EXHAUSTED"
    VOIDED     = "VOIDED"


class LotCreate(BaseModel):
    project_id: str
    molecule: str = Field(..., description="H2, NH3, E_METHANOL, SAF, E_DIESEL")
    production_date: str = Field(..., description="ISO date of production batch")
    total_volume_kg: float = Field(..., gt=0)
    certification_pathway: Optional[str] = None
    carbon_intensity_gco2e_mj: Optional[float] = None
    created_by: str


class LotResponse(BaseModel):
    lot_id: str
    project_id: str
    molecule: str
    production_date: str
    total_volume_kg: float
    allocated_volume_kg: float
    remaining_volume_kg: float
    status: str
    certification_pathway: Optional[str]
    carbon_intensity_gco2e_mj: Optional[float]
    audit_hash: str
    created_at: str
    updated_at: str


class AllocationCreate(BaseModel):
    lot_id: str
    token_id: str
    volume_kg: float = Field(..., gt=0)
    allocated_by: str


class AllocationResponse(BaseModel):
    allocation_id: str
    lot_id: str
    token_id: str
    volume_kg: float
    allocated_by: str
    allocation_hash: str
    prev_hash: Optional[str]
    created_at: str


class LotSummary(BaseModel):
    project_id: str
    total_lots: int
    total_production_kg: float
    total_allocated_kg: float
    total_remaining_kg: float
    by_status: dict
    by_molecule: dict


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
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mass_balance_lots (
            lot_id                    TEXT PRIMARY KEY,
            project_id                TEXT NOT NULL,
            molecule                  TEXT NOT NULL,
            production_date           TEXT NOT NULL,
            total_volume_kg           REAL NOT NULL,
            allocated_volume_kg       REAL NOT NULL DEFAULT 0,
            remaining_volume_kg       REAL NOT NULL,
            status                    TEXT NOT NULL DEFAULT 'OPEN',
            certification_pathway     TEXT,
            carbon_intensity_gco2e_mj REAL,
            audit_hash                TEXT NOT NULL,
            created_by                TEXT NOT NULL,
            created_at                TEXT NOT NULL,
            updated_at                TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mbl_project ON mass_balance_lots(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mbl_status ON mass_balance_lots(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mbl_molecule ON mass_balance_lots(molecule)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mass_balance_allocations (
            allocation_id  TEXT PRIMARY KEY,
            lot_id         TEXT NOT NULL,
            token_id       TEXT NOT NULL,
            volume_kg      REAL NOT NULL,
            allocated_by   TEXT NOT NULL,
            allocation_hash TEXT NOT NULL,
            prev_hash      TEXT,
            created_at     TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mba_lot ON mass_balance_allocations(lot_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mba_token ON mass_balance_allocations(token_id)")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _lot_row(row) -> dict:
    return {
        "lot_id": row["lot_id"],
        "project_id": row["project_id"],
        "molecule": row["molecule"],
        "production_date": row["production_date"],
        "total_volume_kg": row["total_volume_kg"],
        "allocated_volume_kg": row["allocated_volume_kg"],
        "remaining_volume_kg": row["remaining_volume_kg"],
        "status": row["status"],
        "certification_pathway": row["certification_pathway"],
        "carbon_intensity_gco2e_mj": row["carbon_intensity_gco2e_mj"],
        "audit_hash": row["audit_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("/lots", response_model=LotResponse, status_code=201)
def create_lot(lot: LotCreate, db: sqlite3.Connection = Depends(get_db)):
    lot_id = str(uuid.uuid4())
    now = _now()
    audit_hash = _hash({
        "lot_id": lot_id, "project_id": lot.project_id,
        "molecule": lot.molecule, "total_volume_kg": lot.total_volume_kg,
        "created_at": now,
    })

    db.execute("""
        INSERT INTO mass_balance_lots
        (lot_id, project_id, molecule, production_date, total_volume_kg,
         allocated_volume_kg, remaining_volume_kg, status,
         certification_pathway, carbon_intensity_gco2e_mj,
         audit_hash, created_by, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lot_id, lot.project_id, lot.molecule, lot.production_date,
        lot.total_volume_kg, 0.0, lot.total_volume_kg,
        LotStatus.OPEN.value, lot.certification_pathway,
        lot.carbon_intensity_gco2e_mj, audit_hash, lot.created_by, now, now,
    ))
    db.commit()

    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (lot_id,)).fetchone()
    return _lot_row(row)


@router.get("/lots/{lot_id}", response_model=LotResponse)
def get_lot(lot_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (lot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Lot {lot_id} not found")
    return _lot_row(row)


@router.get("/lots/project/{project_id}", response_model=list[LotResponse])
def list_lots_by_project(
    project_id: str,
    status: Optional[LotStatus] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
):
    query = "SELECT * FROM mass_balance_lots WHERE project_id=?"
    params: list = [project_id]
    if status:
        query += " AND status=?"
        params.append(status.value)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [_lot_row(r) for r in rows]


@router.post("/allocate", response_model=AllocationResponse, status_code=201)
def allocate_from_lot(alloc: AllocationCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Allocate volume from a lot to a token. Rejects if:
      - lot not found or not OPEN
      - requested volume > remaining volume (exhaustion guard)
    Auto-transitions lot to EXHAUSTED when remaining hits zero.
    """
    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (alloc.lot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Lot {alloc.lot_id} not found")

    if row["status"] != LotStatus.OPEN.value:
        raise HTTPException(400, f"Lot {alloc.lot_id} is {row['status']}, not OPEN")

    remaining = row["remaining_volume_kg"]
    if alloc.volume_kg > remaining:
        raise HTTPException(
            400,
            f"Exhaustion guard: requested {alloc.volume_kg} kg but only "
            f"{remaining} kg remaining in lot {alloc.lot_id}",
        )

    allocation_id = str(uuid.uuid4())
    now = _now()

    prev = db.execute(
        "SELECT allocation_hash FROM mass_balance_allocations "
        "WHERE lot_id=? ORDER BY created_at DESC LIMIT 1",
        (alloc.lot_id,),
    ).fetchone()
    prev_hash = prev["allocation_hash"] if prev else None

    allocation_hash = _hash({
        "allocation_id": allocation_id, "lot_id": alloc.lot_id,
        "token_id": alloc.token_id, "volume_kg": alloc.volume_kg,
        "prev_hash": prev_hash, "timestamp": now,
    })

    db.execute("""
        INSERT INTO mass_balance_allocations
        (allocation_id, lot_id, token_id, volume_kg, allocated_by,
         allocation_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        allocation_id, alloc.lot_id, alloc.token_id, alloc.volume_kg,
        alloc.allocated_by, allocation_hash, prev_hash, now,
    ))

    new_allocated = row["allocated_volume_kg"] + alloc.volume_kg
    new_remaining = row["total_volume_kg"] - new_allocated
    new_status = LotStatus.EXHAUSTED.value if new_remaining <= 0 else LotStatus.OPEN.value

    new_audit_hash = _hash({
        "lot_id": alloc.lot_id, "allocated": new_allocated,
        "remaining": new_remaining, "status": new_status, "timestamp": now,
    })

    db.execute("""
        UPDATE mass_balance_lots
        SET allocated_volume_kg=?, remaining_volume_kg=?, status=?,
            audit_hash=?, updated_at=?
        WHERE lot_id=?
    """, (new_allocated, new_remaining, new_status, new_audit_hash, now, alloc.lot_id))

    db.commit()

    return {
        "allocation_id": allocation_id,
        "lot_id": alloc.lot_id,
        "token_id": alloc.token_id,
        "volume_kg": alloc.volume_kg,
        "allocated_by": alloc.allocated_by,
        "allocation_hash": allocation_hash,
        "prev_hash": prev_hash,
        "created_at": now,
    }


@router.get("/lots/{lot_id}/allocations", response_model=list[AllocationResponse])
def list_allocations(lot_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM mass_balance_allocations WHERE lot_id=? ORDER BY created_at ASC",
        (lot_id,),
    ).fetchall()
    return [
        {
            "allocation_id": r["allocation_id"],
            "lot_id": r["lot_id"],
            "token_id": r["token_id"],
            "volume_kg": r["volume_kg"],
            "allocated_by": r["allocated_by"],
            "allocation_hash": r["allocation_hash"],
            "prev_hash": r["prev_hash"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/project/{project_id}/summary", response_model=LotSummary)
def lot_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM mass_balance_lots WHERE project_id=?", (project_id,)
    ).fetchall()
    if not rows:
        raise HTTPException(404, f"No lots found for project {project_id}")

    by_status: dict = {}
    by_molecule: dict = {}
    total_prod = 0.0
    total_alloc = 0.0
    total_remain = 0.0

    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_molecule[r["molecule"]] = by_molecule.get(r["molecule"], 0) + r["total_volume_kg"]
        total_prod += r["total_volume_kg"]
        total_alloc += r["allocated_volume_kg"]
        total_remain += r["remaining_volume_kg"]

    return LotSummary(
        project_id=project_id,
        total_lots=len(rows),
        total_production_kg=total_prod,
        total_allocated_kg=total_alloc,
        total_remaining_kg=total_remain,
        by_status=by_status,
        by_molecule=by_molecule,
    )
