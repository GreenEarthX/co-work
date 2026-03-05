#!/usr/bin/env python3
"""
GreenEarthX Database Setup Script (SQLite)
Run this to create and populate the database
"""
import sqlite3
import os

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'gex_platform.db')
FINANCE_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema_finance_sqlite.sql')
PRODUCER_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema_producer_sqlite.sql')

def setup_database():
    """Create database and run schemas"""
    print(f"Setting up database at: {DB_PATH}")
    
    # Connect to database (creates if doesn't exist)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Read and execute finance schema
    print(f"Loading finance schema from: {FINANCE_SCHEMA_PATH}")
    with open(FINANCE_SCHEMA_PATH, 'r') as f:
        finance_sql = f.read()
    cursor.executescript(finance_sql)
    
    # Read and execute producer schema
    print(f"Loading producer schema from: {PRODUCER_SCHEMA_PATH}")
    with open(PRODUCER_SCHEMA_PATH, 'r') as f:
        producer_sql = f.read()
    cursor.executescript(producer_sql)
    
    conn.commit()
    print("✅ Database setup complete!")
    
    # Verify data
    cursor.execute("SELECT COUNT(*) FROM stage_gates")
    gates_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM covenants")
    covenants_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM contracts")
    contracts_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM capacities")
    capacities_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tokens")
    tokens_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM offers")
    offers_count = cursor.fetchone()[0]
    
    print(f"\n📊 Finance Data:")
    print(f"  - Stage gates: {gates_count}")
    print(f"  - Covenants: {covenants_count}")
    print(f"  - Contracts: {contracts_count}")
    
    print(f"\n📦 Producer Data:")
    print(f"  - Capacities: {capacities_count}")
    print(f"  - Tokens: {tokens_count}")
    print(f"  - Offers: {offers_count}")
    
    conn.close()
    print(f"\n✅ Database ready at: {DB_PATH}")

if __name__ == '__main__':
    setup_database()
