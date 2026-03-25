-- ═══════════════════════════════════════════════════════════════════════════════
-- GEX Bankability Evidence Schema
-- Location: gex-platform-enhanced/backend/app/db/
-- Run AFTER existing schema. Adds evidence tracking + bankability snapshots.
-- ═══════════════════════════════════════════════════════════════════════════════

-- Evidence items: one row per (project, evidence_key) pair.
-- Updated by stakeholders via the platform UI.
-- On every status change → call bankability engine for re-evaluation.
CREATE TABLE IF NOT EXISTS bankability_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    evidence_key    TEXT NOT NULL,           -- e.g. "land_option_or_lease_executed"
    gate_id         TEXT NOT NULL,           -- e.g. "G0_SITE_RIGHTS"
    status          TEXT NOT NULL DEFAULT 'NOT_STARTED',
                    -- NOT_STARTED | IN_PROGRESS | SUBMITTED | UNDER_REVIEW | VERIFIED | REJECTED | EXPIRED
    submitted_by    TEXT,                    -- user who uploaded/submitted
    verified_by     TEXT,                    -- user who verified/approved
    submitted_at    TIMESTAMP,
    verified_at     TIMESTAMP,
    document_hash   TEXT,                    -- SHA-256 of uploaded document
    document_url    TEXT,                    -- link to stored document
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, evidence_key)
);

CREATE INDEX IF NOT EXISTS idx_evidence_project ON bankability_evidence(project_id);
CREATE INDEX IF NOT EXISTS idx_evidence_gate ON bankability_evidence(gate_id);
CREATE INDEX IF NOT EXISTS idx_evidence_status ON bankability_evidence(status);


-- Bankability snapshots: stored after each engine evaluation.
-- Immutable audit trail of state progression.
CREATE TABLE IF NOT EXISTS bankability_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    evaluated_at        TIMESTAMP NOT NULL,
    current_state       TEXT NOT NULL,       -- BankabilityState enum value
    previous_state      TEXT,
    overall_completion_pct REAL NOT NULL,
    total_evidence      INTEGER NOT NULL,
    total_verified      INTEGER NOT NULL,
    snapshot_hash       TEXT NOT NULL,        -- tamper-proof hash from engine
    snapshot_json       TEXT NOT NULL,        -- full JSON payload (for replay)
    regression_detected INTEGER DEFAULT 0,   -- boolean
    regression_reason   TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshot_project ON bankability_snapshots(project_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_state ON bankability_snapshots(current_state);


-- Gate status cache: denormalized for fast reads by frontend.
-- Updated after each evaluation. One row per (project, gate).
CREATE TABLE IF NOT EXISTS bankability_gate_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    gate_id         TEXT NOT NULL,
    gate_name       TEXT NOT NULL,
    total_evidence  INTEGER NOT NULL,
    verified_count  INTEGER NOT NULL,
    completion_pct  REAL NOT NULL,
    is_complete     INTEGER NOT NULL DEFAULT 0,  -- boolean
    blocking_items  TEXT,                          -- JSON array of evidence keys
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, gate_id)
);

CREATE INDEX IF NOT EXISTS idx_gate_status_project ON bankability_gate_status(project_id);


-- Capital unlock status: denormalized for finance dashboard.
CREATE TABLE IF NOT EXISTS bankability_capital_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    capital_type    TEXT NOT NULL,
    is_unlocked     INTEGER NOT NULL DEFAULT 0,
    gating_gates    TEXT,                         -- JSON array of gate IDs
    best_progress_pct REAL NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, capital_type)
);


-- ═══════════════════════════════════════════════════════════════════════════════
-- VIEWS: Pre-built queries for common frontend needs
-- ═══════════════════════════════════════════════════════════════════════════════

-- Producer view: construction + production gates
CREATE VIEW IF NOT EXISTS v_producer_gates AS
SELECT gs.*, be.status as evidence_status, be.evidence_key
FROM bankability_gate_status gs
LEFT JOIN bankability_evidence be ON gs.project_id = be.project_id AND gs.gate_id = be.gate_id
WHERE gs.gate_id IN (
    'G0_SITE_RIGHTS', 'G1_GRID_UTILITIES_REALITY', 'G3_INPUTS_SECURED',
    'G5_EPC_RISK_PRICED', 'G9_PERMITS_SAFE', 'G11_COD_STABILIZATION'
);

-- Finance view: financial milestone gates
CREATE VIEW IF NOT EXISTS v_finance_gates AS
SELECT gs.*, be.status as evidence_status, be.evidence_key
FROM bankability_gate_status gs
LEFT JOIN bankability_evidence be ON gs.project_id = be.project_id AND gs.gate_id = be.gate_id
WHERE gs.gate_id IN (
    'G4_OFFTAKE_BANKABLE', 'G6_IE_SIGNOFF', 'G8_AUDIT_GRADE_MODEL',
    'G10_FINANCIAL_CLOSE_CP', 'G7_INSURANCE_BOUND'
);

-- Regulator view: verification + audit gates
CREATE VIEW IF NOT EXISTS v_regulator_gates AS
SELECT gs.*, be.status as evidence_status, be.evidence_key
FROM bankability_gate_status gs
LEFT JOIN bankability_evidence be ON gs.project_id = be.project_id AND gs.gate_id = be.gate_id
WHERE gs.gate_id IN (
    'G2_CERTIFICATION_PATH_LOCKED', 'G6_IE_SIGNOFF',
    'G7_INSURANCE_BOUND', 'G9_PERMITS_SAFE'
);

-- Executive KPI view: state progression across all projects
CREATE VIEW IF NOT EXISTS v_executive_kpi AS
SELECT
    project_id,
    current_state,
    overall_completion_pct,
    total_evidence,
    total_verified,
    regression_detected,
    evaluated_at,
    snapshot_hash
FROM bankability_snapshots
WHERE id IN (
    SELECT MAX(id) FROM bankability_snapshots GROUP BY project_id
);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SEED: Initialize evidence rows for a new project
-- Run this when a new project is created in gex-platform-enhanced.
-- ═══════════════════════════════════════════════════════════════════════════════

-- Example: seed evidence for project 'PROJ-001'
-- In practice, the platform does this via Python on project creation:
--
--   from app.core.bankability_engine import GATE_REGISTRY
--   for gate in GATE_REGISTRY:
--       for evidence_key in gate.required_evidence:
--           db.execute("""
--               INSERT OR IGNORE INTO bankability_evidence
--               (project_id, evidence_key, gate_id, status)
--               VALUES (?, ?, ?, 'NOT_STARTED')
--           """, [project_id, evidence_key, gate.id])
