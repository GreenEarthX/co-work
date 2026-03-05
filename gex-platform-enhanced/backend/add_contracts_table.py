"""
Database Migration: Add Contracts Table for Producer Workspace
Run this script to add the contracts table to your existing database
"""
import sqlite3
import os

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'gex_platform.db')

def migrate():
    """Add contracts table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if contracts table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='contracts'
        """)
        
        if cursor.fetchone():
            print("✓ Contracts table already exists")
        else:
            # Create contracts table
            cursor.execute("""
                CREATE TABLE contracts (
                    id TEXT PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    buyer_name TEXT NOT NULL,
                    molecule TEXT NOT NULL,
                    volume_mtpd REAL NOT NULL,
                    price_eur_kg REAL NOT NULL,
                    delivery_start TEXT NOT NULL,
                    delivery_end TEXT NOT NULL,
                    contract_terms TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (match_id) REFERENCES matches(id)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX idx_contracts_match ON contracts(match_id)")
            cursor.execute("CREATE INDEX idx_contracts_status ON contracts(status)")
            cursor.execute("CREATE INDEX idx_contracts_molecule ON contracts(molecule)")
            
            conn.commit()
            print("✓ Contracts table created successfully")
        
        # Verify table structure
        cursor.execute("PRAGMA table_info(contracts)")
        columns = cursor.fetchall()
        print(f"\n✓ Contracts table has {len(columns)} columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        conn.close()
        raise

if __name__ == "__main__":
    migrate()
