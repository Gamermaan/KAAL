import sqlite3
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import DB_PATH

def migrate():
    print(f"[*] Starting database migration for {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=OFF")
    cursor = conn.cursor()

    # 1. Update agents table
    print("[+] Updating 'agents' table...")
    columns_to_add = {
        "seq_in": "INTEGER DEFAULT -1",
        "seq_out": "INTEGER DEFAULT 0",
        "integrity_hash": "TEXT",
        "transport_health": "TEXT DEFAULT 'healthy'",
        "last_error": "TEXT"
    }

    cursor.execute("PRAGMA table_info(agents)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    for col, definition in columns_to_add.items():
        if col not in existing_columns:
            print(f"    - Adding column: {col}")
            cursor.execute(f"ALTER TABLE agents ADD COLUMN {col} {definition}")
        else:
            print(f"    - Column '{col}' already exists.")

    # 2. Add SYSTEM agent for logging
    print("[+] Seeding 'SYSTEM' agent...")
    cursor.execute("SELECT id FROM agents WHERE id = 'SYSTEM'")
    if not cursor.fetchone():
        from datetime import datetime
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO agents (id, platform, hostname, first_seen, last_seen, status, connection_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("SYSTEM", "orchestrator", "KAAL-SERVER", now, now, "active", "internal"))
        print("    - Seeded 'SYSTEM' agent.")

    # 3. Create agent_events table if missing
    print("[+] Ensuring 'agent_events' table exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id        TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            severity        TEXT DEFAULT 'INFO',
            message         TEXT,
            timestamp       TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[*] Migration completed successfully.")

if __name__ == "__main__":
    migrate()
