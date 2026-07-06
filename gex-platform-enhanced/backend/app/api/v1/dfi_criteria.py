"""
dfi_criteria.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Per-institution criteria tracking for Development Finance Institutions.
Each DFI (EIB, KfW, IFC, BPI, DFC, AfDB) imposes specific eligibility
criteria on a project before capital can be drawn. This module tracks
criterion-level status, evidence linkage, and drawdown-blocking flags.

Integration points:
  - evidence_ledger.py: evidence_ref links to SHA-256 hash-chain entries
  - capital_bridge.py: blocks_drawdown=True freezes tranche drawdown
  - bankability_engine.py: readiness_pct feeds into effective_score weighting
  - development_packages.py: packages with concessional_tranche_id link here

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

router = APIRouter(prefix="/api/v1/dfi-criteria", tags=["dfi-criteria"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class DFIInstitution(str, Enum):
    EIB  = "EIB"
    KFW  = "KFW"
    IFC  = "IFC"
    BPI  = "BPI"
    DFC  = "DFC"
    AFDB = "AFDB"


class CriterionStatus(str, Enum):
    MET            = "MET"
    IN_PROGRESS    = "IN_PROGRESS"
    PENDING        = "PENDING"
    CHECK          = "CHECK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ═══════════════════════════════════════════════════════════════════════════
# SEED CRITERIA — typical requirements per institution
# ═══════════════════════════════════════════════════════════════════════════

SEED_CRITERIA: dict[str, list[dict]] = {
    "EIB": [
        {"code": "EIB_EU_TAXONOMY", "name": "EU Taxonomy Alignment", "requirement": "Project must qualify under EU Taxonomy Delegated Act for climate change mitigation"},
        {"code": "EIB_CLIMATE_CONTRIBUTION", "name": "Climate Contribution", "requirement": "Demonstrate measurable climate contribution per EIB Climate Bank Roadmap"},
        {"code": "EIB_DO_NO_SIGNIFICANT_HARM", "name": "Do No Significant Harm", "requirement": "DNSH assessment across all six EU Taxonomy environmental objectives"},
        {"code": "EIB_MINIMUM_SAFEGUARDS", "name": "Minimum Safeguards", "requirement": "Compliance with OECD Guidelines, UN Guiding Principles, ILO core conventions"},
    ],
    "IFC": [
        {"code": "IFC_PS_1_ASSESSMENT", "name": "PS1 — Assessment & Management", "requirement": "Environmental and Social Assessment and Management System in place"},
        {"code": "IFC_PS_2_LABOR", "name": "PS2 — Labor & Working Conditions", "requirement": "Compliance with IFC Performance Standard 2 on labor rights"},
        {"code": "IFC_PS_3_POLLUTION", "name": "PS3 — Resource Efficiency & Pollution", "requirement": "Pollution prevention and resource efficiency measures documented"},
        {"code": "IFC_PS_4_COMMUNITY", "name": "PS4 — Community Health & Safety", "requirement": "Community health, safety, and security risk assessment completed"},
        {"code": "IFC_PS_5_LAND", "name": "PS5 — Land Acquisition & Resettlement", "requirement": "Land acquisition due diligence and resettlement plan if applicable"},
        {"code": "IFC_PS_6_BIODIVERSITY", "name": "PS6 — Biodiversity Conservation", "requirement": "Biodiversity assessment and critical habitat screening completed"},
        {"code": "IFC_PS_7_INDIGENOUS", "name": "PS7 — Indigenous Peoples", "requirement": "Free, prior, and informed consent process where indigenous peoples affected"},
        {"code": "IFC_PS_8_CULTURAL", "name": "PS8 — Cultural Heritage", "requirement": "Cultural heritage impact assessment and chance-finds procedure"},
    ],
    "KFW": [
        {"code": "KFW_IKB_GREEN_LOAN", "name": "IKB Green Loan Eligible", "requirement": "Meets KfW IKB green loan programme eligibility criteria"},
        {"code": "KFW_CLIMATE_ACTION_ELIGIBLE", "name": "Climate Action Eligible", "requirement": "Qualifies under KfW climate action and energy transition programme"},
        {"code": "KFW_GERMAN_DEV_POLICY", "name": "German Development Policy", "requirement": "Aligned with German Federal Government development policy objectives"},
    ],
    "BPI": [
        {"code": "BPI_PLAN_HYDROGENE", "name": "Plan Hydrogène Eligible", "requirement": "Eligible under France Relance / Plan Hydrogène national strategy"},
        {"code": "BPI_FRENCH_TAXONOMY", "name": "French Taxonomy Alignment", "requirement": "Meets French green taxonomy requirements (Article 29 LEC)"},
        {"code": "BPI_ADEME_ELIGIBLE", "name": "ADEME Eligible", "requirement": "Project qualifies for ADEME co-financing or subsidy schemes"},
    ],
    "DFC": [
        {"code": "DFC_BUILD_ACT_ELIGIBLE", "name": "BUILD Act Eligible", "requirement": "Qualifies under US BUILD Act development finance authority"},
        {"code": "DFC_US_NATIONAL_INTEREST", "name": "US National Interest", "requirement": "Project demonstrates alignment with US foreign policy and national interest"},
        {"code": "DFC_DEVELOPMENT_IMPACT", "name": "Development Impact", "requirement": "Measurable development impact per DFC impact quotient methodology"},
    ],
    "AFDB": [
        {"code": "AFDB_HOST_NATION_BENEFIT", "name": "Host Nation Benefit", "requirement": "Demonstrated economic benefit to host African nation"},
        {"code": "AFDB_AFRICAN_DEV_STRATEGY", "name": "African Development Strategy", "requirement": "Aligned with AfDB High 5 priorities and country strategy papers"},
        {"code": "AFDB_CLIMATE_ADAPTATION", "name": "Climate Adaptation", "requirement": "Climate adaptation component or climate-resilient design demonstrated"},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class CriterionCreate(BaseModel):
    project_id: str
    institution: DFIInstitution
    criterion_code: str = Field(..., description="e.g. EIB_TAXONOMY, IFC_PS_1_8, BUILD_ACT_ELIGIBLE")
    criterion_name: str = Field(..., description="Human-readable criterion name")
    requirement_text: str = Field(..., description="Verbatim requirement from institution")
    status: CriterionStatus = CriterionStatus.PENDING
    evidence_ref: Optional[str] = Field(None, description="evidence_id when status=MET")
    responsible_actor: str = Field(..., description="FK to user — assigned owner")
    target_date: Optional[str] = Field(None, description="ISO date target")
    blocks_drawdown: bool = Field(False, description="TRUE means unsatisfied criterion freezes tranche drawdown")
    changed_by: str


class CriterionUpdate(BaseModel):
    criterion_name: Optional[str] = None
    requirement_text: Optional[str] = None
    status: Optional[CriterionStatus] = None
    evidence_ref: Optional[str] = None
    responsible_actor: Optional[str] = None
    target_date: Optional[str] = None
    blocks_drawdown: Optional[bool] = None
    changed_by: str = Field(..., description="Actor ID making the change")


class CriterionResponse(BaseModel):
    criterion_id: str
    project_id: str
    institution: str
    criterion_code: str
    criterion_name: str
    requirement_text: str
    status: str
    evidence_ref: Optional[str]
    responsible_actor: str
    target_date: Optional[str]
    blocks_drawdown: bool
    last_reviewed: Optional[str]
    version: int
    created_at: str
    updated_at: str


class InstitutionSummary(BaseModel):
    institution: str
    total: int
    met: int
    blocking: int
    readiness_pct: float


class ProjectDFISummary(BaseModel):
    project_id: str
    institutions: list[InstitutionSummary]


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
    Create dfi_criteria + dfi_criteria_events tables.
    Call from app/main.py startup alongside other init_db() calls.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dfi_criteria (
            criterion_id       TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            institution        TEXT NOT NULL,
            criterion_code     TEXT NOT NULL,
            criterion_name     TEXT NOT NULL,
            requirement_text   TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'PENDING',
            evidence_ref       TEXT,
            responsible_actor  TEXT NOT NULL,
            target_date        TEXT,
            blocks_drawdown    INTEGER NOT NULL DEFAULT 0,
            last_reviewed      TEXT,
            version            INTEGER NOT NULL DEFAULT 1,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfi_project ON dfi_criteria(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfi_institution ON dfi_criteria(institution)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfi_status ON dfi_criteria(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfi_blocking ON dfi_criteria(blocks_drawdown)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS dfi_criteria_events (
            event_id       TEXT PRIMARY KEY,
            criterion_id   TEXT NOT NULL,
            project_id     TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            field_changed  TEXT,
            old_value      TEXT,
            new_value      TEXT,
            changed_by     TEXT NOT NULL,
            event_hash     TEXT NOT NULL,
            prev_hash      TEXT,
            created_at     TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfi_evt_criterion ON dfi_criteria_events(criterion_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(conn, criterion_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None, new_val=None):
    now = _now()
    prev = conn.execute(
        "SELECT event_hash FROM dfi_criteria_events "
        "WHERE criterion_id=? ORDER BY created_at DESC LIMIT 1",
        (criterion_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "criterion_id": criterion_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO dfi_criteria_events
        (event_id, criterion_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), criterion_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "criterion_id": row["criterion_id"],
        "project_id": row["project_id"],
        "institution": row["institution"],
        "criterion_code": row["criterion_code"],
        "criterion_name": row["criterion_name"],
        "requirement_text": row["requirement_text"],
        "status": row["status"],
        "evidence_ref": row["evidence_ref"],
        "responsible_actor": row["responsible_actor"],
        "target_date": row["target_date"],
        "blocks_drawdown": bool(row["blocks_drawdown"]),
        "last_reviewed": row["last_reviewed"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=CriterionResponse, status_code=201)
def create_criterion(crit: CriterionCreate, db: sqlite3.Connection = Depends(get_db)):
    """Create a single DFI criterion entry."""
    criterion_id = str(uuid.uuid4())
    now = _now()

    db.execute("""
        INSERT INTO dfi_criteria
        (criterion_id, project_id, institution, criterion_code, criterion_name,
         requirement_text, status, evidence_ref, responsible_actor, target_date,
         blocks_drawdown, last_reviewed, version, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        criterion_id, crit.project_id, crit.institution.value, crit.criterion_code,
        crit.criterion_name, crit.requirement_text, crit.status.value,
        crit.evidence_ref, crit.responsible_actor, crit.target_date,
        int(crit.blocks_drawdown), None, 1, now, now
    ))
    _log_event(db, criterion_id, crit.project_id, "criterion.created",
               crit.changed_by, new_val=crit.criterion_code)
    db.commit()

    row = db.execute("SELECT * FROM dfi_criteria WHERE criterion_id=?", (criterion_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{criterion_id}", response_model=CriterionResponse)
def get_criterion(criterion_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM dfi_criteria WHERE criterion_id=?", (criterion_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Criterion {criterion_id} not found")
    return _row_to_response(row)


@router.get("/project/{project_id}", response_model=list[CriterionResponse])
def list_criteria(
    project_id: str,
    institution: Optional[DFIInstitution] = Query(None),
    status: Optional[CriterionStatus] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """List all DFI criteria for a project with optional filters."""
    query = "SELECT * FROM dfi_criteria WHERE project_id=?"
    params: list = [project_id]

    if institution:
        query += " AND institution=?"; params.append(institution.value)
    if status:
        query += " AND status=?"; params.append(status.value)

    query += " ORDER BY institution, criterion_code"
    rows = db.execute(query, params).fetchall()
    return [_row_to_response(r) for r in rows]


@router.patch("/{criterion_id}", response_model=CriterionResponse)
def update_criterion(
    criterion_id: str,
    update: CriterionUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Update criterion fields. Auto-stamps last_reviewed when status changes.
    Every change is logged to the event chain.
    """
    row = db.execute("SELECT * FROM dfi_criteria WHERE criterion_id=?", (criterion_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Criterion {criterion_id} not found")

    now = _now()
    fields = update.model_dump(exclude_none=True, exclude={"changed_by"})
    status_changed = False

    for field, new_val in fields.items():
        old_val = row[field] if field in row.keys() else None
        stored = new_val
        if field == "status":
            stored = new_val.value if hasattr(new_val, "value") else new_val
            status_changed = True
        if field == "blocks_drawdown":
            stored = int(new_val)

        db.execute(
            f"UPDATE dfi_criteria SET {field}=?, version=version+1, updated_at=? WHERE criterion_id=?",
            (stored, now, criterion_id)
        )
        _log_event(db, criterion_id, row["project_id"], "criterion.updated",
                   update.changed_by, field=field, old_val=old_val, new_val=new_val)

    # Auto-stamp last_reviewed on status change
    if status_changed:
        db.execute(
            "UPDATE dfi_criteria SET last_reviewed=? WHERE criterion_id=?",
            (now, criterion_id)
        )

    db.commit()
    row = db.execute("SELECT * FROM dfi_criteria WHERE criterion_id=?", (criterion_id,)).fetchone()
    return _row_to_response(row)


@router.get("/project/{project_id}/summary", response_model=ProjectDFISummary)
def project_dfi_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Per-institution summary: total/met/blocking counts, readiness_pct."""
    rows = db.execute(
        "SELECT * FROM dfi_criteria WHERE project_id=?", (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No DFI criteria found for project {project_id}")

    # Group by institution
    by_inst: dict[str, list] = {}
    for r in rows:
        by_inst.setdefault(r["institution"], []).append(r)

    institutions = []
    for inst, criteria in sorted(by_inst.items()):
        total = len(criteria)
        met = sum(1 for c in criteria if c["status"] == "MET")
        blocking = sum(
            1 for c in criteria
            if c["blocks_drawdown"] and c["status"] != "MET"
        )
        readiness_pct = round((met / total * 100) if total else 0.0, 1)
        institutions.append(InstitutionSummary(
            institution=inst,
            total=total,
            met=met,
            blocking=blocking,
            readiness_pct=readiness_pct,
        ))

    return ProjectDFISummary(project_id=project_id, institutions=institutions)


@router.get("/project/{project_id}/blocking", response_model=list[CriterionResponse])
def blocking_criteria(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """List all criteria where blocks_drawdown=True AND status!=MET."""
    rows = db.execute(
        "SELECT * FROM dfi_criteria WHERE project_id=? AND blocks_drawdown=1 AND status!='MET' "
        "ORDER BY institution, criterion_code",
        (project_id,)
    ).fetchall()
    return [_row_to_response(r) for r in rows]


@router.post("/project/{project_id}/seed/{institution}", status_code=201)
def seed_institution_criteria(
    project_id: str,
    institution: DFIInstitution,
    responsible_actor: str = Query(..., description="Default responsible actor for seeded criteria"),
    changed_by: str = Query(..., description="Actor performing the seed"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Auto-create all standard criteria for a given institution on a project.
    Uses SEED_CRITERIA dict. All seeded criteria start as PENDING.
    """
    seed_list = SEED_CRITERIA.get(institution.value, [])
    if not seed_list:
        raise HTTPException(404, f"No seed criteria defined for {institution.value}")

    now = _now()
    created = []
    for item in seed_list:
        criterion_id = str(uuid.uuid4())
        db.execute("""
            INSERT INTO dfi_criteria
            (criterion_id, project_id, institution, criterion_code, criterion_name,
             requirement_text, status, evidence_ref, responsible_actor, target_date,
             blocks_drawdown, last_reviewed, version, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            criterion_id, project_id, institution.value, item["code"],
            item["name"], item["requirement"], CriterionStatus.PENDING.value,
            None, responsible_actor, None,
            0, None, 1, now, now
        ))
        _log_event(db, criterion_id, project_id, "criterion.seeded",
                   changed_by, new_val=item["code"])
        created.append(criterion_id)

    db.commit()

    rows = db.execute(
        "SELECT * FROM dfi_criteria WHERE criterion_id IN ({})".format(
            ",".join("?" for _ in created)
        ),
        created
    ).fetchall()
    return [_row_to_response(r) for r in rows]
