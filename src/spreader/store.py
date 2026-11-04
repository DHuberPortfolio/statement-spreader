"""Persistence: documents, runs, an append-only audit log, reviewer mapping memory, timings.

SQLite (the standard library's sqlite3), one file under var/. Every write that changes a run
happens inside one transaction, so a crash leaves either the old state or the new one, never a
half-updated run. The audit log is append-only: corrections are new events, never edits.

Document bytes are stored as files named by their SHA-256, outside the database; uploading the
same file twice stores it once.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finops.core.vault import vault

SCHEMA_VERSION = 9

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
    """CREATE TRIGGER IF NOT EXISTS company_mappings_no_update BEFORE UPDATE ON company_mappings
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
        note TEXT,
        background INTEGER NOT NULL DEFAULT 0  -- review time recorded without a person starting anything (D65)
    )""",
    # Documents whose content was erased (retention or a deletion request, D46): the minimal record that it happened.
    """CREATE TABLE IF NOT EXISTS erasures (
        document_id TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        completed_at TEXT,
        counts TEXT
    )""",
    # The model's hidden second opinion on each row of a run (schema 6, DECISIONS D52). Kept apart from the run: it
    # never changes a spread and is never shown to analysts. Erased with the document (D46).
    """CREATE TABLE IF NOT EXISTS shadow_opinions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES runs(id),
        model_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        row_index INTEGER NOT NULL,
        label TEXT NOT NULL,
        section TEXT NOT NULL,
        platform_line TEXT,
        platform_excluded INTEGER NOT NULL,
        platform_rule TEXT NOT NULL,
        model_line TEXT,                   -- a line id, 'none', or NULL (no usable answer)
        outcome TEXT NOT NULL,             -- agree | disagree | no_answer
        created_at TEXT NOT NULL,
        UNIQUE (run_id, model_id, statement, row_index)
    )""",
    # Rows where the model's opinion differs from what the analyst approved, waiting for a senior's ruling (schema 7,
    # DECISIONS D53). Never shown to analysts; erased with the document (D46).
    """CREATE TABLE IF NOT EXISTS disagreements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opinion_id INTEGER NOT NULL UNIQUE REFERENCES shadow_opinions(id),
        run_id INTEGER NOT NULL REFERENCES runs(id),
        document_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        row_index INTEGER NOT NULL,
        label TEXT NOT NULL,
        section TEXT NOT NULL,
        analyst_line TEXT NOT NULL,        -- the approved placement; 'none' when the row was left off the spread
        analyst_rule TEXT NOT NULL,        -- the rule behind it (memory = a reviewer's remap)
        model_line TEXT NOT NULL,          -- a line id or 'none'
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL,
        due_at TEXT NOT NULL,              -- after this, without a ruling, the analyst's answer stands
        status TEXT NOT NULL,              -- open | analyst_stands | ruled | withdrawn (the approval was reopened)
        ruled_by TEXT,                     -- filled by the senior's ruling (step 3) or the deadline
        ruled_at TEXT,
        verdict TEXT,                      -- analyst | model | neither
        correct_line TEXT,
        reason TEXT,
        note TEXT,
        created_at TEXT NOT NULL
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


ERASED = '{"erased": true}'  # what an erased event's payload becomes (DECISIONS D46)

# Rebuilt at every start (DROP, then CREATE), so an older database gets the current rules. History is append-only;
# the one exception is erasure (D46): once a document is listed in `erasures`, its events' payloads may be replaced by
# ERASED (nothing else about the event may change) and its approved values and confirmed mappings may be deleted.
_DOC_OF_EVENT = "COALESCE(OLD.document_id, (SELECT document_id FROM runs WHERE id = OLD.run_id))"
GUARDS = [
    "DROP TRIGGER IF EXISTS events_no_update",
    f"""CREATE TRIGGER events_no_update BEFORE UPDATE ON events
       WHEN NOT EXISTS (SELECT 1 FROM erasures e WHERE e.document_id = {_DOC_OF_EVENT})
         OR NEW.payload IS NOT '{ERASED}' OR NEW.id IS NOT OLD.id OR NEW.run_id IS NOT OLD.run_id
         OR NEW.document_id IS NOT OLD.document_id OR NEW.at IS NOT OLD.at OR NEW.actor IS NOT OLD.actor
         OR NEW.kind IS NOT OLD.kind OR NEW.prev_hash IS NOT OLD.prev_hash OR NEW.hash IS NOT OLD.hash
         OR NEW.payload_sha IS NOT OLD.payload_sha
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
    "DROP TRIGGER IF EXISTS events_no_delete",
    """CREATE TRIGGER events_no_delete BEFORE DELETE ON events
       BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
    "DROP TRIGGER IF EXISTS approved_values_no_delete",
    """CREATE TRIGGER approved_values_no_delete BEFORE DELETE ON approved_values
       WHEN NOT EXISTS (SELECT 1 FROM erasures e WHERE e.document_id = OLD.document_id)
       BEGIN SELECT RAISE(ABORT, 'approved values are append-only'); END""",
    "DROP TRIGGER IF EXISTS company_mappings_no_delete",
    """CREATE TRIGGER company_mappings_no_delete BEFORE DELETE ON company_mappings
       WHEN NOT EXISTS (SELECT 1 FROM erasures e WHERE e.document_id = (SELECT document_id FROM runs WHERE id = OLD.run_id))
       BEGIN SELECT RAISE(ABORT, 'company mappings are append-only'); END""",
    "DROP TRIGGER IF EXISTS erasures_no_delete",
    """CREATE TRIGGER erasures_no_delete BEFORE DELETE ON erasures
       BEGIN SELECT RAISE(ABORT, 'erasure records are kept'); END""",
    "DROP TRIGGER IF EXISTS erasures_no_rewrite",
    """CREATE TRIGGER erasures_no_rewrite BEFORE UPDATE ON erasures
       WHEN NEW.document_id IS NOT OLD.document_id OR NEW.reason IS NOT OLD.reason
         OR NEW.requested_by IS NOT OLD.requested_by OR NEW.requested_at IS NOT OLD.requested_at
       BEGIN SELECT RAISE(ABORT, 'erasure records are kept'); END""",
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _event_hash(prev: str, r: Any, payload_sha: str) -> str:
    """The chain covers a digest of the payload, not the payload itself, so an erased payload (D46) leaves the chain
    intact while every other field stays covered."""
    body = json.dumps([prev, r["run_id"], r["document_id"], r["at"], r["actor"], r["kind"], payload_sha],
                      ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


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
            if "origin" not in {r["name"] for r in c.execute("PRAGMA table_info(documents)")}:
                # schema 8: what the document is, for the screens (D63): sec | generated | uploaded; NULL until looked at
                for col in ("company_name", "filing", "origin"):
                    c.execute(f"ALTER TABLE documents ADD COLUMN {col} TEXT")
            ws = {r["name"] for r in c.execute("PRAGMA table_info(work_sessions)")}
            for col in ("difficulty", "analyst_experience"):  # schema 5: pilot context (PILOT_PROTOCOL.md)
                if col not in ws:
                    c.execute(f"ALTER TABLE work_sessions ADD COLUMN {col} TEXT")
            if "background" not in {r["name"] for r in c.execute("PRAGMA table_info(work_sessions)")}:
                c.execute("ALTER TABLE work_sessions ADD COLUMN background INTEGER NOT NULL DEFAULT 0")  # schema 9 (D65)
            if "hash" not in {r["name"] for r in c.execute("PRAGMA table_info(events)")}:
                # schema 4: the audit log becomes a hash chain that refuses edits (DECISIONS D44). Events written before
                # this migration are chained as they are now: later edits to them are detected, earlier ones cannot be.
                c.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''")
                c.execute("ALTER TABLE events ADD COLUMN hash TEXT NOT NULL DEFAULT ''")
                c.execute("ALTER TABLE events ADD COLUMN payload_sha TEXT NOT NULL DEFAULT ''")
                c.execute("DROP TRIGGER IF EXISTS events_no_update")
                prev = "genesis"
                legacy = c.execute("SELECT * FROM events ORDER BY id").fetchall()
                for r in legacy:
                    ps = _sha(r["payload"])
                    h = _event_hash(prev, r, ps)
                    c.execute("UPDATE events SET prev_hash=?, hash=?, payload_sha=? WHERE id=?", (prev, h, ps, r["id"]))
                    prev = h
                c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('chain_legacy_events', ?)", (str(len(legacy)),))
            for stmt in GUARDS:
                c.execute(stmt)
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
            vault().write(blob, data)  # encrypted when a data key is configured (D45); atomic on the same volume
        with self.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO documents(id, filename, format, size, uploaded_at) VALUES (?,?,?,?,?)",
                            (doc_id, filename, fmt, len(data), now()))
            return cur.rowcount == 1

    def document_bytes(self, doc_id: str, fmt: str) -> bytes:
        ext = {"html": "htm", "pdf": "pdf", "xlsx": "xlsx"}[fmt]
        return vault().read(self.blob_dir / f"{doc_id}.{ext}")

    def document(self, doc_id: str) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM documents WHERE id=?", (doc_id,))
        return rows[0] if rows else None

    # ---- events ----
    def log(self, c: sqlite3.Connection, kind: str, payload: dict[str, Any], actor: str,
            run_id: int | None = None, document_id: str | None = None) -> None:
        """Append an event inside the caller's transaction, chained to the one before it."""
        last = c.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "genesis"
        row = {"run_id": run_id, "document_id": document_id, "at": now(), "actor": actor, "kind": kind,
               "payload": json.dumps(payload, default=str)}
        ps = _sha(row["payload"])
        c.execute("INSERT INTO events(run_id, document_id, at, actor, kind, payload, prev_hash, hash, payload_sha)"
                  " VALUES (?,?,?,?,?,?,?,?,?)",
                  (row["run_id"], row["document_id"], row["at"], actor, kind, row["payload"], prev,
                   _event_hash(prev, row, ps), ps))

    def verify_chain(self) -> tuple[bool, int | None]:
        """(True, None) if every event still fits the chain; else (False, id of the first that does not).

        Detects an edit, insertion or deletion made with other tools. It cannot stop someone who controls the file
        from rebuilding the whole chain: that needs a copy of the latest hash kept elsewhere (THREAT_MODEL T41)."""
        prev = "genesis"
        erased = {r["document_id"] for r in self.query("SELECT document_id FROM erasures")}
        run_doc = {r["id"]: r["document_id"] for r in self.query("SELECT id, document_id FROM runs")}
        for r in self.query("SELECT * FROM events ORDER BY id"):
            if r["prev_hash"] != prev or r["hash"] != _event_hash(prev, r, r["payload_sha"]):
                return False, int(r["id"])
            doc = r["document_id"] or run_doc.get(r["run_id"])
            if _sha(r["payload"]) != r["payload_sha"] and not (r["payload"] == ERASED and doc in erased):
                return False, int(r["id"])
            prev = r["hash"]
        return True, None

    def chain_head(self) -> dict[str, Any]:
        """The latest event id and hash: copy it somewhere the database's owner cannot write, to detect a rebuild."""
        rows = self.query("SELECT id, hash FROM events ORDER BY id DESC LIMIT 1")
        return {"id": int(rows[0]["id"]), "hash": rows[0]["hash"]} if rows else {"id": 0, "hash": "genesis"}

    # ---- memory ----
    def memory_rows(self, profile_id: str) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM mapping_memory WHERE profile_id=?", (profile_id,))

    def memory_version(self, profile_id: str) -> int:
        rows = self.query("SELECT COUNT(*) AS n, COALESCE(MAX(rowid), 0) AS m FROM mapping_memory WHERE profile_id=?",
                          (profile_id,))
        r = rows[0]
        return int(r["n"]) * 100000 + int(r["m"])
