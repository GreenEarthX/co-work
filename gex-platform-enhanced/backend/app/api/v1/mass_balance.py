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

Since migration 097 (2026-11-12, GreenMesh Phase 1 Step 2) a lot can belong to an
ACCOUNTING PERIOD per facility, molecule and pathway (`app/core/custody_ledger.py`):

  · INPUT CONSIGNMENTS are recorded per period (electricity, CO2, N2, water, hydrogen),
    each with an evidence reference (PPA, GO, supplier PoS ...), hash-chained.
  · DECLARED CONVERSION, versioned per facility, pathway, molecule and input type, turns
    certified inputs into the period's credit. A lot declaring more output than all
    inputs allow (beyond the factor's tolerance) is FLAGGED, not silently accepted.
  · A WITHDRAWAL (an allocation to a token) beyond the period balance is refused.
  · CLOSING writes the period statement, opening + inputs x conversion - withdrawals =
    closing, and its hash; a closed period never changes.
  · A period lot carries a validated CHARACTERISTICS object (GHG intensity, pathway,
    scheme, certificate, origin, production window, RFNBO flag, additionality basis).

Still true: those characteristics and the inputs are DECLARED. Metered output is not
reconciled yet (Step 3) and correlation is not computed yet (Step 4). Lots created before
097, or without a period, carry no period and are not period-grade; they keep
`carbon_intensity_gco2e_mj` and work as before.

Scheme-specific rules — permitted period length, carry-forward, a negative interim
balance — differ between ISCC EU, REDcert and others. They live in `coc_scheme_rule`,
which ships EMPTY: with no confirmed rule the ledger applies the conservative reading and
says so. They MUST be confirmed with the certifying body before any compliance claim is
made on the basis of this ledger.

DESIGN
------
  - Lot created when a production batch is confirmed, optionally inside a period
  - Tokens allocate volume from the lot (deduct remaining); the token must exist, belong
    to the lot's project and not be retired, annulled or voided. The token is linked to
    the lot (`tokens.mass_balance_lot_id`); claim and retirement stay in tokens_sqlite.py
  - Allocation rejected if remaining < requested (exhaustion guard) and, for a period
    lot, if the period balance < requested
  - Append-only, hash-chained allocation log (prev_hash → allocation_hash)
  - project_id is validated against the canonical projects store

Store: PostgreSQL only (DOMAIN_DB_BACKEND=postgres), via domain_connection.
"""

import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.core import custody_ledger as cl
from app.core import meter_reconciliation as mr
from app.core.db_backend import domain_connection, domain_is_postgres, require_postgres

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
    created_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)
    # Since 097: a period lot names its period and carries validated characteristics.
    period_id: Optional[str] = None
    characteristics: Optional[dict] = None


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
    period_id: Optional[str] = None
    facility_id: Optional[str] = None
    characteristics: Optional[dict] = None
    conversion_check: Optional[str] = None
    conversion_detail: Optional[dict] = None
    custody_grade: str = "NO_PERIOD"
    # Since 098: the reconciliation against metered output known when the lot was
    # created (period lots), and the live one, recomputed on every read.
    meter_check: Optional[str] = None
    meter_detail: Optional[dict] = None
    meter_reconciliation: Optional[dict] = None


class AllocationCreate(BaseModel):
    lot_id: str
    token_id: str
    volume_kg: float = Field(..., gt=0)
    allocated_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


class AllocationResponse(BaseModel):
    allocation_id: str
    lot_id: str
    token_id: str
    volume_kg: float
    allocated_by: str
    allocation_hash: str
    prev_hash: Optional[str]
    created_at: str
    period_id: Optional[str] = None


class LotSummary(BaseModel):
    project_id: str
    total_lots: int
    total_production_kg: float
    total_allocated_kg: float
    total_remaining_kg: float
    by_status: dict
    by_molecule: dict


def get_db():
    # PostgreSQL only (JML, 2026-10-23); resolved per request.
    require_postgres(domain_is_postgres(), "Chain of custody", "DOMAIN_DB_BACKEND")
    conn = domain_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Nothing to create: migrations 043/044 own these tables and their RLS
    policies on PostgreSQL, the only store (JML, 2026-10-23). Requests refuse in
    get_db() when the switch is not postgres; startup does not."""


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



def _actor(claimed: Optional[str] = None) -> str:
    """The acting user, from the verified token (G-20) — never from the request body.

    A body still carrying a `*_by` field is accepted for compatibility; its value is
    ignored, and a different value is logged. With no signed-in user there is no actor,
    and a custody record without an attributable actor is not written."""
    from app.core.request_tenant import current_user
    uid = current_user()
    if not uid:
        raise HTTPException(401, "An attributable identity is required to write a custody record")
    if claimed and claimed != uid:
        logger.warning("custody write: ignored body actor %r; the actor recorded is %s", claimed, uid)
    return uid


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
        "period_id": row["period_id"],
        "facility_id": row["facility_id"],
        "characteristics": row["characteristics"],
        "conversion_check": row["conversion_check"],
        "conversion_detail": row["conversion_detail"],
        "custody_grade": "PERIOD" if row["period_id"] else "NO_PERIOD",
        "meter_check": row["meter_check"],
        "meter_detail": row["meter_detail"],
    }


def _lot_out(db, row) -> dict:
    out = _lot_row(row)
    out["meter_reconciliation"] = mr.lot_reconciliation(db, dict(row))
    return out


def _refuse(db, exc: Exception):
    """Map a refusal to a status. Triggers and constraints in 097 speak first; the
    application checks the same things earlier, so these are the backstop."""
    import psycopg2

    db.rollback()
    if isinstance(exc, cl.CustodyError):
        raise HTTPException(exc.status, exc.message) from exc
    if isinstance(exc, psycopg2.Error):
        msg = (exc.diag.message_primary if getattr(exc, "diag", None) else None) or str(exc)
        code = exc.pgcode
        if code == "42501":
            raise HTTPException(403, "Not permitted for this project: " + msg) from exc
        if code == "23514":
            raise HTTPException(409 if msg.startswith("COC_") else 422, msg) from exc
        if code in ("23505", "23503"):
            raise HTTPException(409 if code == "23505" else 422, msg) from exc
    raise exc


@router.post("/lots", response_model=LotResponse, status_code=201)
def create_lot(lot: LotCreate, db: Any = Depends(get_db)):
    _assert_project_exists(lot.project_id)
    if lot.period_id is None and lot.characteristics is not None:
        raise HTTPException(422, "characteristics belong to a period lot: name its period_id")
    lot_id = str(uuid.uuid4())
    now = _now()
    audit_hash = _hash({
        "lot_id": lot_id, "project_id": lot.project_id,
        "molecule": lot.molecule, "total_volume_kg": lot.total_volume_kg,
        "created_at": now,
    })
    try:
        facility_id = characteristics = check = detail = meter_check = meter_detail = None
        ci = lot.carbon_intensity_gco2e_mj
        if lot.period_id is not None:
            period = cl.period_row(db, lot.period_id, lock=True)
            if period["status"] != "OPEN":
                raise cl.CustodyError(409, f"COC_PERIOD_CLOSED: period {lot.period_id} is closed")
            if (period["project_id"], period["molecule"]) != (lot.project_id, lot.molecule):
                raise cl.CustodyError(422, "a period lot has its period's project and molecule")
            characteristics = cl.validate_characteristics(lot.characteristics, period, lot.production_date)
            if ci is not None and abs(ci - characteristics["ghg_intensity_gco2e_mj"]) > cl.EPS:
                raise cl.CustodyError(422, "carbon_intensity_gco2e_mj disagrees with "
                                           "characteristics.ghg_intensity_gco2e_mj")
            ci = characteristics["ghg_intensity_gco2e_mj"]     # the old column stays readable
            facility_id = period["facility_id"]
            check, detail = cl.conversion_check_for_new_lot(db, period, lot.total_volume_kg)
            meter_check, meter_detail = mr.reconcile_lot(
                db, lot.project_id, facility_id, lot.molecule,
                characteristics["production_window_start"], characteristics["production_window_end"],
                lot.total_volume_kg)
            meter_detail["checked_at"] = _now()

        db.execute("""
            INSERT INTO mass_balance_lots
            (lot_id, project_id, molecule, production_date, total_volume_kg,
             allocated_volume_kg, remaining_volume_kg, status,
             certification_pathway, carbon_intensity_gco2e_mj,
             audit_hash, created_by, created_at, updated_at,
             period_id, facility_id, characteristics, conversion_check, conversion_detail,
             meter_check, meter_detail)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CAST(? AS jsonb),?,CAST(? AS jsonb),?,CAST(? AS jsonb))
        """, (
            lot_id, lot.project_id, lot.molecule, lot.production_date,
            lot.total_volume_kg, 0.0, lot.total_volume_kg,
            LotStatus.OPEN.value, lot.certification_pathway,
            ci, audit_hash, _actor(lot.created_by), now, now,
            lot.period_id, facility_id,
            json.dumps(characteristics) if characteristics is not None else None,
            check, json.dumps(detail) if detail is not None else None,
            meter_check, json.dumps(meter_detail) if meter_detail is not None else None,
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — mapped or re-raised
        _refuse(db, exc)

    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (lot_id,)).fetchone()
    return _lot_out(db, row)


@router.get("/lots/{lot_id}", response_model=LotResponse)
def get_lot(lot_id: str, db: Any = Depends(get_db)):
    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=?", (lot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Lot {lot_id} not found")
    return _lot_out(db, row)


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
    return [_lot_out(db, r) for r in rows]


_TOKEN_STATES_WITHOUT_ALLOCATION = ("RETIRED", "ANNULLED", "VOIDED")


def _check_token(db, token_id: str, lot) -> None:
    """The token exists, belongs to the lot's project, can still take volume, and is not
    already backed by another lot. The claim itself stays with tokens_sqlite.py."""
    tok = db.execute(
        "SELECT t.id, t.lifecycle_state, t.mass_balance_lot_id, c.project_id "
        "FROM tokens t LEFT JOIN capacities c ON c.id = t.capacity_id WHERE t.id = ?",
        (token_id,)).fetchone()
    if not tok:
        raise cl.CustodyError(404, f"Token {token_id} not found")
    if (tok["lifecycle_state"] or "MINTED") in _TOKEN_STATES_WITHOUT_ALLOCATION:
        raise cl.CustodyError(409, f"Token {token_id} is {tok['lifecycle_state']}: it takes no allocation")
    if tok["project_id"] != lot["project_id"]:
        raise cl.CustodyError(409, f"Token {token_id} belongs to another project than lot {lot['lot_id']}")
    if tok["mass_balance_lot_id"] not in (None, lot["lot_id"]):
        raise cl.CustodyError(409, f"Token {token_id} is already backed by lot {tok['mass_balance_lot_id']}")


@router.post("/allocate", response_model=AllocationResponse, status_code=201)
def allocate_from_lot(alloc: AllocationCreate, db: Any = Depends(get_db)):
    """
    Allocate volume from a lot to a token. Rejects if:
      - lot not found or not OPEN
      - requested volume > remaining volume (exhaustion guard)
      - the token is unknown, of another project, retired/annulled/voided, or backed by
        another lot
      - for a period lot: the period is closed, or requested > the period balance
    Auto-transitions lot to EXHAUSTED when remaining hits zero.
    """
    actor = _actor(alloc.allocated_by)
    row = db.execute("SELECT * FROM mass_balance_lots WHERE lot_id=? FOR UPDATE", (alloc.lot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Lot {alloc.lot_id} not found")

    if row["status"] != LotStatus.OPEN.value:
        raise HTTPException(400, f"Lot {alloc.lot_id} is {row['status']}, not OPEN")

    # Hydrogen already taken as an input downstream (101) is not available to tokens.
    remaining = row["remaining_volume_kg"] - cl.cited_kg(db, alloc.lot_id)
    if alloc.volume_kg > remaining:
        raise HTTPException(
            400,
            f"Exhaustion guard: requested {alloc.volume_kg} kg but only "
            f"{remaining} kg remaining in lot {alloc.lot_id}",
        )

    allocation_id = str(uuid.uuid4())
    now = _now()
    try:
        _check_token(db, alloc.token_id, row)
        if row["period_id"]:
            cl.check_withdrawal(db, cl.period_row(db, row["period_id"], lock=True), alloc.volume_kg)

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
             allocation_hash, prev_hash, created_at, period_id)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            allocation_id, alloc.lot_id, alloc.token_id, alloc.volume_kg,
            actor, allocation_hash, prev_hash, now, row["period_id"],
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
        db.execute("UPDATE tokens SET mass_balance_lot_id = ? WHERE id = ? AND mass_balance_lot_id IS NULL",
                   (alloc.lot_id, alloc.token_id))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — mapped or re-raised
        _refuse(db, exc)

    return {
        "allocation_id": allocation_id,
        "lot_id": alloc.lot_id,
        "token_id": alloc.token_id,
        "volume_kg": alloc.volume_kg,
        "allocated_by": actor,
        "allocation_hash": allocation_hash,
        "prev_hash": prev_hash,
        "created_at": now,
        "period_id": row["period_id"],
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
            "period_id": r["period_id"],
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


# ── Accounting periods (migration 097; app/core/custody_ledger.py) ──────────

class PeriodCreate(BaseModel):
    project_id: str
    facility_id: str = Field(..., min_length=1)
    molecule: str
    pathway: str = Field(..., min_length=1, description="production route, e.g. PEM_ELECTROLYSIS")
    scheme: str = Field(..., min_length=1, description="certification scheme, e.g. ISCC_EU")
    period_start: str
    period_end: str
    opened_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


class InputCreate(BaseModel):
    input_type: str = Field(..., description="ELECTRICITY, CO2, N2, WATER or H2")
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., description="MWh/kWh/GWh for electricity; kg/t otherwise")
    sustainability_status: str = Field(..., description="CERTIFIED or NON_CERTIFIED")
    received_on: str
    evidence_kind: str = Field(..., description="PPA, GO, POS, SUPPLIER_INVOICE, METER or OTHER")
    evidence_ref: str = Field(..., min_length=1)
    characteristics: dict = Field(default_factory=dict)
    # Since 101: an H2 input names the upstream hydrogen lot; its correlation is carried through.
    source_lot_id: Optional[str] = None
    source_token_id: Optional[str] = None     # G-23 (110): a hydrogen token this company holds
    recorded_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


class FactorCreate(BaseModel):
    project_id: str
    facility_id: str = Field(..., min_length=1)
    pathway: str = Field(..., min_length=1)
    molecule: str
    input_type: str
    value: float = Field(..., gt=0, description="declared input per unit of output")
    unit: str = Field(..., description="kWh/kg, MWh/kg, MWh/t for electricity; kg/kg, t/t, kg/t otherwise")
    tolerance_fraction: Optional[float] = Field(None, ge=0)
    valid_from: str
    source: str = Field(..., min_length=1)
    recorded_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


class PeriodClose(BaseModel):
    closed_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


def _period_out(db, p: dict) -> dict:
    out = cl.public_period(p)
    if p["status"] == "CLOSED":
        out["position"] = p["statement"]
        out["meter_reconciliation"] = p["statement"].get("meter_reconciliation")
    else:
        out["position"] = cl.position(db, p)
        out["meter_reconciliation"] = mr.period_reconciliation(db, p, out["position"])
    return out


def _input_out(r: dict) -> dict:
    out = dict(r)
    for k in ("received_on", "recorded_at"):
        out[k] = cl._iso(out[k])
    return out


def _factor_out(r: dict) -> dict:
    out = dict(r)
    for k in ("valid_from", "recorded_at"):
        out[k] = cl._iso(out[k])
    return out


@router.post("/periods", status_code=201)
def open_period(body: PeriodCreate, db: Any = Depends(get_db)):
    """Open an accounting period for one facility, molecule and pathway. Its opening
    balance follows the scheme rule; with no confirmed rule there is no carry-forward."""
    _assert_project_exists(body.project_id)
    try:
        p = cl.open_period(db, body.model_dump(), _actor(body.opened_by))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _period_out(db, p)


@router.get("/periods/{period_id}")
def get_period(period_id: str, db: Any = Depends(get_db)):
    """An open period's live position, or a closed period's statement."""
    try:
        return _period_out(db, cl.period_row(db, period_id))
    except cl.CustodyError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/periods/project/{project_id}")
def list_periods(project_id: str, db: Any = Depends(get_db)):
    rows = db.execute("SELECT * FROM coc_period WHERE project_id = ? ORDER BY facility_id, molecule, "
                      "pathway, period_start", (project_id,)).fetchall()
    return [cl.public_period(dict(r)) for r in rows]


@router.post("/periods/{period_id}/inputs", status_code=201)
def record_input(period_id: str, body: InputCreate, db: Any = Depends(get_db)):
    """Record an input consignment with its evidence. Hash-chained within the period."""
    try:
        r = cl.record_input(db, period_id, body.model_dump(), _actor(body.recorded_by))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _input_out(r)


@router.get("/periods/{period_id}/inputs")
def list_inputs(period_id: str, db: Any = Depends(get_db)):
    rows = db.execute("SELECT * FROM coc_input WHERE period_id = ? ORDER BY seq", (period_id,)).fetchall()
    return [_input_out(dict(r)) for r in rows]


@router.post("/periods/{period_id}/close")
def close_period(period_id: str, body: Optional[PeriodClose] = None, db: Any = Depends(get_db)):
    """Close the period: write its statement and hash. A closed period never changes."""
    try:
        p = cl.close_period(db, period_id, _actor(body.closed_by if body else None))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _period_out(db, p)


@router.get("/periods/{period_id}/verify")
def verify_period(period_id: str, db: Any = Depends(get_db)):
    """Recompute the period's open hash, input chain and (closed) statement from the rows."""
    try:
        return cl.verify_period(db, period_id)
    except cl.CustodyError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.post("/conversion-factors", status_code=201)
def record_factor(body: FactorCreate, db: Any = Depends(get_db)):
    """Record a DECLARED conversion factor (input per unit of output), in force from
    `valid_from` until a later version. Never edited: a new value is a new row."""
    _assert_project_exists(body.project_id)
    try:
        r = cl.record_factor(db, body.model_dump(), _actor(body.recorded_by))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _factor_out(r)


@router.get("/conversion-factors/project/{project_id}")
def list_factors(project_id: str, db: Any = Depends(get_db)):
    rows = db.execute("SELECT * FROM coc_conversion_factor WHERE project_id = ? ORDER BY facility_id, "
                      "pathway, molecule, input_type, valid_from", (project_id,)).fetchall()
    return [_factor_out(dict(r)) for r in rows]


@router.get("/scheme-rules")
def list_scheme_rules(db: Any = Depends(get_db)):
    """The certifier-confirmed rules per scheme. Empty until GEX records one."""
    rows = db.execute("SELECT * FROM coc_scheme_rule ORDER BY scheme").fetchall()
    return [cl._rule_view(dict(r)) for r in rows]


# ── Meter tolerances (migration 098; app/core/meter_reconciliation.py) ──────

class ToleranceCreate(BaseModel):
    project_id: str
    facility_id: str = Field(..., min_length=1)
    measure: str = Field(..., description="PRODUCTION (of a molecule) or ELECTRICITY")
    molecule: Optional[str] = None
    tolerance_fraction: float = Field(..., ge=0)
    valid_from: str
    source: str = Field(..., min_length=1, description="who agreed it: certifier, independent engineer ...")
    recorded_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


@router.post("/meter-tolerances", status_code=201)
def record_tolerance(body: ToleranceCreate, db: Any = Depends(get_db)):
    """Record the tolerance agreed between declared and metered quantities. Never edited: a
    new value is a new row from its valid_from. With none recorded the tolerance is zero."""
    _assert_project_exists(body.project_id)
    if body.measure not in ("PRODUCTION", "ELECTRICITY"):
        raise HTTPException(422, "measure must be PRODUCTION or ELECTRICITY")
    if (body.measure == "PRODUCTION") != bool(body.molecule):
        raise HTTPException(422, "a PRODUCTION tolerance names its molecule; an ELECTRICITY one does not")
    tid = str(uuid.uuid4())
    try:
        db.execute(
            "INSERT INTO coc_meter_tolerance (tolerance_id, project_id, facility_id, measure, molecule, "
            "tolerance_fraction, valid_from, source, recorded_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (tid, body.project_id, body.facility_id, body.measure, body.molecule, body.tolerance_fraction,
             cl._d(body.valid_from), body.source.strip(), _actor(body.recorded_by)))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    r = dict(db.execute("SELECT * FROM coc_meter_tolerance WHERE tolerance_id = ?", (tid,)).fetchone())
    return {**r, "valid_from": cl._iso(r["valid_from"]), "recorded_at": cl._iso(r["recorded_at"])}


@router.get("/meter-tolerances/project/{project_id}")
def list_tolerances(project_id: str, db: Any = Depends(get_db)):
    rows = db.execute("SELECT * FROM coc_meter_tolerance WHERE project_id = ? ORDER BY facility_id, "
                      "measure, molecule, valid_from", (project_id,)).fetchall()
    return [{**dict(r), "valid_from": cl._iso(r["valid_from"]), "recorded_at": cl._iso(r["recorded_at"])}
            for r in rows]


# ── RFNBO correlation, computed (migration 099; app/core/rfnbo_correlation.py) ──

class FacilityProfileCreate(BaseModel):
    project_id: str
    facility_id: str = Field(..., min_length=1)
    bidding_zone: str = Field(..., min_length=1, description="e.g. DE-LU")
    electrolyser_commissioning_date: Optional[str] = None
    source: str = Field(..., min_length=1)
    recorded_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


class PPACreate(BaseModel):
    project_id: str
    facility_id: str = Field(..., min_length=1)
    ppa_ref: str = Field(..., min_length=1)
    generator_id: str = Field(..., min_length=1)
    generator_bidding_zone: str = Field(..., min_length=1)
    generator_commissioning_date: Optional[str] = None
    technology: Optional[str] = None
    evidence_ref: str = Field(..., min_length=1)
    recorded_by: Optional[str] = None   # IGNORED: the actor is the signed-in user (G-20)


def _dates_out(r: dict) -> dict:
    return {k: cl._iso(v) if hasattr(v, "isoformat") else v for k, v in r.items()}


@router.post("/facility-profiles", status_code=201)
def record_facility_profile(body: FacilityProfileCreate, db: Any = Depends(get_db)):
    """A facility's bidding zone and electrolyser commissioning date. Recorded once."""
    _assert_project_exists(body.project_id)
    d = cl._d(body.electrolyser_commissioning_date) if body.electrolyser_commissioning_date else None
    try:
        db.execute("INSERT INTO coc_facility_profile (project_id, facility_id, bidding_zone, "
                   "electrolyser_commissioning_date, source, recorded_by) VALUES (?,?,?,?,?,?)",
                   (body.project_id, body.facility_id, body.bidding_zone, d, body.source, _actor(body.recorded_by)))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _dates_out(dict(db.execute("SELECT * FROM coc_facility_profile WHERE project_id = ? AND facility_id = ?",
                                      (body.project_id, body.facility_id)).fetchone()))


@router.post("/ppas", status_code=201)
def record_ppa(body: PPACreate, db: Any = Depends(get_db)):
    """Register a PPA of a facility: its generator, bidding zone, commissioning date, evidence."""
    _assert_project_exists(body.project_id)
    pid = str(uuid.uuid4())
    d = cl._d(body.generator_commissioning_date) if body.generator_commissioning_date else None
    try:
        db.execute("INSERT INTO coc_ppa (ppa_id, project_id, facility_id, ppa_ref, generator_id, "
                   "generator_bidding_zone, generator_commissioning_date, technology, evidence_ref, recorded_by) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (pid, body.project_id, body.facility_id, body.ppa_ref, body.generator_id,
                    body.generator_bidding_zone, d, body.technology, body.evidence_ref, _actor(body.recorded_by)))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _refuse(db, exc)
    return _dates_out(dict(db.execute("SELECT * FROM coc_ppa WHERE ppa_id = ?", (pid,)).fetchone()))


@router.get("/periods/{period_id}/rfnbo-correlation")
def rfnbo_correlation(period_id: str, db: Any = Depends(get_db)):
    """Temporal, geographic and additionality checks COMPUTED from meters and PPAs. A closed
    period answers with the result recorded in its statement."""
    from app.core.rfnbo_correlation import evaluate_period

    try:
        p = cl.period_row(db, period_id)
    except cl.CustodyError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    if p["status"] == "CLOSED" and p["statement"].get("rfnbo_correlation"):
        return p["statement"]["rfnbo_correlation"]
    return evaluate_period(db, p)


@router.get("/rfnbo-rules")
def list_rfnbo_rules(db: Any = Depends(get_db)):
    rows = db.execute("SELECT * FROM rfnbo_rule ORDER BY rule_key, valid_from NULLS FIRST").fetchall()
    return [_dates_out(dict(r)) for r in rows]


@router.get("/upstream-proof/{token_id}")
def upstream_proof_route(token_id: str):
    """G-23 (110): the proof that a hydrogen token THIS company holds comes from a closed,
    re-verified upstream period, and its RFNBO result. 404 for a token it does not hold."""
    from app.core import upstream_proof
    from app.core.request_tenant import current_company

    pr = upstream_proof.proof(token_id, current_company())
    if pr is None:
        raise HTTPException(404, "No hydrogen token of your company with that id")
    return pr
