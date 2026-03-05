-- GreenEarthX Finance Database Schema (SQLite)
-- Run this with: sqlite3 gex_platform.db < schema_finance_sqlite.sql

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================
-- FINANCE WORKSPACE TABLES
-- ============================================

-- Projects table (if not exists)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_name TEXT NOT NULL,
    molecule TEXT NOT NULL,
    location TEXT,
    description TEXT,
    stage TEXT,
    capacity_mtpd REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Stage Gates table
CREATE TABLE IF NOT EXISTS stage_gates (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    gate_name TEXT NOT NULL,
    status TEXT NOT NULL, -- 'complete', 'in-progress', 'at-risk', 'pending'
    completion_pct INTEGER NOT NULL DEFAULT 0,
    due_date DATE,
    completed_date DATE,
    critical_items TEXT, -- JSON array as text
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stage_gates_project ON stage_gates(project_id);
CREATE INDEX IF NOT EXISTS idx_stage_gates_status ON stage_gates(status);

-- Covenants table
CREATE TABLE IF NOT EXISTS covenants (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    covenant_name TEXT NOT NULL,
    current_value TEXT NOT NULL,
    required_value TEXT NOT NULL,
    status TEXT NOT NULL, -- 'compliant', 'warning', 'breach'
    trend TEXT, -- 'improving', 'stable', 'deteriorating'
    last_updated DATE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_covenants_project ON covenants(project_id);
CREATE INDEX IF NOT EXISTS idx_covenants_status ON covenants(status);

-- Insurance Policies table
CREATE TABLE IF NOT EXISTS insurance_policies (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    policy_id_external TEXT NOT NULL,
    policy_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    coverage_amount TEXT NOT NULL,
    premium_amount TEXT NOT NULL,
    start_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    status TEXT NOT NULL, -- 'active', 'expiring-soon', 'expired'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_insurance_project ON insurance_policies(project_id);
CREATE INDEX IF NOT EXISTS idx_insurance_expiry ON insurance_policies(expiry_date);

-- Guarantees table
CREATE TABLE IF NOT EXISTS guarantees (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    guarantee_id_external TEXT NOT NULL,
    guarantee_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    amount TEXT NOT NULL,
    beneficiary TEXT NOT NULL,
    expiry_date DATE NOT NULL,
    status TEXT NOT NULL, -- 'active', 'claimed', 'expired'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_guarantees_project ON guarantees(project_id);

-- Contracts table (for revenue/offtake)
CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    contract_id_external TEXT NOT NULL,
    counterparty TEXT NOT NULL,
    molecule TEXT NOT NULL,
    volume_mtpd REAL NOT NULL,
    price_eur_kg REAL NOT NULL,
    pricing_basis TEXT,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    tenor_years INTEGER NOT NULL,
    credit_rating TEXT,
    status TEXT NOT NULL, -- 'active', 'negotiating', 'expired'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contracts_project ON contracts(project_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);

-- Risk Register table
CREATE TABLE IF NOT EXISTS risks (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    risk_id_external TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    impact TEXT NOT NULL, -- 'high', 'medium', 'low'
    likelihood TEXT NOT NULL, -- 'high', 'medium', 'low'
    mitigation TEXT,
    owner TEXT,
    status TEXT NOT NULL, -- 'active', 'mitigated', 'escalated'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_risks_project ON risks(project_id);
CREATE INDEX IF NOT EXISTS idx_risks_status ON risks(status);

-- ============================================
-- SEED DATA (Sample data for demo)
-- ============================================

-- Insert sample project
INSERT OR IGNORE INTO projects (id, project_name, molecule, location, description, stage, capacity_mtpd) 
VALUES (
    'hanover-h2-project-001',
    'Hanover H2 Project',
    'H2',
    'Hanover, Germany',
    'Green hydrogen production facility',
    'FID',
    50.0
);

-- Insert Stage Gates
INSERT OR IGNORE INTO stage_gates (project_id, gate_name, status, completion_pct, due_date, completed_date, critical_items) VALUES
('hanover-h2-project-001', 'FEL (Front End Loading)', 'complete', 100, '2024-03-15', '2024-03-10', '[]'),
('hanover-h2-project-001', 'FEED (Front End Engineering Design)', 'complete', 100, '2024-09-30', '2024-09-25', '[]'),
('hanover-h2-project-001', 'FID (Final Investment Decision)', 'at-risk', 78, '2026-02-15', NULL, 
    '["EPC contract finalization (7 days overdue)", "Grid connection agreement pending signature", "Final environmental permit approval needed", "Offtake agreements at 72% (target: 75%)"]'),
('hanover-h2-project-001', 'Financial Close', 'pending', 15, '2026-04-30', NULL,
    '["Senior debt facility documentation", "Equity commitment letters", "Final technical advisor report", "Insurance placement"]'),
('hanover-h2-project-001', 'COD (Commercial Operations Date)', 'pending', 0, '2027-12-31', NULL,
    '["Construction completion", "Commissioning tests", "Performance guarantees satisfied", "All regulatory approvals final"]');

-- Insert Covenants
INSERT OR IGNORE INTO covenants (project_id, covenant_name, current_value, required_value, status, trend, last_updated) VALUES
('hanover-h2-project-001', 'DSCR (Debt Service Coverage Ratio)', '1.35x', '≥ 1.25x', 'compliant', 'stable', '2026-01-15'),
('hanover-h2-project-001', 'LLCR (Loan Life Coverage Ratio)', '1.52x', '≥ 1.40x', 'compliant', 'improving', '2026-01-15'),
('hanover-h2-project-001', 'Debt Service Reserve Account', '€8.2M', '≥ €7.5M', 'compliant', 'stable', '2026-01-20'),
('hanover-h2-project-001', 'Maintenance Reserve Account', '€2.1M', '≥ €2.0M', 'compliant', 'stable', '2026-01-20'),
('hanover-h2-project-001', 'Debt/Equity Ratio', '70/30', '≤ 75/25', 'compliant', 'stable', '2025-12-31'),
('hanover-h2-project-001', 'Minimum Liquidity', '€12.5M', '≥ €10.0M', 'compliant', 'improving', '2026-01-25');

-- Insert Insurance Policies
INSERT OR IGNORE INTO insurance_policies (project_id, policy_id_external, policy_type, provider, coverage_amount, premium_amount, start_date, expiry_date, status) VALUES
('hanover-h2-project-001', 'INS-001', 'All Risk Property Insurance', 'Munich Re', '€250M', '€1.2M/year', '2024-01-01', '2027-01-01', 'active'),
('hanover-h2-project-001', 'INS-002', 'Business Interruption', 'Swiss Re', '€100M (24mo)', '€850K/year', '2024-01-01', '2027-01-01', 'active'),
('hanover-h2-project-001', 'INS-003', 'Liability Insurance', 'Allianz SE', '€50M per occurrence', '€420K/year', '2025-06-01', '2026-06-01', 'active'),
('hanover-h2-project-001', 'INS-004', 'Construction All Risk', 'AXA XL', '€180M', '€2.1M (single)', '2025-03-01', '2026-12-31', 'active'),
('hanover-h2-project-001', 'INS-005', 'Directors & Officers', 'Chubb', '€25M', '€180K/year', '2025-01-01', '2026-02-15', 'expiring-soon');

-- Insert Guarantees
INSERT OR IGNORE INTO guarantees (project_id, guarantee_id_external, guarantee_type, provider, amount, beneficiary, expiry_date, status) VALUES
('hanover-h2-project-001', 'GUA-001', 'Performance Bond (EPC)', 'Deutsche Bank', '€15M (10% contract value)', 'Project Company', '2027-06-30', 'active'),
('hanover-h2-project-001', 'GUA-002', 'Advance Payment Guarantee', 'BNP Paribas', '€8M', 'Project Company', '2026-12-31', 'active'),
('hanover-h2-project-001', 'GUA-003', 'Warranty Bond (OEM)', 'Commerzbank', '€3M', 'Project Company', '2032-12-31', 'active');

-- Insert Contracts
INSERT OR IGNORE INTO contracts (project_id, contract_id_external, counterparty, molecule, volume_mtpd, price_eur_kg, pricing_basis, start_date, end_date, tenor_years, credit_rating, status) VALUES
('hanover-h2-project-001', 'C-001', 'BASF Industrial GmbH', 'H2', 15.0, 6.80, 'Fixed + inflation index (HICP)', '2027-01-01', '2037-12-31', 10, 'A-', 'active'),
('hanover-h2-project-001', 'C-002', 'Shell Refining B.V.', 'H2', 12.0, 6.50, 'Fixed + natural gas index', '2027-06-01', '2032-05-31', 5, 'BBB+', 'active'),
('hanover-h2-project-001', 'C-003', 'Air France Aviation SA', 'H2', 9.0, 7.20, 'Fixed', '2027-03-01', '2034-02-28', 7, 'A', 'active'),
('hanover-h2-project-001', 'C-004', 'Bayer Chemical AG', 'H2', 8.0, 6.90, 'Floor €6.50 / Ceiling €7.50', '2027-01-01', '2029-12-31', 3, 'BBB', 'negotiating');

-- Insert Risks
INSERT OR IGNORE INTO risks (project_id, risk_id_external, category, description, impact, likelihood, mitigation, owner, status) VALUES
('hanover-h2-project-001', 'R-001', 'Schedule', 'EPC contractor delays due to supply chain issues', 'high', 'medium', 'Secured alternative suppliers, penalty clauses in EPC contract', 'Project Director', 'active'),
('hanover-h2-project-001', 'R-002', 'Regulatory', 'Environmental permit approval delayed', 'high', 'medium', 'Engaged with regulator, submitted additional documentation', 'Regulatory Manager', 'escalated'),
('hanover-h2-project-001', 'R-003', 'Commercial', 'Offtake volume below financing threshold', 'high', 'low', 'Active negotiations with 3 additional offtakers', 'Commercial Director', 'active'),
('hanover-h2-project-001', 'R-004', 'Technical', 'Electrolyzer technology performance risk', 'medium', 'low', 'Performance guarantees from OEM, independent technical review', 'Technical Director', 'mitigated');
