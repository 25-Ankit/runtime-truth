"""SQLite database connection and schema management."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from runtime_truth.core.errors import StorageError

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    host_metadata TEXT NOT NULL,
    runtime_mode TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS declared_entities (
    entity_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    raw_value TEXT,
    source TEXT NOT NULL,
    source_location TEXT,
    metadata TEXT NOT NULL,
    PRIMARY KEY (run_id, entity_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runtime_events (
    event_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    pid INTEGER,
    process TEXT,
    event_type TEXT NOT NULL,
    attributes TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_reference TEXT,
    PRIMARY KEY (run_id, event_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observed_entities (
    entity_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL,
    evidence_ids TEXT NOT NULL,
    attributes TEXT NOT NULL,
    PRIMARY KEY (run_id, entity_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    event_id TEXT,
    collector TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    description TEXT NOT NULL,
    raw_evidence TEXT,
    structured_data TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    subject TEXT NOT NULL,
    declared_state TEXT,
    observed_state TEXT,
    explanation TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, finding_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_declared_run ON declared_entities (run_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON runtime_events (run_id);
CREATE INDEX IF NOT EXISTS idx_observed_run ON observed_entities (run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence (run_id);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings (run_id);
"""


class Database:
    """Manages SQLite connections and schema initialization."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._is_memory = (db_path == ":memory:")
        self._mem_conn: Optional[sqlite3.Connection] = None
        if not self._is_memory:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        if self._is_memory and self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise StorageError(f"Database error: {exc}") from exc
        finally:
            if not self._is_memory:
                conn.close()

    def initialize_schema(self) -> None:
        """Create tables and record schema version if not present."""
        with self.session() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_version WHERE version = ?", (SCHEMA_VERSION,))
            row = cursor.fetchone()
            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_str),
                )
