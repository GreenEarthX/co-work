"""
Seed script: inserts the 5 canonical customer projects into gex_platform.db.
Run from the backend/ directory:
    python seed_customer_projects.py
"""
import sqlite3
import json
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "gex_platform.db")

PROJECTS = [
    {
        "id": "proj_bremen_h2",
        "project_name": "Bremen Green Hydrogen Plant",
        "molecule": "H2",
        "capacity_mtpd": 85.0,
        "location": "Bremen, Germany",
        "capex_eur": 220_000_000.0,
        "opex_eur_kg": 3.20,
        "production_start": "2026-09-30",
        "production_end": "2046-09-30",
        "compliance_certifications": json.dumps(["RED_III", "RFNBO", "ISO_14064"]),
        "status": "construction",
    },
    {
        "id": "proj_rotterdam_nh3",
        "project_name": "Rotterdam Green Ammonia Terminal",
        "molecule": "NH3",
        "capacity_mtpd": 160.0,
        "location": "Rotterdam, Netherlands",
        "capex_eur": 380_000_000.0,
        "opex_eur_kg": 0.55,
        "production_start": "2028-06-30",
        "production_end": "2048-06-30",
        "compliance_certifications": json.dumps(["RED_III", "RFNBO"]),
        "status": "development",
    },
    {
        "id": "proj_sansebastian_emethanol",
        "project_name": "Project Helios e-Methanol",
        "molecule": "e-Methanol",
        "capacity_mtpd": 42.0,
        "location": "San Sebastián, Spain",
        "capex_eur": 165_000_000.0,
        "opex_eur_kg": 0.88,
        "production_start": "2027-03-31",
        "production_end": "2047-03-31",
        "compliance_certifications": json.dumps(["RED_III", "45V", "FuelEU_Maritime"]),
        "status": "construction",
    },
    {
        "id": "proj_wales_saf",
        "project_name": "Celtic Green SAF Complex",
        "molecule": "SAF",
        "capacity_mtpd": 28.0,
        "location": "Neath Port Talbot, Wales",
        "capex_eur": 290_000_000.0,
        "opex_eur_kg": 1.45,
        "production_start": "2029-01-31",
        "production_end": "2049-01-31",
        "compliance_certifications": json.dumps(["ReFuelEU_Aviation", "RED_III", "CORSIA"]),
        "status": "development",
    },
    {
        "id": "proj_lehavre_eng",
        "project_name": "Le Havre e-Gas Hub",
        "molecule": "e-NG",
        "capacity_mtpd": 55.0,
        "location": "Le Havre, France",
        "capex_eur": 195_000_000.0,
        "opex_eur_kg": 1.10,
        "production_start": "2025-11-30",
        "production_end": "2045-11-30",
        "compliance_certifications": json.dumps(["RED_III", "ISO_14064", "FR_Green_Gas_Tariff"]),
        "status": "operating",
    },
]

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create capacities table if it doesn't exist yet."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS capacities (
            id TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            molecule TEXT NOT NULL,
            capacity_mtpd REAL NOT NULL,
            location TEXT,
            production_start DATE,
            production_end DATE,
            compliance_certifications TEXT,
            capex_eur REAL,
            opex_eur_kg REAL,
            status TEXT DEFAULT 'development',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add status column if it was created without it
    try:
        conn.execute("ALTER TABLE capacities ADD COLUMN status TEXT DEFAULT 'development'")
    except sqlite3.OperationalError:
        pass  # Column already exists


def seed(conn: sqlite3.Connection) -> None:
    ensure_schema(conn)
    inserted = 0
    skipped  = 0
    for p in PROJECTS:
        existing = conn.execute(
            "SELECT id FROM capacities WHERE id = ?", (p["id"],)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO capacities
              (id, project_name, molecule, capacity_mtpd, location,
               production_start, production_end, compliance_certifications,
               capex_eur, opex_eur_kg, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["id"], p["project_name"], p["molecule"], p["capacity_mtpd"],
            p["location"], p["production_start"], p["production_end"],
            p["compliance_certifications"], p["capex_eur"], p["opex_eur_kg"],
            p["status"],
        ))
        inserted += 1
        print(f"  + Inserted: {p['project_name']}")
    conn.commit()
    print(f"\nDone — {inserted} inserted, {skipped} already existed.")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run the backend first (uvicorn app.main:app) to initialise the DB, then re-run this script.")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    try:
        seed(conn)
    finally:
        conn.close()
