-- GreenEarthX Producer Workspace Tables (SQLite)
-- Run this to add capacity, tokenization, marketplace tables

PRAGMA foreign_keys = ON;

-- ============================================
-- PRODUCER WORKSPACE TABLES
-- ============================================

-- Capacities table
CREATE TABLE IF NOT EXISTS capacities (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_name TEXT NOT NULL,
    molecule TEXT NOT NULL,
    capacity_mtpd REAL NOT NULL,
    location TEXT,
    production_start DATE,
    production_end DATE,
    compliance_certifications TEXT, -- JSON array
    capex_eur REAL,
    opex_eur_kg REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_capacities_project ON capacities(project_name);
CREATE INDEX IF NOT EXISTS idx_capacities_molecule ON capacities(molecule);

-- Tokens table (tokenized capacity)
CREATE TABLE IF NOT EXISTS tokens (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    capacity_id TEXT REFERENCES capacities(id) ON DELETE CASCADE,
    tokenised_mtpd REAL NOT NULL,
    delivery_start DATE NOT NULL,
    delivery_end DATE NOT NULL,
    compliance_certifications TEXT, -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tokens_capacity ON tokens(capacity_id);

-- Offers table (marketplace listings)
CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    token_id TEXT REFERENCES tokens(id) ON DELETE CASCADE,
    molecule TEXT NOT NULL,
    volume_mtpd REAL NOT NULL,
    price_eur_kg REAL NOT NULL,
    delivery_start DATE NOT NULL,
    delivery_end DATE NOT NULL,
    location TEXT,
    status TEXT DEFAULT 'active', -- 'active', 'matched', 'expired'
    offer_type TEXT DEFAULT 'indicative', -- 'indicative', 'firm'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_offers_molecule ON offers(molecule);
CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);

-- RFQs table (requests for quotes)
CREATE TABLE IF NOT EXISTS rfqs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    molecule TEXT NOT NULL,
    volume_mtpd REAL NOT NULL,
    max_price_eur_kg REAL,
    delivery_start DATE NOT NULL,
    delivery_end DATE NOT NULL,
    location TEXT,
    status TEXT DEFAULT 'open', -- 'open', 'matched', 'closed'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rfqs_molecule ON rfqs(molecule);
CREATE INDEX IF NOT EXISTS idx_rfqs_status ON rfqs(status);

-- Matches table (matching engine results)
CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    offer_id TEXT REFERENCES offers(id),
    rfq_id TEXT REFERENCES rfqs(id),
    match_score INTEGER NOT NULL,
    volume_mtpd REAL NOT NULL,
    price_eur_kg REAL NOT NULL,
    status TEXT DEFAULT 'pending', -- 'pending', 'accepted', 'rejected'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_matches_offer ON matches(offer_id);
CREATE INDEX IF NOT EXISTS idx_matches_rfq ON matches(rfq_id);

-- ============================================
-- SEED DATA (Sample)
-- ============================================

-- Sample capacity
INSERT OR IGNORE INTO capacities (id, project_name, molecule, capacity_mtpd, location, production_start, production_end, compliance_certifications, capex_eur, opex_eur_kg) 
VALUES (
    'capacity-hanover-001',
    'Hanover H2 Project',
    'H2',
    50.0,
    'Hanover, Germany',
    '2027-01-01',
    '2047-12-31',
    '["RFNBO", "RED III", "CertifHy"]',
    250000000.0,
    4.20
);

-- Sample token
INSERT OR IGNORE INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, compliance_certifications)
VALUES (
    'token-hanover-001',
    'capacity-hanover-001',
    32.5,
    '2027-01-01',
    '2032-12-31',
    '["RFNBO", "RED III"]'
);

-- Sample offers
INSERT OR IGNORE INTO offers (token_id, molecule, volume_mtpd, price_eur_kg, delivery_start, delivery_end, location, status, offer_type)
VALUES 
('token-hanover-001', 'H2', 10.0, 6.80, '2027-01-01', '2030-12-31', 'Hanover, Germany', 'active', 'firm'),
('token-hanover-001', 'H2', 5.2, 7.20, '2027-06-01', '2029-12-31', 'Hanover, Germany', 'active', 'indicative');

-- Sample RFQ
INSERT OR IGNORE INTO rfqs (molecule, volume_mtpd, max_price_eur_kg, delivery_start, delivery_end, location, status)
VALUES
('H2', 8.0, 7.50, '2027-01-01', '2029-12-31', 'Bremen, Germany', 'open');

VACUUM;
