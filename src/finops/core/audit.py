"""A local SQLite database and an append-only, tamper-evident audit log for the engines.

Append-only is enforced by the database itself: triggers refuse UPDATE and DELETE on the
events table, so no code path (including a bug) can rewrite history. Each event also stores
the hash of the previous event; verify_chain() recomputes the chain and reports the first
event that does not fit, which detects edits made with other tools.

This is evidence, not a security boundary: whoever controls the file can rebuild it. A
deployment that needs a stronger guarantee ships events to write-once storage.

Erasure (DECISIONS D46): events written since 2026-10-28 chain a digest of their payload (`payload_sha`), so once a
unit is listed in `erasures` (engine + scope) its payloads can be replaced by ERASED without breaking the chain; who
did what, and when, stays. Older events chain the payload itself and cannot be erased this way.
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
    """CREATE TABLE IF NOT EXISTS erasures (
        engine TEXT NOT NULL,
        unit TEXT NOT NULL,           -- the audit scope of what was erased, e.g. 'doc:0a1b2c3d4e5f'
        reason TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        completed_at TEXT,
        counts TEXT,
        PRIMARY KEY (engine, unit)
    )""",
    """CREATE TABLE IF NOT EXISTS legal_holds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        engine TEXT NOT NULL,
        unit TEXT NOT NULL,
        reason TEXT NOT NULL,
        placed_by TEXT NOT NULL,
        placed_at TEXT NOT NULL,
        released_by TEXT,
        released_at TEXT
    )""",
]
ERASED = '{"erased": true}'
# Rebuilt at every start so an older database gets the current rules (see the module docstring).
AUDIT_GUARDS = [
    "DROP TRIGGER IF EXISTS audit_no_update",
    f"""CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
       WHEN OLD.payload_sha = '' OR NEW.payload IS NOT '{ERASED}'
         OR NOT EXISTS (SELECT 1 FROM erasures e WHERE e.engine = OLD.engine AND e.unit = OLD.scope)
         OR NEW.id IS NOT OLD.id OR NEW.at IS NOT OLD.at OR NEW.engine IS NOT OLD.engine OR NEW.scope IS NOT OLD.scope
         OR NEW.actor IS NOT OLD.actor OR NEW.kind IS NOT OLD.kind OR NEW.prev_hash IS NOT OLD.prev_hash
         OR NEW.hash IS NOT OLD.hash OR NEW.payload_sha IS NOT OLD.payload_sha
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
    "DROP TRIGGER IF EXISTS audit_no_delete",
    """CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
    "DROP TRIGGER IF EXISTS erasures_no_delete",
    """CREATE TRIGGER erasures_no_delete BEFORE DELETE ON erasures
       BEGIN SELECT RAISE(ABORT, 'erasure records are kept'); END""",
    "DROP TRIGGER IF EXISTS erasures_no_rewrite",
    """CREATE TRIGGER erasures_no_rewrite BEFORE UPDATE ON erasures
       WHEN NEW.engine IS NOT OLD.engine OR NEW.unit IS NOT OLD.unit OR NEW.reason IS NOT OLD.reason
         OR NEW.requested_by IS NOT OLD.requested_by OR NEW.requested_at IS NOT OLD.requested_at
       BEGIN SELECT RAISE(ABORT, 'erasure records are kept'); END""",
    "DROP TRIGGER IF EXISTS legal_holds_no_delete",
    """CREATE TRIGGER legal_holds_no_delete BEFORE DELETE ON legal_holds
       BEGIN SELECT RAISE(ABORT, 'legal holds are released, never deleted'); END""",
]


def _payload_sha(body: str) -> str:
    import hashlib

    return hashlib.sha256(body.encode()).hexdigest()


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
            for stmt in AUDIT_SCHEMA:
                self.conn.execute(stmt)
            if "payload_sha" not in {r["name"] for r in self.conn.execute("PRAGMA table_info(audit_events)")}:
                self.conn.execute("DROP TRIGGER IF EXISTS audit_no_update")
                self.conn.execute("ALTER TABLE audit_events ADD COLUMN payload_sha TEXT NOT NULL DEFAULT ''")
            for stmt in AUDIT_GUARDS + (schema or []):
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
        ps = _payload_sha(body)
        h = content_hash([prev, at, engine, scope, actor, kind, "sha256:" + ps], 32)
        cur = conn.execute(
            "INSERT INTO audit_events (at, engine, scope, actor, kind, payload, prev_hash, hash, payload_sha)"
            " VALUES (?,?,?,?,?,?,?,?,?)", (at, engine, scope, actor, kind, body, prev, h, ps))
        return int(cur.lastrowid or 0)

    def events(self, engine: str, scope: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_events WHERE engine = ?" + (" AND scope = ?" if scope else "") + " ORDER BY id"
        rows = self.query(sql, (engine, scope) if scope else (engine,))
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def verify_chain(self) -> tuple[bool, int | None]:
        """(True, None) when every event's hash fits; else (False, id of the first that does not)."""
        prev = "genesis"
        erased = {(r["engine"], r["unit"]) for r in self.query("SELECT engine, unit FROM erasures")}
        for r in self.query("SELECT * FROM audit_events ORDER BY id"):
            ps = r["payload_sha"]
            covered = ("sha256:" + ps) if ps else r["payload"]  # events before 2026-10-28 chain the payload itself
            h = content_hash([prev, r["at"], r["engine"], r["scope"], r["actor"], r["kind"], covered], 32)
            if r["prev_hash"] != prev or r["hash"] != h:
                return False, int(r["id"])
            if ps and _payload_sha(r["payload"]) != ps and not (
                    r["payload"] == ERASED and (r["engine"], r["scope"]) in erased):
                return False, int(r["id"])
            prev = r["hash"]
        return True, None
