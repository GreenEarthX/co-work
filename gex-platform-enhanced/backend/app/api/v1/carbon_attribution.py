"""
carbon_attribution.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Host-nation carbon attribution for SOVEREIGN_ESG tokens. When a settlement
completes, the carbon volume must be attributed between the host nation and
the buyer according to Article 6 / CORSIA / CBAM rules.

Design principles:
  - Every settled carbon volume gets a dual attribution record
  - host_nation_share_pct + buyer_share_pct must equal 100
  - Attribution is immutable once REGISTERED in a sovereign registry
  - Sovereign certifiers (IMF, World Bank, National Authority) validate

Integration points:
  - FK to settlement_events.py (settlement_id — carbon must be settled first)
  - FK to tokens_sqlite.py (token_id)
  - FK to sovereign_instruments.py (debt_swap_id — optional D4N link)
  - Feeds regulator dashboards (nation-level carbon attribution totals)
  - Event log feeds event_store.py / event_bus.py

ABAC alignment (abac.py):
  - PRODUCER: create + read own attributions
  - REGULATOR / CERTIFIER: read + advance to VERIFIED / REGISTERED
  - FINANCE / DFI: read (exposure to sovereign carbon risk)
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
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/carbon-attribution", tags=["carbon-attribution"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class AttributionStatus(str, Enum):
    DRAFT      = "DRAFT"
    SUBMITTED  = "SUBMITTED"
    VERIFIED   = "VERIFIED"
    REGISTERED = "REGISTERED"


# State machine: DRAFT -> SUBMITTED -> VERIFIED -> REGISTERED
VALID_TRANSITIONS = {
    AttributionStatus.DRAFT:      [AttributionStatus.SUBMITTED],
    AttributionStatus.SUBMITTED:  [AttributionStatus.VERIFIED],
    AttributionStatus.VERIFIED:   [AttributionStatus.REGISTERED],
    AttributionStatus.REGISTERED: [],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class AttributionCreate(BaseModel):
    settlement_id:            str = Field(..., description="FK to settlement_events")
    token_id:                 str = Field(..., description="FK to tokens")
    project_id:               str
    host_nation:              str = Field(..., description="ISO country code")
    host_nation_share_pct:    float = Field(..., ge=0, le=100)
    buyer_share_pct:          float = Field(..., ge=0, le=100)
    carbon_volume_tonnes:     float = Field(..., gt=0)
    sovereign_certifier:      str = Field(..., description="e.g. IMF, WORLD_BANK, NATIONAL_AUTHORITY")
    debt_swap_id:             Optional[str] = Field(None, description="FK to sovereign_instruments")
    attribution_methodology:  Optional[str] = None
    changed_by:               str

    @model_validator(mode="after")
    def shares_must_equal_100(self):
        if abs((self.host_nation_share_pct + self.buyer_share_pct) - 100.0) > 0.01:
            raise ValueError(
                f"host_nation_share_pct ({self.host_nation_share_pct}) + "
                f"buyer_share_pct ({self.buyer_share_pct}) must equal 100"
            )
        return self


class AttributionResponse(BaseModel):
    attribution_id:           str
    settlement_id:            str
    token_id:                 str
    project_id:               str
    host_nation:              str
    host_nation_share_pct:    float
    buyer_share_pct:          float
    carbon_volume_tonnes:     float
    sovereign_certifier:      str
    debt_swap_id:             Optional[str]
    attribution_methodology:  Optional[str]
    attribution_status:       str
    registry_ref:             Optional[str]
    audit_hash:               str
    version:                  int
    created_at:               str
    updated_at:               str


class NationSummary(BaseModel):
    host_nation:              str
    total_attributions:       int
    total_carbon_tonnes:      float
    host_nation_carbon_tonnes: float
    buyer_carbon_tonnes:      float
    by_status:                dict   # status -> count
    by_certifier:             dict   # certifier -> count


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
    Create CARBON_ATTRIBUTION_EVENTS table.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS carbon_attribution_events (
            attribution_id         TEXT PRIMARY KEY,
            settlement_id          TEXT NOT NULL,
            token_id               TEXT NOT NULL,
            project_id             TEXT NOT NULL,
            host_nation            TEXT NOT NULL,
            host_nation_share_pct  REAL NOT NULL,
            buyer_share_pct        REAL NOT NULL,
            carbon_volume_tonnes   REAL NOT NULL,
            sovereign_certifier    TEXT NOT NULL,
            debt_swap_id           TEXT,
            attribution_methodology TEXT,
            attribution_status     TEXT NOT NULL DEFAULT 'DRAFT',
            registry_ref           TEXT,
            audit_hash             TEXT NOT NULL,
            version                INTEGER NOT NULL DEFAULT 1,
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_settlement ON carbon_attribution_events(settlement_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_project ON carbon_attribution_events(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_nation ON carbon_attribution_events(host_nation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_status ON carbon_attribution_events(attribution_status)")

    # Audit table — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS carbon_attribution_event_log (
            event_id       TEXT PRIMARY KEY,
            attribution_id TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_attribution ON carbon_attribution_event_log(attribution_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_attribution(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_event(conn, attribution_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM carbon_attribution_event_log "
        "WHERE attribution_id=? ORDER BY created_at DESC LIMIT 1",
        (attribution_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "attribution_id": attribution_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO carbon_attribution_event_log
        (event_id, attribution_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), attribution_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "attribution_id":          row["attribution_id"],
        "settlement_id":           row["settlement_id"],
        "token_id":                row["token_id"],
        "project_id":              row["project_id"],
        "host_nation":             row["host_nation"],
        "host_nation_share_pct":   row["host_nation_share_pct"],
        "buyer_share_pct":         row["buyer_share_pct"],
        "carbon_volume_tonnes":    row["carbon_volume_tonnes"],
        "sovereign_certifier":     row["sovereign_certifier"],
        "debt_swap_id":            row["debt_swap_id"],
        "attribution_methodology": row["attribution_methodology"],
        "attribution_status":      row["attribution_status"],
        "registry_ref":            row["registry_ref"],
        "audit_hash":              row["audit_hash"],
        "version":                 row["version"],
        "created_at":              row["created_at"],
        "updated_at":              row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=AttributionResponse, status_code=201)
def create_attribution(a: AttributionCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a carbon attribution record for a settlement.
    Validates host_nation_share_pct + buyer_share_pct == 100.
    Fires event: attribution.created
    """
    attribution_id = str(uuid.uuid4())
    now = _now()

    content = {
        "attribution_id": attribution_id,
        "settlement_id": a.settlement_id,
        "token_id": a.token_id,
        "project_id": a.project_id,
        "host_nation": a.host_nation,
        "carbon_volume_tonnes": a.carbon_volume_tonnes,
        "created_at": now,
    }
    audit_hash = _hash_attribution(content)

    db.execute("""
        INSERT INTO carbon_attribution_events
        (attribution_id, settlement_id, token_id, project_id,
         host_nation, host_nation_share_pct, buyer_share_pct,
         carbon_volume_tonnes, sovereign_certifier, debt_swap_id,
         attribution_methodology, attribution_status, registry_ref,
         audit_hash, version, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        attribution_id, a.settlement_id, a.token_id, a.project_id,
        a.host_nation, a.host_nation_share_pct, a.buyer_share_pct,
        a.carbon_volume_tonnes, a.sovereign_certifier, a.debt_swap_id,
        a.attribution_methodology, AttributionStatus.DRAFT.value, None,
        audit_hash, 1, now, now
    ))
    _log_event(db, attribution_id, a.project_id, "attribution.created",
               a.changed_by, new_val=a.settlement_id)
    db.commit()

    row = db.execute("SELECT * FROM carbon_attribution_events WHERE attribution_id=?", (attribution_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{attribution_id}", response_model=AttributionResponse)
def get_attribution(attribution_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM carbon_attribution_events WHERE attribution_id=?", (attribution_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Attribution {attribution_id} not found")
    return _row_to_response(row)


@router.get("/settlement/{settlement_id}", response_model=list[AttributionResponse])
def list_by_settlement(settlement_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Attribution records for a settlement."""
    rows = db.execute(
        "SELECT * FROM carbon_attribution_events WHERE settlement_id=? ORDER BY created_at DESC",
        (settlement_id,)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.get("/project/{project_id}", response_model=list[AttributionResponse])
def list_by_project(
    project_id: str,
    host_nation: Optional[str] = Query(None, description="Filter by ISO country code"),
    db: sqlite3.Connection = Depends(get_db)
):
    """All attributions for a project with optional host_nation filter."""
    query = "SELECT * FROM carbon_attribution_events WHERE project_id=?"
    params: list = [project_id]
    if host_nation:
        query += " AND host_nation=?"
        params.append(host_nation)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.post("/{attribution_id}/advance", response_model=AttributionResponse)
def advance_attribution(
    attribution_id: str,
    changed_by: str = Query(...),
    sovereign_certifier: Optional[str] = Query(None, description="Required when advancing to VERIFIED"),
    registry_ref: Optional[str] = Query(None, description="Set when advancing to REGISTERED"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance attribution status one step forward.
    DRAFT -> SUBMITTED -> VERIFIED -> REGISTERED

    Guards:
      - VERIFIED requires sovereign_certifier
      - REGISTERED sets registry_ref
    """
    row = db.execute("SELECT * FROM carbon_attribution_events WHERE attribution_id=?", (attribution_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Attribution {attribution_id} not found")

    current = AttributionStatus(row["attribution_status"])
    valid_next = VALID_TRANSITIONS.get(current, [])
    if not valid_next:
        raise HTTPException(400, f"Attribution is in terminal state: {current.value}")

    new_status = valid_next[0]  # Always one valid next state

    # State-specific guards
    if new_status == AttributionStatus.VERIFIED:
        certifier = sovereign_certifier or row["sovereign_certifier"]
        if not certifier:
            raise HTTPException(400,
                "Cannot advance to VERIFIED: sovereign_certifier is required. "
                "Provide the certifying body (IMF, WORLD_BANK, NATIONAL_AUTHORITY)."
            )

    if new_status == AttributionStatus.REGISTERED and not registry_ref:
        raise HTTPException(400,
            "Cannot advance to REGISTERED: registry_ref is required. "
            "Provide the sovereign registry reference number."
        )

    now = _now()
    new_hash = _hash_attribution({
        "attribution_id": attribution_id,
        "status": new_status.value,
        "advanced_at": now,
    })

    update_query = """
        UPDATE carbon_attribution_events
        SET attribution_status=?, audit_hash=?, version=version+1, updated_at=?
    """
    params: list = [new_status.value, new_hash, now]

    if new_status == AttributionStatus.REGISTERED and registry_ref:
        update_query += ", registry_ref=?"
        params.append(registry_ref)

    update_query += " WHERE attribution_id=?"
    params.append(attribution_id)

    db.execute(update_query, params)

    _log_event(db, attribution_id, row["project_id"], "attribution.advanced",
               changed_by, field="attribution_status",
               old_val=current.value, new_val=new_status.value)
    db.commit()

    row = db.execute("SELECT * FROM carbon_attribution_events WHERE attribution_id=?", (attribution_id,)).fetchone()
    return _row_to_response(row)


@router.get("/nation/{country_code}/summary", response_model=NationSummary)
def nation_summary(country_code: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Total attributed carbon by nation — regulator view.
    Shows total volume, host/buyer splits, by status, by certifier.
    """
    rows = db.execute(
        "SELECT * FROM carbon_attribution_events WHERE host_nation=?",
        (country_code,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No attributions found for nation {country_code}")

    total_carbon = sum(r["carbon_volume_tonnes"] for r in rows)
    host_carbon = sum(
        r["carbon_volume_tonnes"] * r["host_nation_share_pct"] / 100.0 for r in rows
    )
    buyer_carbon = sum(
        r["carbon_volume_tonnes"] * r["buyer_share_pct"] / 100.0 for r in rows
    )

    by_status: dict = {}
    for r in rows:
        by_status[r["attribution_status"]] = by_status.get(r["attribution_status"], 0) + 1

    by_certifier: dict = {}
    for r in rows:
        by_certifier[r["sovereign_certifier"]] = by_certifier.get(r["sovereign_certifier"], 0) + 1

    return NationSummary(
        host_nation=country_code,
        total_attributions=len(rows),
        total_carbon_tonnes=total_carbon,
        host_nation_carbon_tonnes=round(host_carbon, 2),
        buyer_carbon_tonnes=round(buyer_carbon, 2),
        by_status=by_status,
        by_certifier=by_certifier,
    )
