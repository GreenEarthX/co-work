"""
Add financial_model_results table to SQLite database
Run this from backend/ directory: python add_financial_model_table.py
"""
import sqlite3
import os

# Database path (same as your code)
DB_PATH = os.path.join(os.path.dirname(__file__), 'gex_platform.db')

def add_financial_model_table():
    """Add financial_model_results table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_model_results (
            id TEXT PRIMARY KEY,
            match_id TEXT NOT NULL,
            bankability TEXT NOT NULL,
            dscr_base REAL NOT NULL,
            dscr_stress REAL NOT NULL,
            irr_base REAL NOT NULL,
            irr_stress REAL NOT NULL,
            recommendation TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
    """)
    
    # Create index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_financial_model_match 
        ON financial_model_results(match_id)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Successfully created financial_model_results table")
    print(f"   Database: {DB_PATH}")

if __name__ == "__main__":
    add_financial_model_table()
