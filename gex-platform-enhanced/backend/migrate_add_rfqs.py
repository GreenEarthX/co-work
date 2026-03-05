"""
Database Migration: Add RFQs Table for Trader Workspace
Adds table for buyer Request for Quotes
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'gex_platform.db')

def migrate():
    """Add RFQs table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔄 Adding RFQs table for Trader workspace...\n")
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rfqs'")
        if cursor.fetchone():
            print("✓ RFQs table already exists")
        else:
            # Create RFQs table
            cursor.execute("""
                CREATE TABLE rfqs (
                    id TEXT PRIMARY KEY,
                    molecule TEXT NOT NULL,
                    volume_mtpd REAL NOT NULL,
                    max_price_eur_kg REAL,
                    delivery_start TEXT NOT NULL,
                    delivery_end TEXT NOT NULL,
                    location TEXT,
                    buyer_name TEXT NOT NULL,
                    buyer_contact TEXT,
                    compliance_requirements TEXT,
                    status TEXT DEFAULT 'draft',
                    correlation_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX idx_rfqs_molecule ON rfqs(molecule)")
            cursor.execute("CREATE INDEX idx_rfqs_status ON rfqs(status)")
            cursor.execute("CREATE INDEX idx_rfqs_correlation ON rfqs(correlation_id)")
            
            print("✅ Created rfqs table")
            print("✅ Created indexes")
        
        conn.commit()
        
        print("\n✅ Migration completed successfully!")
        print("\n📊 Summary:")
        print("   • RFQs table ready")
        print("   • Indexes created for fast lookups")
        print("   • Ready for Trader workspace")
        print("\n🎯 Next: Restart backend and test RFQ endpoints")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
