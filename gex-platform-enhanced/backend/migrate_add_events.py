"""
Database Migration: Add Event-Driven Architecture Support
Adds correlation_id for chain of custody tracking
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'gex_platform.db')

def migrate():
    """Add correlation_id to all main tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔄 Adding correlation_id columns for chain of custody tracking...\n")
        
        # Check and add correlation_id to capacities
        cursor.execute("PRAGMA table_info(capacities)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'correlation_id' not in columns:
            cursor.execute("ALTER TABLE capacities ADD COLUMN correlation_id TEXT")
            cursor.execute("CREATE INDEX idx_capacities_correlation ON capacities(correlation_id)")
            print("✅ Added correlation_id to capacities table")
        else:
            print("✓ capacities.correlation_id already exists")
        
        # Add to tokens
        cursor.execute("PRAGMA table_info(tokens)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'correlation_id' not in columns:
            cursor.execute("ALTER TABLE tokens ADD COLUMN correlation_id TEXT")
            cursor.execute("CREATE INDEX idx_tokens_correlation ON tokens(correlation_id)")
            print("✅ Added correlation_id to tokens table")
        else:
            print("✓ tokens.correlation_id already exists")
        
        # Add to offers
        cursor.execute("PRAGMA table_info(offers)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'correlation_id' not in columns:
            cursor.execute("ALTER TABLE offers ADD COLUMN correlation_id TEXT")
            cursor.execute("CREATE INDEX idx_offers_correlation ON offers(correlation_id)")
            print("✅ Added correlation_id to offers table")
        else:
            print("✓ offers.correlation_id already exists")
        
        # Add to matches
        cursor.execute("PRAGMA table_info(matches)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'correlation_id' not in columns:
            cursor.execute("ALTER TABLE matches ADD COLUMN correlation_id TEXT")
            cursor.execute("CREATE INDEX idx_matches_correlation ON matches(correlation_id)")
            print("✅ Added correlation_id to matches table")
        else:
            print("✓ matches.correlation_id already exists")
        
        # Add to contracts
        cursor.execute("PRAGMA table_info(contracts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'correlation_id' not in columns:
            cursor.execute("ALTER TABLE contracts ADD COLUMN correlation_id TEXT")
            cursor.execute("CREATE INDEX idx_contracts_correlation ON contracts(correlation_id)")
            print("✅ Added correlation_id to contracts table")
        else:
            print("✓ contracts.correlation_id already exists")
        
        # Add status column to capacities if missing
        cursor.execute("PRAGMA table_info(capacities)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'status' not in columns:
            cursor.execute("ALTER TABLE capacities ADD COLUMN status TEXT DEFAULT 'draft'")
            print("✅ Added status to capacities table")
        else:
            print("✓ capacities.status already exists")
        
        conn.commit()
        
        print("\n✅ Migration completed successfully!")
        print("\n📊 Summary:")
        print("   • correlation_id added to 5 tables")
        print("   • Indexes created for fast lookups")
        print("   • Ready for event-driven architecture")
        print("\n🎯 Next: Update API endpoints to emit events")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
