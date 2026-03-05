-- ============================================================================
-- GreenMesh SQLite Schema
-- Production monitoring and settlement (Based on Oxford Energy bankability)
-- ============================================================================

-- Production readings table
CREATE TABLE IF NOT EXISTS production_readings (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    reading_timestamp TIMESTAMP NOT NULL,
    volume_produced REAL NOT NULL,
    production_rate REAL NOT NULL,
    ghg_intensity REAL NOT NULL,
    purity REAL NOT NULL,
    renewable_electricity_pct REAL NOT NULL,
    production_status TEXT NOT NULL,
    availability_pct REAL NOT NULL
);

-- Offtake contracts table
CREATE TABLE IF NOT EXISTS offtake_contracts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    buyer_id TEXT NOT NULL,
    buyer_credit_rating TEXT,
    contract_type TEXT NOT NULL,
    annual_volume_mt REAL NOT NULL,
    minimum_availability_pct REAL NOT NULL,
    performance_penalty_rate REAL NOT NULL,
    has_cfd_support INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

-- Deliveries table
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    volume_mt REAL NOT NULL,
    quality_verified INTEGER DEFAULT 0,
    verified_ghg_intensity REAL,
    quality_certificate_number TEXT,
    title_transferred INTEGER DEFAULT 0,
    title_transfer_date TIMESTAMP,
    delivery_status TEXT NOT NULL,
    invoice_amount REAL,
    payment_received INTEGER DEFAULT 0
);

-- Availability reports table
CREATE TABLE IF NOT EXISTS availability_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    availability_pct REAL NOT NULL,
    guaranteed_availability_pct REAL NOT NULL,
    penalty_triggered INTEGER DEFAULT 0,
    penalty_amount REAL,
    is_material_breach INTEGER DEFAULT 0
);

-- Quality certificates table
CREATE TABLE IF NOT EXISTS quality_certificates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    certificate_number TEXT UNIQUE NOT NULL,
    ghg_intensity_measured REAL NOT NULL,
    purity_measured REAL NOT NULL,
    red_iii_compliant INTEGER DEFAULT 0,
    v45_compliant INTEGER DEFAULT 0,
    is_valid INTEGER DEFAULT 1
);

-- Indexes
CREATE INDEX idx_production_project ON production_readings(project_id);
CREATE INDEX idx_deliveries_project ON deliveries(project_id);
CREATE INDEX idx_availability_project ON availability_reports(project_id);

-- View: Production performance
CREATE VIEW IF NOT EXISTS v_production_performance AS
SELECT 
    project_id,
    DATE(reading_timestamp) as production_date,
    SUM(volume_produced) as daily_volume,
    AVG(ghg_intensity) as avg_ghg_intensity,
    AVG(availability_pct) as avg_availability
FROM production_readings
GROUP BY project_id, DATE(reading_timestamp);
