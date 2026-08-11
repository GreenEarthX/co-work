"""
development_packages.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

The Development Package Object is the core bridge between project definition
and capital release. Every cost line in a Greenfield e-fuel project is attached
to a named Package. No orphaned cost lines are accepted.

Design principles (Alt Bridge v0 + Hidalgo/Sung doctrine):
  - package → spend → evidence → risk removed → capital eligible → unlock → next gate
  - Pre-COD finance is a package-definition problem, not an operating-ratio problem
  - Each package has one owner, one purpose, one unlock condition, one downstream effect
  - Hidalgo: entropy reduction as capital logic — each transition reduces a specific uncertainty
  - Sung: single object carries cost, evidence, capital status, downstream effect (causal adjacency)
  - Two orthogonal progressions: workflow_state (knowledge maturity) + capital_status (capital engagement)

Integration points:
  - Feeds PLANT_BUILDER data (Excel Sheet 2)
  - Gates G0–G11 are referenced per package (bankability_engine.py)
  - capital_eligible drives CAPITAL_STACK tranche eligibility (waterfall.py via proxy)
  - workflow_state feeds Pre-COD metrics (pre_cod_metrics.py)
  - Evidence refs link to SHA-256 audit chain (audit.py)
  - concessional_tranche_id links to DFI waterfall (gex_pf_engine/waterfall.py)
  - debt_swap_id links to sovereign provenance (tokens_sqlite.py)

ABAC alignment (abac.py — align when sharing):
  - PRODUCER: full CRUD on own-project packages
  - FINANCE / DFI: read + approve workflow transitions
  - REGULATOR: read only, filtered by gate
  - EXECUTIVE: read-only portfolio aggregate

SQLite pattern: matches tokens_sqlite.py / contracts_sqlite.py conventions.
Replace DB_PATH with your actual db path constant from core/config.py.
"""

import os
import sqlite3
import uuid
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query, File, Form, Header, UploadFile
from pydantic import BaseModel, Field, field_validator

# Unified DB — single store for projects, users, packages, capital bridge,
# pre-COD metrics, and additionality. Every client's data lives in one place.
from app.core.config import settings
from app.core.abac import evaluate_four_eyes, Decision
from app.core.entropy_doctrine import (
    validate_causal_adjacency,
    package_entropy_score,
    EntropySource,
    ENTROPY_BY_TRANSITION,
)

DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/packages", tags=["development-packages"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS — matches GEX Bridge Document field definitions
# ═══════════════════════════════════════════════════════════════════════════

class PackageType(str, Enum):
    """
    Alt Bridge v0 §5 — cost-classification taxonomy.
    Maps to knowledge phases, not procurement categories (Hidalgo entropy reduction).
    Each type carries causal ordering: DEVEX → PRE_FEED → FEED → CAPEX.
    Capital-condition actors (insurer, lawyer, certifier, logistics) elevated to package types.
    """
    DEVEX           = "DEVEX"           # Site diligence, owner's engineer, market work
    PRE_FEED        = "PRE_FEED"        # BOD, licensor screening, grid/water/CO2 interfaces
    FEED            = "FEED"            # Licensed package, 3D model, HAZOP, tender prep
    DIRECT_CAPEX    = "DIRECT_CAPEX"    # Electrolysers, synthesis, tanks, civils, buildings
    INDIRECT_CAPEX  = "INDIRECT_CAPEX"  # Interconnection, utilities, shared infrastructure
    OWNER_COST      = "OWNER_COST"      # Project management, owner's engineer, administration
    CONTINGENCY     = "CONTINGENCY"     # Cost contingency per AACE methodology
    RESERVE         = "RESERVE"         # DSRA, liquidity reserve, cash controls
    INSURANCE       = "INSURANCE"       # CAR/EAR, DSU/BI, risk engineering
    LEGAL           = "LEGAL"           # Land title, step-in, security, financing CPs
    LOGISTICS       = "LOGISTICS"       # Port, storage, shipping, handling, route-to-market
    CERTIFICATION   = "CERTIFICATION"   # RFNBO/RED III, metering, PoS/GoO, audit plan


class PhaseRequired(str, Enum):
    FEL_1        = "FEL_1"
    FEL_2        = "FEL_2"
    FEED         = "FEED"
    FID          = "FID"
    CONSTRUCTION = "CONSTRUCTION"
    COD          = "COD"


class EstimateClass(str, Enum):
    """AACE RP 18R-97 estimate classification."""
    CLASS_5 = "CLASS_5"   # Concept screening — ±50%
    CLASS_4 = "CLASS_4"   # Feasibility — ±30%
    CLASS_3 = "CLASS_3"   # Budget / FID-support — ±20%  ← FID minimum
    CLASS_2 = "CLASS_2"   # Control — ±15%
    CLASS_1 = "CLASS_1"   # Check — ±10%


class RiskCategory(str, Enum):
    """Alt Bridge v0 §5 risk_removed — 12 categories matching capital-condition actors."""
    TECHNICAL     = "TECHNICAL"
    PERMITTING    = "PERMITTING"
    COST          = "COST"
    SCHEDULE      = "SCHEDULE"
    REVENUE       = "REVENUE"
    CERTIFICATION = "CERTIFICATION"
    EXECUTION     = "EXECUTION"
    SOVEREIGN     = "SOVEREIGN"
    LEGAL         = "LEGAL"
    FINANCIAL     = "FINANCIAL"
    INSURABILITY  = "INSURABILITY"   # Alt Bridge: insurer as capital-condition actor
    LOGISTICS     = "LOGISTICS"      # Alt Bridge: route-to-market as risk dimension


class CapitalSource(str, Enum):
    """Alt Bridge v0 §3.2 — 9 capital sources including insurance-backed facilities."""
    EQUITY            = "EQUITY"
    GRANT             = "GRANT"
    BRIDGE            = "BRIDGE"
    VENDOR_FINANCE    = "VENDOR_FINANCE"
    CONCESSIONAL      = "CONCESSIONAL"
    SENIOR_DEBT       = "SENIOR_DEBT"
    ECA               = "ECA"
    DSRA              = "DSRA"
    INSURANCE_BACKED  = "INSURANCE_BACKED"  # Alt Bridge: insurance-wrapped capital layer


class DrawdownMethod(str, Enum):
    """Alt Bridge v0 §7.3 — 8 drawdown methods matching facility mechanics."""
    MILESTONE         = "MILESTONE"      # EPC milestone certificates
    CERTIFICATE       = "CERTIFICATE"    # IE/certifier confirmation
    PERMIT            = "PERMIT"         # Regulatory approval trigger
    DATE              = "DATE"           # Time-based tranche schedule
    PROGRESS          = "PROGRESS"       # Measured % completion
    AWARD             = "AWARD"          # EPC/OEM/port contract award
    REIMBURSEMENT     = "REIMBURSEMENT"  # Proof of eligible spend (DFI/grant)
    RESERVE           = "RESERVE"        # DSRA/contingency/insurance reserve condition


class WorkflowState(str, Enum):
    """
    Package state machine — 12-state linear progression (Alt Bridge v0 §6).
    GEX enforces forward-only transitions (no rollback except via admin override).

    Entropy reduction per transition (Hidalgo doctrine):
      identified → scoped:      project-definition entropy reduced
      scoped → costed:          financial entropy reduced
      costed → evidenced:       credibility entropy reduced
      evidenced → eligible:     funding-pathway entropy reduced
      eligible → approved:      governance entropy reduced
      approved → committed:     capital-engagement entropy reduced
      committed → drawable:     release-condition entropy reduced
      drawable → drawn:         cash-movement entropy reduced
      drawn → verified:         use-of-funds entropy reduced
      verified → closed:        completion entropy reduced
      closed → propagated:      information-propagation entropy reduced
    """
    IDENTIFIED  = "identified"   # Package exists as named object
    SCOPED      = "scoped"       # Role in project is defined
    COSTED      = "costed"       # Cost basis exists (any estimate class)
    EVIDENCED   = "evidenced"    # Supporting documentation linked
    ELIGIBLE    = "eligible"     # System confirmed capital source eligibility
    APPROVED    = "approved"     # Internal governance accepted
    COMMITTED   = "committed"    # Capital committed
    DRAWABLE    = "drawable"     # Release conditions met
    DRAWN       = "drawn"        # Funds moved
    VERIFIED    = "verified"     # Use of funds independently evidenced
    CLOSED      = "closed"       # Package completed its funding purpose
    PROPAGATED  = "propagated"   # Downstream gates, metrics, views updated


# State machine: valid forward transitions only
VALID_TRANSITIONS = {
    WorkflowState.IDENTIFIED:  [WorkflowState.SCOPED],
    WorkflowState.SCOPED:      [WorkflowState.COSTED],
    WorkflowState.COSTED:      [WorkflowState.EVIDENCED],
    WorkflowState.EVIDENCED:   [WorkflowState.ELIGIBLE],
    WorkflowState.ELIGIBLE:    [WorkflowState.APPROVED],
    WorkflowState.APPROVED:    [WorkflowState.COMMITTED],
    WorkflowState.COMMITTED:   [WorkflowState.DRAWABLE],
    WorkflowState.DRAWABLE:    [WorkflowState.DRAWN],
    WorkflowState.DRAWN:       [WorkflowState.VERIFIED],
    WorkflowState.VERIFIED:    [WorkflowState.CLOSED],
    WorkflowState.CLOSED:      [WorkflowState.PROPAGATED],
    WorkflowState.PROPAGATED:  [],
}


# ═══════════════════════════════════════════════════════════════════════════
# CAPITAL STATUS — orthogonal to workflow (Hidalgo: two entropy dimensions)
# ═══════════════════════════════════════════════════════════════════════════

class CapitalStatus(str, Enum):
    """
    Capital engagement ladder (Alt Bridge v0 §7.1).
    Orthogonal to workflow_state — tracks capital-provider engagement,
    not package maturity. A package can be technically mature (EVIDENCED)
    but financially unengaged (NOT_ELIGIBLE), or vice versa.

    Hidalgo: separating these two dimensions preserves information that
    conflating them would destroy. workflow_state reduces knowledge entropy;
    capital_status reduces financial-commitment entropy.

    Sung: the package carries BOTH progressions as causally connected
    but independent hierarchies — not a flat merged list.
    """
    NOT_ELIGIBLE           = "NOT_ELIGIBLE"           # Source cannot rationally fund this
    THEORETICALLY_ELIGIBLE = "THEORETICALLY_ELIGIBLE" # Source type could fund, no provider engaged
    INDICATED              = "INDICATED"               # Provider interest, no binding commitment
    COMMITTED              = "COMMITTED"               # Funding legally committed
    DRAWABLE               = "DRAWABLE"                # CPs satisfied, release conditions met
    DRAWN                  = "DRAWN"                   # Cash has moved


# Capital status transitions — forward-only, independent of workflow_state
VALID_CAPITAL_TRANSITIONS = {
    CapitalStatus.NOT_ELIGIBLE:           [CapitalStatus.THEORETICALLY_ELIGIBLE],
    CapitalStatus.THEORETICALLY_ELIGIBLE: [CapitalStatus.INDICATED],
    CapitalStatus.INDICATED:              [CapitalStatus.COMMITTED],
    CapitalStatus.COMMITTED:              [CapitalStatus.DRAWABLE],
    CapitalStatus.DRAWABLE:               [CapitalStatus.DRAWN],
    CapitalStatus.DRAWN:                  [],
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class VerificationStateEnum(str, Enum):
    """Package-level verification state (mirrors verification.py states)."""
    UNVERIFIED = "UNVERIFIED"
    SUBMITTED  = "SUBMITTED"
    CONFIRMED  = "CONFIRMED"
    AUDITED    = "AUDITED"


class PackageCreate(BaseModel):
    project_id:            str
    package_name:          str = Field(..., min_length=3, max_length=200)
    package_type:          PackageType
    phase_required:        PhaseRequired
    discipline_owner:      str = Field(..., description="Actor ID — must map to project stakeholder")
    cost_amount:           float = Field(..., gt=0, description="Current P50 cost estimate in EUR")
    cost_p10:              Optional[float] = Field(None, description="Optimistic cost estimate EUR")
    cost_p90:              Optional[float] = Field(None, description="Pessimistic cost estimate EUR")
    estimate_class:        EstimateClass = EstimateClass.CLASS_5
    risk_removed:          list[RiskCategory] = Field(default_factory=list)
    capital_eligible:      list[CapitalSource] = Field(default_factory=list)
    unlock_condition:      list[str] = Field(
                               default_factory=list,
                               description="Evidence items or gate IDs that must be satisfied before drawdown"
                           )
    drawdown_method:       DrawdownMethod = DrawdownMethod.MILESTONE
    downstream_effect:     list[str] = Field(
                               default_factory=list,
                               description="package_ids or gate_ids this package unlocks"
                           )
    gex_gate:              Optional[str] = Field(None, description="Primary GEX gate e.g. G5, G10")
    evidence_refs:         list[str] = Field(default_factory=list, description="SHA-256 hashed evidence IDs")
    concessional_tranche_id: Optional[str] = Field(None, description="FK → DFI tranche in waterfall.py")
    debt_swap_id:          Optional[str] = Field(None, description="FK → SOVEREIGN_INSTRUMENTS (D4N swap)")
    notes:                 Optional[str] = None
    currency:              Optional[str] = Field("EUR", description="ISO 4217 currency code")
    fx_hedge_id:           Optional[str] = Field(None, description="FK to FX hedge instrument")
    aace_class_history:    list = Field(default_factory=list, description="JSON array of [{class, date, evidence_ref}]")
    personnel_breakdown:   list = Field(default_factory=list, description="JSON array of [{role, fte, daily_rate, months}]")
    verification_state:    VerificationStateEnum = VerificationStateEnum.UNVERIFIED
    capital_status:        CapitalStatus = Field(
                               CapitalStatus.NOT_ELIGIBLE,
                               description="Capital engagement ladder (orthogonal to workflow_state)"
                           )
    opex_effect:           Optional[float] = Field(
                               None,
                               description="Annual OPEX impact in base currency — connects CAPEX to LCOP/debt case"
                           )
    opex_effect_tag:       Optional[str] = Field(
                               None,
                               description="OPEX type: MAINTENANCE | INSURANCE | UTILITIES | LOGISTICS | PERSONNEL"
                           )

    @field_validator("capital_eligible")
    @classmethod
    def validate_eligibility_against_phase(cls, v, info):
        """
        Enforce capital eligibility rules per phase.
        Senior debt is never eligible before FID.
        """
        phase = info.data.get("phase_required")
        pre_fid_phases = {PhaseRequired.FEL_1, PhaseRequired.FEL_2, PhaseRequired.FEED}
        if phase in pre_fid_phases and CapitalSource.SENIOR_DEBT in v:
            raise ValueError(
                f"SENIOR_DEBT is not eligible for phase {phase}. "
                "Senior debt only eligible from FID onwards. "
                "Use EQUITY, GRANT, BRIDGE, or CONCESSIONAL for pre-FID packages."
            )
        return v

    @field_validator("risk_removed")
    @classmethod
    def require_risk_removed(cls, v):
        """Every package must state what uncertainty it removes."""
        if not v:
            raise ValueError(
                "risk_removed cannot be empty. "
                "Every package must declare at least one risk category it addresses. "
                "A package that removes no risk is an orphaned cost line."
            )
        return v


class PackageUpdate(BaseModel):
    package_name:         Optional[str] = None
    cost_amount:          Optional[float] = None
    cost_p10:             Optional[float] = None
    cost_p90:             Optional[float] = None
    estimate_class:       Optional[EstimateClass] = None
    risk_removed:         Optional[list[RiskCategory]] = None
    capital_eligible:     Optional[list[CapitalSource]] = None
    unlock_condition:     Optional[list[str]] = None
    drawdown_method:      Optional[DrawdownMethod] = None
    downstream_effect:    Optional[list[str]] = None
    gex_gate:             Optional[str] = None
    evidence_refs:        Optional[list[str]] = None
    concessional_tranche_id: Optional[str] = None
    debt_swap_id:         Optional[str] = None
    notes:                Optional[str] = None
    currency:             Optional[str] = None
    fx_hedge_id:          Optional[str] = None
    aace_class_history:   Optional[list] = None
    personnel_breakdown:  Optional[list] = None
    verification_state:   Optional[VerificationStateEnum] = None
    capital_status:       Optional[CapitalStatus] = None
    opex_effect:          Optional[float] = None
    opex_effect_tag:      Optional[str] = None
    changed_by:           str = Field(..., description="Actor ID making the change")


class WorkflowTransition(BaseModel):
    """
    Workflow state transition request.

    Four-eyes enforcement (R11):
      - actor_type: required — maps to ActorClass via ACTOR_CLASS_MAP
      - approved_by + approver_actor_type: required for dual-sign-off transitions
        (COMMITTED, DRAWN) — second person must differ from changed_by
    """
    new_state:            WorkflowState
    changed_by:           str = Field(..., description="Actor ID from JWT")
    actor_type:           str = Field(..., description="ActorType from JWT (e.g. PRODUCER, DFI)")
    justification:        str = Field(..., min_length=10, description="Required: reason for state transition")
    approved_by:          Optional[str] = Field(None, description="Second actor ID for dual-sign-off")
    approver_actor_type:  Optional[str] = Field(None, description="ActorType of the approver")


class CapitalStatusTransition(BaseModel):
    """
    Capital status transition — orthogonal to workflow_state.
    Also enforced by four-eyes (R11) at COMMITTED+ levels.
    """
    new_status:           CapitalStatus
    changed_by:           str = Field(..., description="Actor ID from JWT")
    actor_type:           str = Field(..., description="ActorType from JWT")
    justification:        str = Field(..., min_length=10, description="Reason for capital status change")
    approved_by:          Optional[str] = Field(None, description="Second actor for dual-sign-off")
    approver_actor_type:  Optional[str] = Field(None, description="ActorType of the approver")


class PackageResponse(BaseModel):
    package_id:            str
    project_id:            str
    package_name:          str
    package_type:          str
    phase_required:        str
    discipline_owner:      str
    cost_amount:           float
    cost_p10:              Optional[float]
    cost_p90:              Optional[float]
    estimate_class:        str
    risk_removed:          list[str]
    capital_eligible:      list[str]
    unlock_condition:      list[str]
    drawdown_method:       str
    downstream_effect:     list[str]
    gex_gate:              Optional[str]
    evidence_refs:         list[str]
    workflow_state:        str
    concessional_tranche_id: Optional[str]
    debt_swap_id:          Optional[str]
    notes:                 Optional[str]
    currency:              Optional[str]
    fx_hedge_id:           Optional[str]
    aace_class_history:    list
    personnel_breakdown:   list
    verification_state:    str
    capital_status:        str
    opex_effect:           Optional[float]
    opex_effect_tag:       Optional[str]
    version:               int
    last_changed_by:       str
    created_at:            str
    updated_at:            str
    content_hash:          str


class ProjectPackageSummary(BaseModel):
    """
    Aggregate view for Finance workspace and pre_cod_metrics.
    Now includes capital_status breakdown (Hidalgo: two-axis entropy view)
    and opex_effect_total (Sung: CAPEX→OPEX causal link).
    """
    project_id:             str
    total_packages:         int
    total_capex_p50_eur:    float
    by_phase:               dict  # phase → total cost
    by_state:               dict  # workflow_state → count
    by_capital_status:      dict  # capital_status → count + total cost
    by_capital_source:      dict  # capital_source → total cost
    eligible_for_drawdown:  int   # packages in DRAWABLE or DRAWN state
    blocked_packages:       int   # packages stuck in IDENTIFIED/SCOPED without evidence
    concessional_linked:    int   # packages with concessional_tranche_id
    sovereign_linked:       int   # packages with debt_swap_id
    fid_readiness_pct:      float # % of FID-critical packages at CLASS_3+
    opex_effect_total:      float # Total annual OPEX impact across all packages
    estimate_class_breakdown: dict


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

def get_db():
    """
    ALIGN: Replace with your actual db dependency from core/db.py.
    Pattern matches tokens_sqlite.py / contracts_sqlite.py.

    check_same_thread=False: FastAPI runs sync endpoints in a threadpool, and a
    single request's dependency generator and endpoint body can execute on
    different worker threads. Without this, summary/list calls intermittently
    raise "SQLite objects created in a thread can only be used in that same
    thread". The connection is still per-request (not shared concurrently).

    Slice-5 connection — SQLite or PostgreSQL by configuration
    (CAPITAL_DB_BACKEND). The append-only event chain is backend-agnostic: the
    digest is computed in Python over row values, so it reproduces either side.
    """
    from app.core.db_backend import capital_connection, capital_is_postgres

    conn = capital_connection()
    if not capital_is_postgres():
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Create DEVELOPMENT_PACKAGES table.
    Call from app/main.py startup alongside other init_db() calls.

    UPDM target (PostgreSQL migration — Vademecum task 2.11):
      - Add FOREIGN KEY (project_id) REFERENCES projects(project_id)
      - Add FOREIGN KEY (concessional_tranche_id) REFERENCES concessional_tranches(tranche_id)
      - Add FOREIGN KEY (debt_swap_id) REFERENCES sovereign_instruments(instrument_id)
      - Add row-level security policy for ABAC persona filtering
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS development_packages (
            package_id             TEXT PRIMARY KEY,
            project_id             TEXT NOT NULL,
            package_name           TEXT NOT NULL,
            package_type           TEXT NOT NULL,
            phase_required         TEXT NOT NULL,
            discipline_owner       TEXT NOT NULL,
            cost_amount            REAL NOT NULL,
            cost_p10               REAL,
            cost_p90               REAL,
            estimate_class         TEXT NOT NULL DEFAULT 'CLASS_5',
            risk_removed           TEXT NOT NULL DEFAULT '[]',
            capital_eligible       TEXT NOT NULL DEFAULT '[]',
            unlock_condition       TEXT NOT NULL DEFAULT '[]',
            drawdown_method        TEXT NOT NULL DEFAULT 'MILESTONE',
            downstream_effect      TEXT NOT NULL DEFAULT '[]',
            gex_gate               TEXT,
            evidence_refs          TEXT NOT NULL DEFAULT '[]',
            workflow_state         TEXT NOT NULL DEFAULT 'identified',
            concessional_tranche_id TEXT,
            debt_swap_id           TEXT,
            notes                  TEXT,
            currency               TEXT DEFAULT 'EUR',
            fx_hedge_id            TEXT,
            aace_class_history     TEXT NOT NULL DEFAULT '[]',
            personnel_breakdown    TEXT NOT NULL DEFAULT '[]',
            verification_state     TEXT NOT NULL DEFAULT 'UNVERIFIED',
            capital_status         TEXT NOT NULL DEFAULT 'NOT_ELIGIBLE',
            opex_effect            REAL,
            opex_effect_tag        TEXT,
            version                INTEGER NOT NULL DEFAULT 1,
            last_changed_by        TEXT NOT NULL,
            content_hash           TEXT NOT NULL,
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        )
    """)
    # Index for common query patterns
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_project ON development_packages(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_state ON development_packages(workflow_state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_phase ON development_packages(phase_required)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_gate ON development_packages(gex_gate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_capital_status ON development_packages(capital_status)")

    # Audit table for all package changes — append-only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS development_package_events (
            event_id       TEXT PRIMARY KEY,
            package_id     TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dpe_package ON development_package_events(package_id)")

    # Evidence documents attached to packages — "evidence without a document is
    # a claim". Each upload is content-addressed by sha256 and appended to the
    # package's evidence_refs (which gates the EVIDENCED transition).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_evidence (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id    TEXT NOT NULL,
            project_id    TEXT NOT NULL,
            title         TEXT,
            filename      TEXT NOT NULL,
            sha256        TEXT NOT NULL,
            size_bytes    INTEGER NOT NULL,
            stored_path   TEXT NOT NULL,
            uploaded_by   TEXT NOT NULL,
            uploaded_at   TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pe_package ON package_evidence(package_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_package(data: dict) -> str:
    """SHA-256 of package content — same chain pattern as bankability_engine.py."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_event(conn, package_id: str, project_id: str, event_type: str,
               changed_by: str, field: str = None, old_val=None,
               new_val=None, justification: str = None):
    """
    Append-only event log. Feeds Redis Streams event bus when implemented
    (Vademecum task 2.12 — event: package.state_changed, package.updated).
    """
    now = _now()
    # Get previous hash for chain
    prev = conn.execute(
        "SELECT event_hash FROM development_package_events "
        "WHERE package_id=? ORDER BY created_at DESC LIMIT 1",
        (package_id,)
    ).fetchone()
    prev_hash = prev["event_hash"] if prev else None

    payload = {
        "package_id": package_id,
        "event_type": event_type,
        "field": field,
        "new_value": new_val,
        "actor": changed_by,
        "timestamp": now,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    conn.execute("""
        INSERT INTO development_package_events
        (event_id, package_id, project_id, event_type, field_changed,
         old_value, new_value, changed_by, justification, event_hash, prev_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), package_id, project_id, event_type,
        field, str(old_val) if old_val is not None else None,
        str(new_val) if new_val is not None else None,
        changed_by, justification, event_hash, prev_hash, now
    ))


def _row_to_response(row) -> dict:
    return {
        "package_id":             row["package_id"],
        "project_id":             row["project_id"],
        "package_name":           row["package_name"],
        "package_type":           row["package_type"],
        "phase_required":         row["phase_required"],
        "discipline_owner":       row["discipline_owner"],
        "cost_amount":            row["cost_amount"],
        "cost_p10":               row["cost_p10"],
        "cost_p90":               row["cost_p90"],
        "estimate_class":         row["estimate_class"],
        "risk_removed":           json.loads(row["risk_removed"]),
        "capital_eligible":       json.loads(row["capital_eligible"]),
        "unlock_condition":       json.loads(row["unlock_condition"]),
        "drawdown_method":        row["drawdown_method"],
        "downstream_effect":      json.loads(row["downstream_effect"]),
        "gex_gate":               row["gex_gate"],
        "evidence_refs":          json.loads(row["evidence_refs"]),
        "workflow_state":         row["workflow_state"],
        "concessional_tranche_id": row["concessional_tranche_id"],
        "debt_swap_id":           row["debt_swap_id"],
        "notes":                  row["notes"],
        "currency":               row["currency"],
        "fx_hedge_id":            row["fx_hedge_id"],
        "aace_class_history":     json.loads(row["aace_class_history"]),
        "personnel_breakdown":    json.loads(row["personnel_breakdown"]),
        "verification_state":     row["verification_state"],
        "capital_status":         row["capital_status"],
        "opex_effect":            row["opex_effect"],
        "opex_effect_tag":        row["opex_effect_tag"],
        "version":                row["version"],
        "last_changed_by":        row["last_changed_by"],
        "created_at":             row["created_at"],
        "updated_at":             row["updated_at"],
        "content_hash":           row["content_hash"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", response_model=PackageResponse, status_code=201)
def create_package(pkg: PackageCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    Create a Development Package Object.

    GEX rule: Every cost line must be attached to a named package with at least
    one risk_removed category. Packages without risk_removed are rejected — they
    are orphaned cost lines that provide no de-risking value.

    Fires event: package.created → Redis Streams (when event bus active).
    """
    package_id = str(uuid.uuid4())
    now = _now()

    content = {
        "package_id": package_id,
        "project_id": pkg.project_id,
        "package_name": pkg.package_name,
        "package_type": pkg.package_type,
        "cost_amount": pkg.cost_amount,
        "estimate_class": pkg.estimate_class,
        "created_at": now,
    }
    content_hash = _hash_package(content)

    # Seed aace_class_history with initial estimate_class
    initial_history = pkg.aace_class_history or []
    if not initial_history:
        initial_history = [{"class": pkg.estimate_class.value, "date": now, "evidence_ref": None}]

    db.execute("""
        INSERT INTO development_packages
        (package_id, project_id, package_name, package_type, phase_required,
         discipline_owner, cost_amount, cost_p10, cost_p90, estimate_class,
         risk_removed, capital_eligible, unlock_condition, drawdown_method,
         downstream_effect, gex_gate, evidence_refs, workflow_state,
         concessional_tranche_id, debt_swap_id, notes,
         currency, fx_hedge_id, aace_class_history, personnel_breakdown,
         verification_state, capital_status, opex_effect, opex_effect_tag,
         version, last_changed_by, content_hash, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        package_id, pkg.project_id, pkg.package_name, pkg.package_type,
        pkg.phase_required, pkg.discipline_owner, pkg.cost_amount,
        pkg.cost_p10, pkg.cost_p90, pkg.estimate_class,
        json.dumps([r.value for r in pkg.risk_removed]),
        json.dumps([c.value for c in pkg.capital_eligible]),
        json.dumps(pkg.unlock_condition),
        pkg.drawdown_method,
        json.dumps(pkg.downstream_effect),
        pkg.gex_gate,
        json.dumps(pkg.evidence_refs),
        WorkflowState.IDENTIFIED.value,
        pkg.concessional_tranche_id,
        pkg.debt_swap_id,
        pkg.notes,
        pkg.currency,
        pkg.fx_hedge_id,
        json.dumps(initial_history),
        json.dumps(pkg.personnel_breakdown),
        pkg.verification_state.value,
        pkg.capital_status.value,
        pkg.opex_effect,
        pkg.opex_effect_tag,
        1, pkg.discipline_owner, content_hash, now, now
    ))
    _log_event(db, package_id, pkg.project_id, "package.created",
               pkg.discipline_owner, new_val=pkg.package_name)
    db.commit()

    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    return _row_to_response(row)


@router.get("/{package_id}", response_model=PackageResponse)
def get_package(package_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")
    return _row_to_response(row)


@router.get("/project/{project_id}", response_model=list[PackageResponse])
def list_packages(
    project_id: str,
    phase: Optional[PhaseRequired] = Query(None),
    state: Optional[WorkflowState] = Query(None),
    gate: Optional[str] = Query(None),
    capital_source: Optional[CapitalSource] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    List all packages for a project with optional filters.

    ABAC alignment (abac.py):
      - PRODUCER sees all packages for own project
      - FINANCE sees packages where capital_eligible contains SENIOR_DEBT, CONCESSIONAL, ECA
      - DFI sees packages where capital_eligible contains CONCESSIONAL
      - REGULATOR sees packages linked to G2, G9 gates only
    Add persona filtering here when abac.py is aligned.
    """
    query = "SELECT * FROM development_packages WHERE project_id=?"
    params: list = [project_id]

    if phase:
        query += " AND phase_required=?"; params.append(phase.value)
    if state:
        query += " AND workflow_state=?"; params.append(state.value)
    if gate:
        query += " AND gex_gate=?"; params.append(gate)

    rows = db.execute(query, params).fetchall()

    if capital_source:
        # Filter in Python — SQLite JSON doesn't support LIKE cleanly
        rows = [r for r in rows if capital_source.value in json.loads(r["capital_eligible"])]

    return [_row_to_response(r) for r in rows]


@router.patch("/{package_id}", response_model=PackageResponse)
def update_package(
    package_id: str,
    update: PackageUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Update package fields. Every change is logged to the event chain.
    Version is incremented on every save — immutable history.

    GEX rule: cost_amount changes require estimate_class to be explicitly set.
    Lenders see version history — silent changes are not permitted.
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")

    now = _now()
    fields = update.model_dump(exclude_none=True, exclude={"changed_by"})

    # Auto-append to aace_class_history when estimate_class changes
    if "estimate_class" in fields:
        old_class = row["estimate_class"]
        new_class = fields["estimate_class"]
        new_class_val = new_class.value if hasattr(new_class, "value") else new_class
        if old_class != new_class_val:
            existing_history = json.loads(row["aace_class_history"])
            existing_history.append({
                "class": new_class_val,
                "date": now,
                "evidence_ref": None,
            })
            fields["aace_class_history"] = existing_history

    for field, new_val in fields.items():
        old_val = row[field] if field in row.keys() else None
        # Serialise lists for storage
        stored = json.dumps(new_val) if isinstance(new_val, list) else new_val
        # Handle enum values
        if hasattr(stored, "value"):
            stored = stored.value
        db.execute(
            f"UPDATE development_packages SET {field}=?, version=version+1, "
            "last_changed_by=?, updated_at=? WHERE package_id=?",
            (stored, update.changed_by, now, package_id)
        )
        _log_event(db, package_id, row["project_id"], "package.updated",
                   update.changed_by, field=field,
                   old_val=old_val, new_val=new_val)

    # Recompute content hash
    updated = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    new_hash = _hash_package(dict(updated))
    db.execute("UPDATE development_packages SET content_hash=? WHERE package_id=?",
               (new_hash, package_id))
    db.commit()

    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    return _row_to_response(row)


@router.post("/{package_id}/transition", response_model=PackageResponse)
def transition_state(
    package_id: str,
    transition: WorkflowTransition,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance package workflow state.

    Rules enforced:
      - Only forward transitions (VALID_TRANSITIONS)
      - EVIDENCED requires at least one evidence_ref
      - ELIGIBLE requires non-empty capital_eligible
      - DRAWABLE requires all unlock_conditions to be satisfied
        (checked against evidence_refs — full enforcement needs bankability_engine.py)
      - Every transition requires a written justification

    Fires event: package.state_changed → Redis Streams (when event bus active).
    The event bus then triggers bankability re-evaluation and notification engine.
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")

    current = WorkflowState(row["workflow_state"])
    new_state = transition.new_state

    if new_state not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(400,
            f"Invalid transition: {current.value} → {new_state.value}. "
            f"Valid next states: {[s.value for s in VALID_TRANSITIONS.get(current, [])]}"
        )

    # ── R11: FOUR-EYES ENFORCEMENT ──────────────────────────────────
    # Evaluate before state-specific guards — no point checking evidence
    # if the actor is not authorized to make this transition at all.
    four_eyes = evaluate_four_eyes(
        target_state=new_state.value,
        actor_id=transition.changed_by,
        actor_type_str=transition.actor_type,
        package_row=dict(row),
        approver_id=transition.approved_by,
        approver_type_str=transition.approver_actor_type,
    )
    if four_eyes.decision == Decision.DENY:
        raise HTTPException(403, four_eyes.denial_reason)

    # Log the entropy dimension being reduced (Hidalgo doctrine)
    transition_key = f"{current.value} → {new_state.value}"
    entropy_entry = ENTROPY_BY_TRANSITION.get(transition_key)

    # State-specific guards
    if new_state == WorkflowState.EVIDENCED:
        evidence = json.loads(row["evidence_refs"])
        if not evidence:
            raise HTTPException(400,
                "Cannot transition to EVIDENCED: no evidence_refs attached. "
                "Upload evidence via the evidence endpoint before advancing."
            )

    if new_state == WorkflowState.ELIGIBLE:
        eligible = json.loads(row["capital_eligible"])
        if not eligible:
            raise HTTPException(400,
                "Cannot transition to ELIGIBLE: capital_eligible is empty. "
                "Define which capital sources can fund this package."
            )

    if new_state == WorkflowState.DRAWABLE:
        unlock = json.loads(row["unlock_condition"])
        evidence = json.loads(row["evidence_refs"])
        if unlock and not evidence:
            raise HTTPException(400,
                "Cannot transition to DRAWABLE: unlock_condition requires evidence "
                "but no evidence_refs are attached. Satisfy all conditions before drawdown."
            )

    if new_state == WorkflowState.VERIFIED:
        # Use-of-funds entropy reduction: verification_state must show independent check
        ver_state = row["verification_state"]
        if ver_state not in ("CONFIRMED", "AUDITED"):
            raise HTTPException(400,
                f"Cannot transition to VERIFIED: verification_state is {ver_state}. "
                "Requires CONFIRMED or AUDITED — independent evidence of funds use."
            )

    if new_state == WorkflowState.PROPAGATED:
        # Information-propagation entropy: downstream effects must be declared
        downstream = json.loads(row["downstream_effect"])
        if not downstream:
            raise HTTPException(400,
                "Cannot transition to PROPAGATED: downstream_effect is empty. "
                "Declare which gates, metrics, or packages this completion updates."
            )

    now = _now()
    db.execute("""
        UPDATE development_packages
        SET workflow_state=?, version=version+1, last_changed_by=?, updated_at=?
        WHERE package_id=?
    """, (new_state.value, transition.changed_by, now, package_id))

    # Build justification with entropy annotation
    entropy_note = ""
    if entropy_entry:
        entropy_note = f" [Entropy reduced: {entropy_entry.source.value}]"

    _log_event(
        db, package_id, row["project_id"],
        "package.state_changed",
        transition.changed_by,
        field="workflow_state",
        old_val=current.value,
        new_val=new_state.value,
        justification=transition.justification + entropy_note
    )

    # Log four-eyes actors for audit trail
    if transition.approved_by:
        _log_event(
            db, package_id, row["project_id"],
            "package.four_eyes_approval",
            transition.approved_by,
            field="workflow_state",
            old_val=current.value,
            new_val=new_state.value,
            justification=f"Dual sign-off by {transition.approver_actor_type}"
        )

    db.commit()

    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    return _row_to_response(row)


@router.get("/project/{project_id}/summary", response_model=ProjectPackageSummary)
def project_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Aggregate package view for:
      - Finance workspace → FinanceBankabilityView (pre-G10 capital eligibility)
      - Pre-COD metrics engine (pre_cod_metrics.py consumes this)
      - Executive workspace → portfolio capital overview
      - DFI sub-persona → concessional exposure per project

    fid_readiness_pct: % of packages in FID/Construction phase
    that have reached CLASS_3 estimate maturity — lender requirement.
    """
    rows = db.execute(
        "SELECT * FROM development_packages WHERE project_id=?", (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No packages found for project {project_id}")

    total_capex = sum(r["cost_amount"] for r in rows)

    by_phase: dict = {}
    for r in rows:
        by_phase[r["phase_required"]] = by_phase.get(r["phase_required"], 0) + r["cost_amount"]

    by_state: dict = {}
    for r in rows:
        by_state[r["workflow_state"]] = by_state.get(r["workflow_state"], 0) + 1

    by_capital: dict = {}
    for r in rows:
        for src in json.loads(r["capital_eligible"]):
            by_capital[src] = by_capital.get(src, 0) + r["cost_amount"]

    eligible_drawdown = sum(
        1 for r in rows if r["workflow_state"] in ("drawable", "drawn", "verified")
    )
    blocked = sum(
        1 for r in rows if r["workflow_state"] in ("identified", "scoped")
    )
    concessional_linked = sum(
        1 for r in rows if r["concessional_tranche_id"]
    )
    sovereign_linked = sum(
        1 for r in rows if r["debt_swap_id"]
    )

    # FID readiness: FID+Construction packages at CLASS_3 or better
    fid_phases = {"FID", "CONSTRUCTION"}
    fid_pkgs = [r for r in rows if r["phase_required"] in fid_phases]
    fid_class3_plus = {"CLASS_3", "CLASS_2", "CLASS_1"}
    fid_ready = sum(1 for r in fid_pkgs if r["estimate_class"] in fid_class3_plus)
    fid_readiness_pct = (fid_ready / len(fid_pkgs) * 100) if fid_pkgs else 0.0

    # Capital status breakdown — two-axis entropy view (Hidalgo)
    by_cap_status: dict = {}
    for r in rows:
        cs = r["capital_status"]
        if cs not in by_cap_status:
            by_cap_status[cs] = {"count": 0, "total_cost": 0.0}
        by_cap_status[cs]["count"] += 1
        by_cap_status[cs]["total_cost"] += r["cost_amount"]

    # OPEX effect — causal downstream (Sung)
    opex_total = sum(r["opex_effect"] or 0.0 for r in rows)

    class_breakdown: dict = {}
    for r in rows:
        class_breakdown[r["estimate_class"]] = class_breakdown.get(r["estimate_class"], 0) + 1

    return ProjectPackageSummary(
        project_id=project_id,
        total_packages=len(rows),
        total_capex_p50_eur=total_capex,
        by_phase=by_phase,
        by_state=by_state,
        by_capital_status=by_cap_status,
        by_capital_source=by_capital,
        eligible_for_drawdown=eligible_drawdown,
        blocked_packages=blocked,
        concessional_linked=concessional_linked,
        sovereign_linked=sovereign_linked,
        fid_readiness_pct=round(fid_readiness_pct, 1),
        opex_effect_total=round(opex_total, 2),
        estimate_class_breakdown=class_breakdown,
    )


@router.get("/{package_id}/events")
def get_package_events(package_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Full immutable event history for a package — audit trail for lenders."""
    rows = db.execute(
        "SELECT * FROM development_package_events WHERE package_id=? ORDER BY created_at ASC",
        (package_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGE EVIDENCE — "evidence without a document is a claim"
# Uploading a document content-addresses it (sha256), records it, and appends
# the hash to evidence_refs — which is what the EVIDENCED transition checks.
# ═══════════════════════════════════════════════════════════════════════════

PACKAGE_DOCS_DIR = os.getenv("GEX_PACKAGE_DOCS_DIR", "data/package_docs")
_MAX_DOC_BYTES = 25 * 1024 * 1024  # 25 MB


def _actor_email(authorization: str | None) -> str:
    """Best-effort actor identity from the bearer token (auth is enforced upstream)."""
    if authorization and authorization.lower().startswith("bearer "):
        try:
            from app.core.auth import get_user_payload_from_token
            payload = get_user_payload_from_token(authorization.split(" ", 1)[1].strip())
            return payload.get("email", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


@router.post("/{package_id}/evidence", response_model=PackageResponse, status_code=201)
async def upload_package_evidence(
    package_id: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    db: sqlite3.Connection = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """
    Attach a document to a package. Stores the file with its sha256, records it
    in package_evidence, appends the hash to evidence_refs (dedup), and logs the
    event. After at least one document is attached, the package can transition
    IDENTIFIED…COSTED → EVIDENCED.
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(422, "Empty file")
    if len(content) > _MAX_DOC_BYTES:
        raise HTTPException(413, "Document exceeds 25 MB limit")

    sha = hashlib.sha256(content).hexdigest()
    safe_name = os.path.basename(file.filename or "document.bin")
    dest_dir = Path(PACKAGE_DOCS_DIR) / package_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{sha[:12]}_{safe_name}"
    dest.write_bytes(content)

    actor = _actor_email(authorization)
    now = _now()
    db.execute(
        "INSERT INTO package_evidence (package_id, project_id, title, filename, sha256, size_bytes, stored_path, uploaded_by, uploaded_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (package_id, row["project_id"], title.strip() or safe_name, safe_name, sha, len(content), str(dest), actor, now),
    )

    # Append the hash to evidence_refs (dedup) — this is what gates EVIDENCED.
    refs = json.loads(row["evidence_refs"])
    if sha not in refs:
        refs.append(sha)
        db.execute(
            "UPDATE development_packages SET evidence_refs=?, version=version+1, last_changed_by=?, updated_at=? WHERE package_id=?",
            (json.dumps(refs), actor, now, package_id),
        )
    _log_event(db, package_id, row["project_id"], "package.evidence_added", actor,
               field="evidence_refs", new_val=f"{title.strip() or safe_name} ({sha[:12]}…)")
    db.commit()

    updated = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    return _row_to_response(updated)


@router.get("/{package_id}/evidence")
def list_package_evidence(package_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Documents attached to a package (metadata + content hashes)."""
    rows = db.execute(
        "SELECT title, filename, sha256, size_bytes, uploaded_by, uploaded_at "
        "FROM package_evidence WHERE package_id=? ORDER BY id DESC",
        (package_id,),
    ).fetchall()
    return {"package_id": package_id, "documents": [dict(r) for r in rows]}


@router.delete("/{package_id}")
def delete_package(package_id: str, deleted_by: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Soft-delete: sets workflow_state to CLOSED and logs the event.
    Hard deletes are never permitted — packages are part of the evidence chain.
    ALIGN: Add ABAC check — only PRODUCER or EXECUTIVE persona can close packages.
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")
    if row["workflow_state"] in ("drawn", "verified", "closed", "propagated"):
        raise HTTPException(400, "Cannot close a package already in DRAWN, VERIFIED, CLOSED or PROPAGATED state")

    now = _now()
    db.execute("""
        UPDATE development_packages
        SET workflow_state='closed', last_changed_by=?, updated_at=?, version=version+1
        WHERE package_id=?
    """, (deleted_by, now, package_id))
    _log_event(db, package_id, row["project_id"], "package.closed",
               deleted_by, field="workflow_state",
               old_val=row["workflow_state"], new_val="closed",
               justification="Administrative closure")
    db.commit()
    return {"status": "closed", "package_id": package_id}


# ═══════════════════════════════════════════════════════════════════════════
# CAPITAL STATUS TRANSITION — orthogonal axis (Hidalgo: two entropy ladders)
# ═══════════════════════════════════════════════════════════════════════════

# Four-eyes rules for capital_status transitions (parallels workflow rules)
# Capital transitions above INDICATED require institutional sign-off
CAPITAL_FOUR_EYES: dict[str, dict] = {
    "THEORETICALLY_ELIGIBLE": {"required_class": None, "four_eyes": False},
    "INDICATED":              {"required_class": None, "four_eyes": False},
    "COMMITTED":              {"required_class": "RISK_ABSORBER",   "four_eyes": True},
    "DRAWABLE":               {"required_class": "CAPITAL_RELEASER","four_eyes": True},
    "DRAWN":                  {"required_class": "CAPITAL_RELEASER","four_eyes": True, "dual": True},
}


@router.post("/{package_id}/capital-transition", response_model=PackageResponse)
def transition_capital_status(
    package_id: str,
    transition: CapitalStatusTransition,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Advance capital_status independently of workflow_state.

    Hidalgo: workflow_state reduces knowledge entropy; capital_status reduces
    financial-commitment entropy. These are ORTHOGONAL ladders — a package
    can be EVIDENCED (knowledge-mature) but NOT_ELIGIBLE (no capital engaged).

    Four-eyes enforcement:
      - COMMITTED+ requires RISK_ABSORBER or CAPITAL_RELEASER class
      - DRAWN requires dual sign-off
      - Identity check: changed_by ≠ last_changed_by at COMMITTED+
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")

    current = CapitalStatus(row["capital_status"])
    new_status = transition.new_status

    if new_status not in VALID_CAPITAL_TRANSITIONS.get(current, []):
        raise HTTPException(400,
            f"Invalid capital transition: {current.value} → {new_status.value}. "
            f"Valid next: {[s.value for s in VALID_CAPITAL_TRANSITIONS.get(current, [])]}"
        )

    # Four-eyes check for capital transitions
    cap_rule = CAPITAL_FOUR_EYES.get(new_status.value, {})
    if cap_rule.get("four_eyes"):
        # Identity check: must differ from last_changed_by
        if transition.changed_by == row["last_changed_by"]:
            raise HTTPException(403,
                f"Four-eyes violation: actor {transition.changed_by} cannot advance "
                f"capital_status to {new_status.value} — same as last_changed_by. "
                f"A different person must perform this action."
            )

    if cap_rule.get("required_class"):
        # Use the full evaluate_four_eyes logic via a mapped workflow state
        # Capital COMMITTED maps to workflow COMMITTED four-eyes rules
        mapped_state = new_status.value.lower()
        if mapped_state in ("not_eligible", "theoretically_eligible", "indicated"):
            mapped_state = "scoped"  # No four-eyes needed
        elif mapped_state == "committed":
            mapped_state = "committed"
        elif mapped_state == "drawable":
            mapped_state = "drawable"
        elif mapped_state == "drawn":
            mapped_state = "drawn"

        four_eyes = evaluate_four_eyes(
            target_state=mapped_state,
            actor_id=transition.changed_by,
            actor_type_str=transition.actor_type,
            package_row=dict(row),
            approver_id=transition.approved_by,
            approver_type_str=transition.approver_actor_type,
        )
        if four_eyes.decision == Decision.DENY:
            raise HTTPException(403, four_eyes.denial_reason)

    now = _now()
    db.execute("""
        UPDATE development_packages
        SET capital_status=?, version=version+1, last_changed_by=?, updated_at=?
        WHERE package_id=?
    """, (new_status.value, transition.changed_by, now, package_id))

    _log_event(
        db, package_id, row["project_id"],
        "package.capital_status_changed",
        transition.changed_by,
        field="capital_status",
        old_val=current.value,
        new_val=new_status.value,
        justification=transition.justification
    )

    if transition.approved_by:
        _log_event(
            db, package_id, row["project_id"],
            "package.capital_four_eyes_approval",
            transition.approved_by,
            field="capital_status",
            old_val=current.value,
            new_val=new_status.value,
            justification=f"Dual sign-off by {transition.approver_actor_type}"
        )

    db.commit()

    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    return _row_to_response(row)


# ═══════════════════════════════════════════════════════════════════════════
# ENTROPY + CAUSAL SCORING (Hidalgo/Sung diagnostic endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{package_id}/entropy-score")
def get_entropy_score(package_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Hidalgo entropy-reduction score for a single package.
    Sung causal-compression completeness check.

    Used by:
      - Finance workspace: per-package entropy contribution
      - Executive dashboard: entropy heatmap
      - Pre-COD metrics: portfolio entropy weighting
    """
    row = db.execute("SELECT * FROM development_packages WHERE package_id=?", (package_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Package {package_id} not found")

    pkg_dict = dict(row)
    # Parse JSON fields for causal validation
    for field in ("risk_removed", "capital_eligible", "unlock_condition",
                  "downstream_effect", "evidence_refs"):
        if isinstance(pkg_dict.get(field), str):
            pkg_dict[field] = json.loads(pkg_dict[field])

    score = package_entropy_score(pkg_dict)
    causal = validate_causal_adjacency(pkg_dict)

    return {
        "package_id": package_id,
        "entropy": score,
        "causal_adjacency": {
            "is_valid": causal.is_valid,
            "score": causal.score,
            "missing_dimensions": causal.missing_dimensions,
            "detail": causal.detail,
        },
    }


@router.get("/project/{project_id}/entropy-summary")
def project_entropy_summary(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Portfolio-level entropy reduction summary.

    Returns per-package and aggregate entropy scores.
    The aggregate score represents how much total uncertainty
    the project has reduced across all packages (Hidalgo §2.1).
    """
    rows = db.execute(
        "SELECT * FROM development_packages WHERE project_id=?", (project_id,)
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"No packages found for project {project_id}")

    package_scores = []
    total_score = 0.0
    total_causal = 0.0
    all_resolved = set()

    for r in rows:
        pkg_dict = dict(r)
        for field in ("risk_removed", "capital_eligible", "unlock_condition",
                      "downstream_effect", "evidence_refs"):
            if isinstance(pkg_dict.get(field), str):
                pkg_dict[field] = json.loads(pkg_dict[field])

        score = package_entropy_score(pkg_dict)
        causal = validate_causal_adjacency(pkg_dict)

        package_scores.append({
            "package_id": r["package_id"],
            "package_name": r["package_name"],
            "overall_score": score["overall_score"],
            "causal_completeness": causal.score,
            "workflow_state": r["workflow_state"],
            "capital_status": r["capital_status"],
            "resolved_dimensions": score["entropy_dimensions_resolved"],
        })
        total_score += score["overall_score"]
        total_causal += causal.score
        all_resolved.update(score["entropy_dimensions_resolved"])

    n = len(rows)
    return {
        "project_id": project_id,
        "total_packages": n,
        "aggregate_entropy_score": round(total_score / n, 3) if n else 0.0,
        "aggregate_causal_completeness": round(total_causal / n, 3) if n else 0.0,
        "resolved_entropy_dimensions": sorted(all_resolved),
        "unresolved_entropy_dimensions": sorted(
            set(e.value for e in EntropySource) - all_resolved
        ),
        "packages": package_scores,
    }
