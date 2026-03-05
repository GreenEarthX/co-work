-- ============================================================================
-- Enhanced Orchestrator SQLite Schema
-- Project Finance Grade Tracking
-- ============================================================================

-- ============================================================================
-- PROJECT STATES (Enhanced with TR levels)
-- ============================================================================

CREATE TABLE IF NOT EXISTS project_states (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL UNIQUE,
    
    -- Current state
    current_state TEXT NOT NULL,
    previous_state TEXT,
    tr_level TEXT,  -- TR1-TR9
    state_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Milestone timestamps
    evaluation_completed_at TIMESTAMP,
    modeling_completed_at TIMESTAMP,
    certification_issued_at TIMESTAMP,
    listed_at TIMESTAMP,
    financial_close_at TIMESTAMP,
    cod_achieved_at TIMESTAMP,
    
    -- State metadata
    state_metadata TEXT,  -- JSON
    
    CHECK (current_state IN (
        'submitted', 'evaluating', 'evaluated',
        'modeling', 'modeled',
        'certification_pending', 'certified',
        'listed', 'in_review',
        'financial_close',
        'construction_site_prep', 'construction_50pct',
        'mechanical_complete', 'commissioning',
        'cod_achieved', 'operating',
        'settling', 'settled',
        'rejected', 'cancelled', 'failed'
    )),
    
    CHECK (tr_level IN (
        'TR1', 'TR2', 'TR3', 'TR4', 'TR5',
        'TR6', 'TR7', 'TR8', 'TR9', NULL
    ))
);

CREATE INDEX idx_project_states_project ON project_states(project_id);
CREATE INDEX idx_project_states_state ON project_states(current_state);
CREATE INDEX idx_project_states_tr ON project_states(tr_level);


-- ============================================================================
-- DRAWDOWN TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS drawdown_tranches (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL,
    
    -- Tranche details
    tranche_number INTEGER NOT NULL CHECK (tranche_number BETWEEN 1 AND 5),
    tranche_name TEXT NOT NULL,
    percentage REAL NOT NULL,  -- % of total senior debt
    amount REAL,  -- Actual amount in EUR
    tr_level_required TEXT NOT NULL,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, requested, approved, drawn, rejected
    
    -- Conditions
    conditions_json TEXT,  -- JSON array of conditions
    conditions_met_json TEXT,  -- JSON array of which conditions are met
    
    -- Approval tracking
    requested_at TIMESTAMP,
    requested_by TEXT,
    approved_at TIMESTAMP,
    approved_by TEXT,
    drawn_at TIMESTAMP,
    rejected_at TIMESTAMP,
    rejection_reason TEXT,
    
    -- Independent engineer certification
    ie_certificate_number TEXT,
    ie_certificate_date TIMESTAMP,
    ie_approved_by TEXT,
    
    CHECK (status IN ('pending', 'requested', 'approved', 'drawn', 'rejected')),
    CHECK (tr_level_required IN ('TR4', 'TR5', 'TR6', 'TR7', 'TR9')),
    
    UNIQUE(project_id, tranche_number)
);

CREATE INDEX idx_drawdown_project ON drawdown_tranches(project_id);
CREATE INDEX idx_drawdown_status ON drawdown_tranches(status);
CREATE INDEX idx_drawdown_tranche_num ON drawdown_tranches(project_id, tranche_number);


-- ============================================================================
-- COVENANT MONITORING
-- ============================================================================

CREATE TABLE IF NOT EXISTS covenant_compliance (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL,
    
    -- Covenant details
    covenant_type TEXT NOT NULL,
    test_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    test_frequency TEXT NOT NULL,  -- quarterly, monthly, milestone, event_driven
    
    -- Test results
    is_compliant INTEGER NOT NULL,  -- 0 = breach, 1 = compliant
    threshold_value REAL,
    actual_value REAL,
    variance REAL,
    
    -- Breach handling
    breach_severity TEXT,  -- minor, major, event_of_default
    cure_period_days INTEGER,
    cure_deadline TIMESTAMP,
    cured INTEGER DEFAULT 0,
    cured_at TIMESTAMP,
    
    -- Documentation
    notes TEXT,
    supporting_docs TEXT,  -- JSON array of document references
    
    CHECK (covenant_type IN (
        'minimum_dscr', 'completion_guarantee', 
        'reserve_accounts', 'minimum_equity', 'change_of_control'
    )),
    CHECK (test_frequency IN ('quarterly', 'monthly', 'milestone', 'event_driven'))
);

CREATE INDEX idx_covenant_project ON covenant_compliance(project_id);
CREATE INDEX idx_covenant_type ON covenant_compliance(covenant_type);
CREATE INDEX idx_covenant_compliant ON covenant_compliance(is_compliant);
CREATE INDEX idx_covenant_date ON covenant_compliance(test_date DESC);


-- ============================================================================
-- RESERVE ACCOUNTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS reserve_accounts (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL,
    
    -- Account details
    account_type TEXT NOT NULL,  -- DSRA, MMRA, working_capital
    account_name TEXT NOT NULL,
    
    -- Balances
    current_balance REAL NOT NULL DEFAULT 0,
    required_balance REAL NOT NULL,
    
    -- Funding
    initially_funded_at TIMESTAMP,
    last_funded_at TIMESTAMP,
    last_withdrawal_at TIMESTAMP,
    
    -- Compliance
    is_adequate INTEGER NOT NULL DEFAULT 1,  -- 0 = deficient, 1 = adequate
    deficiency_amount REAL DEFAULT 0,
    
    CHECK (account_type IN ('DSRA', 'MMRA', 'working_capital', 'contingency')),
    
    UNIQUE(project_id, account_type)
);

CREATE INDEX idx_reserve_project ON reserve_accounts(project_id);
CREATE INDEX idx_reserve_type ON reserve_accounts(account_type);
CREATE INDEX idx_reserve_adequate ON reserve_accounts(is_adequate);


-- ============================================================================
-- EQUITY CONTRIBUTIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS equity_contributions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL,
    
    -- Contribution details
    investor_id TEXT NOT NULL,
    contribution_date TIMESTAMP NOT NULL,
    amount REAL NOT NULL,
    
    -- Purpose
    contribution_type TEXT NOT NULL,  -- initial, additional, cure
    linked_to_tranche INTEGER,  -- Which debt tranche this enables
    
    -- Verification
    verified INTEGER DEFAULT 0,
    verified_by TEXT,
    verified_at TIMESTAMP,
    
    -- Documentation
    wire_confirmation TEXT,
    notes TEXT,
    
    CHECK (contribution_type IN ('initial', 'additional', 'cure', 'other'))
);

CREATE INDEX idx_equity_project ON equity_contributions(project_id);
CREATE INDEX idx_equity_investor ON equity_contributions(investor_id);
CREATE INDEX idx_equity_date ON equity_contributions(contribution_date DESC);


-- ============================================================================
-- STAKEHOLDER ACCESS CONTROL
-- ============================================================================

CREATE TABLE IF NOT EXISTS project_stakeholders (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project and user
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    
    -- Role
    role TEXT NOT NULL,
    
    -- Access level
    data_access_level TEXT NOT NULL,  -- full, financial, summary, public
    can_approve_drawdowns INTEGER DEFAULT 0,
    can_waive_covenants INTEGER DEFAULT 0,
    
    -- Status
    access_granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_granted_by TEXT,
    access_revoked_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    
    CHECK (role IN (
        'producer', 'senior_lender', 'junior_lender',
        'equity_investor', 'grant_agency', 'regulator',
        'auditor', 'independent_engineer'
    )),
    CHECK (data_access_level IN ('full', 'financial', 'summary', 'public')),
    
    UNIQUE(project_id, user_id, role)
);

CREATE INDEX idx_stakeholder_project ON project_stakeholders(project_id);
CREATE INDEX idx_stakeholder_user ON project_stakeholders(user_id);
CREATE INDEX idx_stakeholder_role ON project_stakeholders(role);
CREATE INDEX idx_stakeholder_active ON project_stakeholders(is_active);


-- ============================================================================
-- PROJECT EVENTS (Enhanced)
-- ============================================================================

CREATE TABLE IF NOT EXISTS project_events (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Event identification
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    
    -- Project reference
    project_id TEXT NOT NULL,
    
    -- State transition
    previous_state TEXT,
    new_state TEXT,
    previous_tr_level TEXT,
    new_tr_level TEXT,
    
    -- Actor
    actor_id TEXT,
    actor_type TEXT,  -- user, system, service, lender
    actor_role TEXT,  -- producer, senior_lender, etc.
    
    -- Event data
    event_data TEXT,  -- JSON
    
    -- Correlation
    correlation_id TEXT,
    causation_id TEXT,
    
    -- Audit
    event_hash TEXT,
    previous_event_hash TEXT
);

CREATE INDEX idx_event_project ON project_events(project_id);
CREATE INDEX idx_event_type ON project_events(event_type);
CREATE INDEX idx_event_date ON project_events(created_at DESC);
CREATE INDEX idx_event_sequence ON project_events(project_id, event_sequence);


-- ============================================================================
-- FINANCIAL METRICS (For Covenant Testing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS financial_metrics (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Project reference
    project_id TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_type TEXT NOT NULL,  -- monthly, quarterly, annual
    
    -- Revenue
    revenue REAL NOT NULL DEFAULT 0,
    subsidies REAL NOT NULL DEFAULT 0,
    other_income REAL DEFAULT 0,
    
    -- Costs
    opex REAL NOT NULL DEFAULT 0,
    maintenance_capex REAL DEFAULT 0,
    
    -- Cash flow
    cfads REAL NOT NULL DEFAULT 0,  -- Cash Flow Available for Debt Service
    
    -- Debt service
    debt_service_principal REAL DEFAULT 0,
    debt_service_interest REAL DEFAULT 0,
    total_debt_service REAL DEFAULT 0,
    
    -- Key ratios
    dscr REAL,  -- Debt Service Coverage Ratio
    llcr REAL,  -- Loan Life Coverage Ratio
    plcr REAL,  -- Project Life Coverage Ratio
    
    -- Production
    production_volume REAL,
    production_unit TEXT,  -- MTPD, kg, etc.
    
    -- Verification
    verified INTEGER DEFAULT 0,
    verified_by TEXT,
    verified_at TIMESTAMP,
    
    CHECK (period_type IN ('monthly', 'quarterly', 'annual'))
);

CREATE INDEX idx_metrics_project ON financial_metrics(project_id);
CREATE INDEX idx_metrics_period ON financial_metrics(period_start, period_end);
CREATE INDEX idx_metrics_dscr ON financial_metrics(dscr);


-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Current project status
CREATE VIEW IF NOT EXISTS v_project_status AS
SELECT 
    ps.project_id,
    ps.current_state,
    ps.tr_level,
    ps.state_changed_at,
    
    -- Latest financial metrics
    fm.dscr,
    fm.cfads,
    fm.total_debt_service,
    fm.period_end as last_financial_period,
    
    -- Drawdown progress
    (SELECT COUNT(*) FROM drawdown_tranches WHERE project_id = ps.project_id AND status = 'drawn') as tranches_drawn,
    (SELECT SUM(amount) FROM drawdown_tranches WHERE project_id = ps.project_id AND status = 'drawn') as total_drawn,
    
    -- Covenant compliance
    (SELECT COUNT(*) FROM covenant_compliance WHERE project_id = ps.project_id AND is_compliant = 0 AND cured = 0) as active_breaches,
    
    -- Reserve adequacy
    (SELECT COUNT(*) FROM reserve_accounts WHERE project_id = ps.project_id AND is_adequate = 0) as deficient_reserves
    
FROM project_states ps
LEFT JOIN financial_metrics fm ON fm.project_id = ps.project_id 
    AND fm.created_at = (SELECT MAX(created_at) FROM financial_metrics WHERE project_id = ps.project_id);


-- View: Drawdown status
CREATE VIEW IF NOT EXISTS v_drawdown_status AS
SELECT 
    project_id,
    tranche_number,
    tranche_name,
    status,
    amount,
    tr_level_required,
    requested_at,
    approved_at,
    drawn_at
FROM drawdown_tranches
ORDER BY project_id, tranche_number;


-- View: Covenant summary
CREATE VIEW IF NOT EXISTS v_covenant_summary AS
SELECT 
    project_id,
    covenant_type,
    test_date,
    is_compliant,
    actual_value,
    threshold_value,
    CASE WHEN is_compliant = 0 THEN 'BREACH' ELSE 'COMPLIANT' END as status
FROM covenant_compliance
WHERE created_at IN (
    SELECT MAX(created_at) 
    FROM covenant_compliance 
    GROUP BY project_id, covenant_type
);


-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_project_states_timestamp
AFTER UPDATE ON project_states
BEGIN
    UPDATE project_states SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_reserve_accounts_timestamp
AFTER UPDATE ON reserve_accounts
BEGIN
    UPDATE reserve_accounts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- ============================================================================
-- INITIAL DATA / EXAMPLES
-- ============================================================================

-- Example: Initialize drawdown tranches for a project
-- INSERT INTO drawdown_tranches (id, project_id, tranche_number, tranche_name, percentage, tr_level_required)
-- VALUES 
--     ('dt_1', 'proj_001', 1, 'Financial Close', 15.0, 'TR4'),
--     ('dt_2', 'proj_001', 2, 'Site Preparation', 20.0, 'TR5'),
--     ('dt_3', 'proj_001', 3, 'Construction 50%', 30.0, 'TR6'),
--     ('dt_4', 'proj_001', 4, 'Mechanical Complete', 25.0, 'TR7'),
--     ('dt_5', 'proj_001', 5, 'COD', 10.0, 'TR9');


-- ============================================================================
-- HELPER QUERIES
-- ============================================================================

-- Get current DSCR for a project
-- SELECT dscr, period_end FROM financial_metrics 
-- WHERE project_id = ? ORDER BY period_end DESC LIMIT 1;

-- Check covenant compliance
-- SELECT * FROM v_covenant_summary WHERE project_id = ?;

-- Get drawdown status
-- SELECT * FROM v_drawdown_status WHERE project_id = ?;

-- Check reserve accounts
-- SELECT account_type, current_balance, required_balance, 
--        (current_balance - required_balance) as surplus_deficit
-- FROM reserve_accounts WHERE project_id = ?;

-- Get stakeholders for a project
-- SELECT user_id, role, data_access_level 
-- FROM project_stakeholders 
-- WHERE project_id = ? AND is_active = 1;
