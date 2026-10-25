"""Persistence: documents, runs, an append-only audit log, reviewer mapping memory, timings.

SQLite (the standard library's sqlite3), one file under var/. Every write that changes a run
happens inside one transaction, so a crash leaves either the old state or the new one, never a
half-updated run. The audit log is append-only: corrections are new events, never edits.

Document bytes are stored as files named by their SHA-256, outside the database; uploading the
same file twice stores it once.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,               -- sha256 of the bytes
        filename TEXT NOT NULL,
        format TEXT NOT NULL,
        size INTEGER NOT NULL,
        uploaded_at TEXT NOT NULL,
        label TEXT                         -- e.g. the company name a reviewer gives it
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL REFERENCES documents(id),
        idempotency_key TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        profile_version TEXT NOT NULL,
        engine_version TEXT NOT NULL,
        memory_version INTEGER NOT NULL,
        model TEXT NOT NULL,               -- 'none' or the model id used for mapping
        status TEXT NOT NULL,              -- running | succeeded | failed
        error TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        timings TEXT,                      -- JSON: stage -> ms
        spread TEXT,                       -- JSON: the computed Spread
        state TEXT NOT NULL DEFAULT '{}',  -- JSON: reviewer overrides, resolutions, approval
        parent_run INTEGER REFERENCES runs(id)
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS runs_idem ON runs(idempotency_key) WHERE status != 'failed'""",
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER REFERENCES runs(id),
        document_id TEXT,
        at TEXT NOT NULL,
        actor TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL              -- JSON
    )""",
    """CREATE TABLE IF NOT EXISTS mapping_memory (
        profile_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        label TEXT NOT NULL,
        section TEXT NOT NULL,
        canonical TEXT NOT NULL,           -- '' means exclude the row
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        source_run INTEGER,
        PRIMARY KEY (profile_id, statement, label, section)
    )""",
    # What each company's approved spreads leave behind (spreader.company). Approved values are append-only: a later
    # approval adds rows and a reopened spread is withdrawn by a new row, so the history of what was approved, by
    # whom and when, can never be rewritten.
    """CREATE TABLE IF NOT EXISTS approved_values (
        company_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        run_id INTEGER NOT NULL REFERENCES runs(id),
        document_id TEXT NOT NULL,
        period TEXT NOT NULL,
        line TEXT NOT NULL,
        value TEXT NOT NULL,               -- Decimal as text
        tolerance TEXT NOT NULL,
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS approved_values_company ON approved_values(company_id, profile_id)""",
    """CREATE TABLE IF NOT EXISTS approval_withdrawals (
        run_id INTEGER NOT NULL REFERENCES runs(id),
        withdrawn_by TEXT NOT NULL,
        withdrawn_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS company_mappings (
        company_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        label TEXT NOT NULL,
        section TEXT NOT NULL,
        canonical TEXT NOT NULL,
        run_id INTEGER NOT NULL REFERENCES runs(id),
        confirmed_by TEXT NOT NULL,
        confirmed_at TEXT NOT NULL
    )""",
    """CREATE TRIGGER IF NOT EXISTS approved_values_no_update BEFORE UPDATE ON approved_values
       BEGIN SELECT RAISE(ABORT, 'approved values are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS approved_values_no_delete BEFORE DELETE ON approved_values
       BEGIN SELECT RAISE(ABORT, 'approved values are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS company_mappings_no_update BEFORE UPDATE ON company_mappings
       BEGIN SELECT RAISE(ABORT, 'company mappings are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS company_mappings_no_delete BEFORE DELETE ON company_mappings
       BEGIN SELECT RAISE(ABORT, 'company mappings are append-only'); END""",
    """CREATE TABLE IF NOT EXISTS work_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL,
        run_id INTEGER,
        mode TEXT NOT NULL,                -- baseline (spread by hand) | assisted (review a run)
        actor TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        active_seconds REAL NOT NULL DEFAULT 0,
        corrections INTEGER NOT NULL DEFAULT 0,
        values_entered INTEGER NOT NULL DEFAULT 0,
        errors_found INTEGER,              -- baseline: hand-keyed values that disagree with the answer key
        values_checked INTEGER,
        note TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS assumptions (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        source TEXT NOT NULL,              -- measured | entered | default
        note TEXT,
        updated_at TEXT NOT NULL,
        updated_by TEXT NOT NULL
    )""",
]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_dir = self.path.parent / "documents"
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)
            if "company_id" not in {r["name"] for r in c.execute("PRAGMA table_info(documents)")}:
                c.execute("ALTER TABLE documents ADD COLUMN company_id TEXT")  # schema 3: who the document is about
            row = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            current = int(row["value"]) if row else 0
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema {current} is newer than this code ({SCHEMA_VERSION})")
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One transaction: everything inside commits together or not at all."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def query(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, args))

    # ---- documents ----
    def save_document(self, doc_id: str, filename: str, fmt: str, data: bytes) -> bool:
        """Store a document once. Returns True if it is new."""
        ext = {"html": "htm", "pdf": "pdf", "xlsx": "xlsx"}[fmt]
        blob = self.blob_dir / f"{doc_id}.{ext}"
        if not blob.exists():
            tmp = blob.with_suffix(blob.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(blob)  # atomic on the same volume
        with self.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO documents(id, filename, format, size, uploaded_at) VALUES (?,?,?,?,?)",
                            (doc_id, filename, fmt, len(data), now()))
            return cur.rowcount == 1

    def document_bytes(self, doc_id: str, fmt: str) -> bytes:
        ext = {"html": "htm", "pdf": "pdf", "xlsx": "xlsx"}[fmt]
        return (self.blob_dir / f"{doc_id}.{ext}").read_bytes()

    def document(self, doc_id: str) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM documents WHERE id=?", (doc_id,))
        return rows[0] if rows else None

    # ---- events ----
    def log(self, c: sqlite3.Connection, kind: str, payload: dict[str, Any], actor: str,
            run_id: int | None = None, document_id: str | None = None) -> None:
        c.execute("INSERT INTO events(run_id, document_id, at, actor, kind, payload) VALUES (?,?,?,?,?,?)",
                  (run_id, document_id, now(), actor, kind, json.dumps(payload, default=str)))

    # ---- memory ----
    def memory_rows(self, profile_id: str) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM mapping_memory WHERE profile_id=?", (profile_id,))

    def memory_version(self, profile_id: str) -> int:
        rows = self.query("SELECT COUNT(*) AS n, COALESCE(MAX(rowid), 0) AS m FROM mapping_memory WHERE profile_id=?",
                          (profile_id,))
        r = rows[0]
        return int(r["n"]) * 100000 + int(r["m"])
