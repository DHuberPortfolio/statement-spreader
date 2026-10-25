"""A local SQLite database and an append-only, tamper-evident audit log for the engines.

Append-only is enforced by the database itself: triggers refuse UPDATE and DELETE on the
events table, so no code path (including a bug) can rewrite history. Each event also stores
the hash of the previous event; verify_chain() recomputes the chain and reports the first
event that does not fit, which detects edits made with other tools.

This is evidence, not a security boundary: whoever controls the file can rebuild it. A
deployment that needs a stronger guarantee ships events to write-once storage.
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

from .fingerprint import canonical_json, content_hash

AUDIT_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        engine TEXT NOT NULL,
        scope TEXT NOT NULL,          -- what the event is about, e.g. 'recon:3' or 'invoice:INV-1'
        actor TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,        -- JSON
        prev_hash TEXT NOT NULL,
        hash TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS audit_scope ON audit_events(engine, scope)""",
    """CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """One SQLite file, one connection guarded by a lock, transactions as a context manager."""

    def __init__(self, path: str | Path, schema: list[str] | None = None):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        with self.tx():
            for stmt in AUDIT_SCHEMA + (schema or []):
                self.conn.execute(stmt)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """All writes inside one block land together or not at all."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")

    def query(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    # -- audit log ---------------------------------------------------------------------------

    def append_event(self, conn: sqlite3.Connection, engine: str, scope: str, actor: str, kind: str,
                     payload: dict[str, Any]) -> int:
        """Append inside the caller's transaction, so the event and the change it records commit together."""
        last = conn.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "genesis"
        at = now()
        body = canonical_json(payload)
        h = content_hash([prev, at, engine, scope, actor, kind, body], 32)
        cur = conn.execute(
            "INSERT INTO audit_events (at, engine, scope, actor, kind, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)",
            (at, engine, scope, actor, kind, body, prev, h))
        return int(cur.lastrowid or 0)

    def events(self, engine: str, scope: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_events WHERE engine = ?" + (" AND scope = ?" if scope else "") + " ORDER BY id"
        rows = self.query(sql, (engine, scope) if scope else (engine,))
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def verify_chain(self) -> tuple[bool, int | None]:
        """(True, None) when every event's hash fits; else (False, id of the first that does not)."""
        prev = "genesis"
        for r in self.query("SELECT * FROM audit_events ORDER BY id"):
            h = content_hash([prev, r["at"], r["engine"], r["scope"], r["actor"], r["kind"], r["payload"]], 32)
            if r["prev_hash"] != prev or r["hash"] != h:
                return False, int(r["id"])
            prev = r["hash"]
        return True, None
