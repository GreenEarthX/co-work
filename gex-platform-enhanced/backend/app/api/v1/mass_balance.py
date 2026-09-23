"""
mass_balance.py — Chain-of-Custody Ledger
=========================================
GEX Platform — backend/app/api/v1/

WHAT THIS IS, PRECISELY
-----------------------
A **chain-of-custody ledger**: it records certified production lots and
allocates volume from them to tokens, refusing any allocation that would
exceed what the lot declared. Its integrity guarantee is

    "you cannot allocate more than was declared"

and NOT

    "what was declared is true".

The product surface is called **Chain of Custody**, not "Mass Balance Ledger".
The file and tables keep the `mass_balance` name because *mass balance* is the
correct name for the chain-of-custody METHOD under RED III — see below. It is
the wrong name for a product, because it reads to an engineer as conservation
of mass and energy, which this module does not perform.

THREE DIFFERENT THINGS IN GEX ARE CALLED "MASS BALANCE"
------------------------------------------------------
They are not duplicates. They are different layers, and conflating them is how
a platform ends up claiming to verify plants it has never modelled.

  1. ENGINEERING / PROCESS BALANCE — frontend `src/engine/`
     Conservation residual r = Σṁ_in − Σṁ_out (F_MASS_BALANCE_RESIDUAL_V1),
     electrolysis stoichiometry (9 kg H2O and 8 kg O2 per kg H2), splitter and
     separator balances, recycle and purge loops, LHV and yield. 20 formulas,
     31 consistency checks, on the PlantBuilder canvas. THIS is engineering
     mass balance and it lives in the frontend, not here.

  2. TECHNO-ECONOMIC — `tea_engine/` on :8002, OpenPyTEA with CEPCI indexing.
     CAPEX/OPEX from equipment sizing. Falls back to a stub that labels itself
     engine="stub", so a stub result can never pass as a real one.

  3. CUSTODY AND ALLOCATION — this module. No physics. Two operations:
     allocated += volume, remaining = total − allocated.

None of the three is wired to the others. A lot's volume is not checked against
the process model, and the process model is not checked against metered output.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not validate equipment sizing, process design, conversion yield,
utilities, losses, recycle closure, CAPEX or OPEX. It does not verify that the
declared volume was produced, that the carbon intensity is correct, or that the
certification is valid. Those are the province of the metering system, the
independent engineer, the LCA practitioner and the scheme auditor.

`total_volume_kg`, `carbon_intensity_gco2e_mj` and `certification_pathway`
arrive as ASSERTED INPUTS. The ledger's job is to stop the same declared tonne
being promised twice, and to make any change to that record detectable.

ALIGNMENT WITH RED III / EU 2018/2001 ARTICLE 30
-----------------------------------------------
Under RED III, "mass balance" is one of the permitted chain-of-custody methods
(as opposed to physical segregation, identity preservation, or book-and-claim —
and note book-and-claim is NOT permitted for RFNBO, which requires a physical
link). Article 30 requires, in substance, that:

  a) consignments with differing sustainability characteristics may be mixed;
  b) information on those characteristics and on consignment size stays
     assigned to the consignments;
  c) the sum withdrawn is not greater than the sum added, over a defined
     accounting period.

This module satisfies (c) for a single lot, and carries one characteristic
(carbon intensity) plus a pathway label. It does NOT yet satisfy (a) or (b),
and the following are known gaps rather than oversights:

  · NO ACCOUNTING PERIOD. RED III mass balance is period-based; this ledger has
    no period boundary, so it cannot yet produce a period statement.
  · NO INPUT CONSIGNMENTS. Only outputs (lots) are recorded. A compliant system
    tracks certified input added as well as product withdrawn.
  · NO CONVERSION FACTOR between input and output, so input/output cannot be
    reconciled across a processing step.
  · ONE CHARACTERISTIC PER LOT. A consignment carries a set of sustainability
    characteristics, not a single CI figure.

Scheme-specific rules — permitted period length, treatment of a negative
interim balance, allowed mixing — differ between ISCC EU, REDcert and others
and MUST be confirmed with the certifying body before any compliance claim is
made on the basis of this ledger.

DESIGN
------
  - Lot created when a production batch is confirmed
  - Tokens allocate volume from the lot (deduct remaining)
  - Allocation rejected if remaining < requested (exhaustion guard)
  - Append-only, hash-chained allocation log (prev_hash → allocation_hash)
  - project_id is validated against the canonical projects store

Store: DOMAIN_DB_BACKEND (SQLite or PostgreSQL, via domain_connection).
"""

import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.core.db_backend import domain_connection, domain_is_postgres

router = APIRouter(prefix="/api/v1/chain-of-custody", tags=["chain-of-custody"])


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
    """Follows DOMAIN_DB_BACKEND. No module-owned path, and nothing captured at
    import: the store is resolved per request, so the tenant context of THIS
    caller is what 044's project-scoped policies see."""
    conn = domain_connection()
    try:
        if not domain_is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def init_db():
    if domain_is_postgres():
        # Migrations 043/044 own these tables and their RLS policies. gex_app
        # has no CREATE on schema public, so this DDL cannot run there — and
        # must not: a runtime-created table would carry no policy.
        return
    conn = domain_connection()
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


def _assert_project_exists(project_id: str) -> None:
    """A lot must hang off a real project, or custody is anchored to nothing.

    The two failure modes are deliberately NOT the same status. `projects_store`
    fails soft — it logs and returns None when PostgreSQL is unreachable — so a
    naive "not found → 404" would report an outage as an invalid project, and a
    caller would 'fix' it by inventing a different project_id. An outage is a
    503; only a reachable store that has never heard of the project is a 404.
    """
    from app.core import projects_store

    try:
        project = projects_store.fetch_project(project_id)
    except Exception as exc:  # noqa: BLE001 — cannot check ≠ does not exist
        raise HTTPException(
            503,
            f"Cannot verify project {project_id}: the projects store is "
            f"unreachable ({type(exc).__name__}). Lot not created.",
        ) from exc

    if project is None:
        # `fetch_project` returns None BOTH for "no such project" and for "the
        # database was unreachable", because projects_store deliberately fails
        # soft to keep ABAC hot paths alive. So None alone proves nothing, and
        # probing with list_projects() does not help either — it fails soft to
        # [] and an empty list is not distinguishable from an outage.
        #
        # Probe the engine directly, where an outage actually raises.
        from sqlalchemy import text as _text

        try:
            with projects_store._engine().connect() as conn:
                conn.execute(_text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                503,
                f"Cannot verify project {project_id}: the projects store is "
                f"unreachable ({type(exc).__name__}). Lot not created.",
            ) from exc
        raise HTTPException(
            404,
            f"Project {project_id} not found. A custody lot must reference an "
            "existing project.",
        )


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
def create_lot(lot: LotCreate, db: Any = Depends(get_db)):
    _assert_project_exists(lot.project_id)
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
def get_lot(lot_id: str, db: Any = Depends(get_db)):
    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (lot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Lot {lot_id} not found")
    return _lot_row(row)


@router.get("/lots/project/{project_id}", response_model=list[LotResponse])
def list_lots_by_project(
    project_id: str,
    status: Optional[LotStatus] = Query(None),
    db: Any = Depends(get_db),
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
def allocate_from_lot(alloc: AllocationCreate, db: Any = Depends(get_db)):
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
def list_allocations(lot_id: str, db: Any = Depends(get_db)):
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
def lot_summary(project_id: str, db: Any = Depends(get_db)):
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
