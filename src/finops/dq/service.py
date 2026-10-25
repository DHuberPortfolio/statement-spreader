"""Gate runs, a person's decisions and the exports, in the platform's SQLite database.

Idempotency and history, as in the reconciliation service:
- Input files are stored by content hash. A run's key is the hash of (dataset configuration, engine version, every
  input file, reference file and snapshot, number of decisions so far); asking again for a run whose key already
  succeeded returns that run, so a retried upload never duplicates records or a load file.
- Decisions are append-only rows (the database refuses UPDATE and DELETE). Each decision starts a new run of the
  same inputs, so the screen always shows a state that the rules and the recorded decisions fully explain.
- Only a dataset's latest run accepts decisions: nobody acts on a stale screen.
- Exports are regenerated from the stored files and the decisions the run saw, and checked against the run's own
  counts before anything is written out.

Controls on people's decisions: a named person only (no "system" or "AI"), a written reason for every decision, a
release only for records held for review (a definite error must be corrected, not waved through), and two people for
a correction: whoever corrected a record cannot also release it.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from pathlib import Path
from typing import Any

from finops.core.audit import Database, now
from finops.core.config import ConfigError, load_config
from finops.core.exceptions import is_person, same_person
from finops.core.fingerprint import content_hash, sha256_bytes

from .config import DatasetSpec
from .engine import (
    ENGINE_VERSION,
    Decisions,
    GateInputError,
    GateResult,
    SourceInput,
    accepted_rows,
    gate,
    mask,
)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, stored_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS dq_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_file TEXT NOT NULL, dataset_id TEXT NOT NULL,
        config_version TEXT NOT NULL, engine_version TEXT NOT NULL, inputs TEXT NOT NULL, run_key TEXT NOT NULL,
        decisions_seen INTEGER NOT NULL, status TEXT NOT NULL, error TEXT, started_at TEXT NOT NULL,
        finished_at TEXT, actor TEXT NOT NULL, counts TEXT, result TEXT)""",
    """CREATE INDEX IF NOT EXISTS dq_runs_lookup ON dq_runs(dataset_id, run_key, status)""",
    """CREATE TABLE IF NOT EXISTS dq_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id TEXT NOT NULL, run_id INTEGER NOT NULL REFERENCES dq_runs(id),
        record_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS dq_decisions_no_update BEFORE UPDATE ON dq_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS dq_decisions_no_delete BEFORE DELETE ON dq_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
]
ACTIONS = {"release", "reject", "correct"}


class ActionError(ValueError):
    """A request the rules refuse; the message says why in plain words."""


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _safe(text: str) -> str:
    """For files people open in a spreadsheet: text that starts like a formula is written as plain text."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def quarantine_rows(result: GateResult) -> list[list[str]]:
    """Every record that did not go through, with where it came from, what was wrong and what the gate changed.
    Sensitive values are masked; text is made safe to open in a spreadsheet."""
    head = ["decision", "record_id", "source", "file", "sheet", "row", "codes", "reasons", "decided_by"] + result.columns + ["changes"]
    out = [head]
    for r in result.records:
        if r.decision in ("accepted",):
            continue
        out.append([r.decision, r.id, r.source_label, r.file, r.sheet or "", str(r.row),
                    "; ".join(sorted({i.code for i in r.issues})), " | ".join(i.message for i in r.issues), r.decided_by]
                   + [r.canonical.get(c, "") for c in result.columns]
                   + [" | ".join(f"{c.field}: '{c.before}' -> '{c.after}' ({c.step})" for c in r.changes)])
    return [[_safe(x) for x in row] for row in out]


class DQService:
    def __init__(self, db: Database, files_dir: Path, datasets_dir: Path):
        self.db = db
        self.files_dir = files_dir
        self.datasets_dir = datasets_dir.resolve()
        self._run_lock = threading.Lock()
        with db.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    # -- configuration and files -------------------------------------------------------------------------------------

    def datasets(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.datasets_dir.glob("*.yaml")):
            try:
                spec, version = load_config(DatasetSpec, p)
                out.append({"file": p.name, "id": spec.id, "name": spec.name, "version": version,
                            "sources": {k: s.label for k, s in spec.sources.items()},
                            "references": sorted({r.dataset for r in spec.references}),
                            "change_control": bool(spec.change_control)})
            except ConfigError as exc:
                out.append({"file": p.name, "error": str(exc)})
        return out

    def spec(self, file: str) -> tuple[DatasetSpec, str]:
        path = (self.datasets_dir / file).resolve()
        if path.parent != self.datasets_dir or path.suffix != ".yaml":
            raise ActionError(f"'{file}' is not a dataset configuration in {self.datasets_dir.name}/")
        try:
            return load_config(DatasetSpec, path)
        except ConfigError as exc:
            raise ActionError(f"The dataset configuration is invalid: {exc}") from exc

    def store_file(self, name: str, data: bytes) -> str:
        sha = sha256_bytes(data)
        path = self.files_dir / sha
        if not path.exists():
            self.files_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO files (sha256, name, size, stored_at) VALUES (?,?,?,?)",
                      (sha, Path(name).name[:200], len(data), now()))
        return sha

    def _file(self, sha: str) -> tuple[str, bytes]:
        row = self.db.query("SELECT name FROM files WHERE sha256 = ?", (sha,))
        if not row:
            raise ActionError(f"file {sha[:12]} is not stored")
        data = (self.files_dir / sha).read_bytes()
        if sha256_bytes(data) != sha:
            raise ActionError(f"stored file {sha[:12]} no longer matches its fingerprint")
        return row[0]["name"], data

    # -- decisions ---------------------------------------------------------------------------------------------------

    def _decision_rows(self, dataset_id: str, upto: int | None = None) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM dq_decisions WHERE dataset_id = ? ORDER BY id", (dataset_id,))
        out = [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]
        return out[:upto] if upto is not None else out

    @staticmethod
    def _replay(rows: list[dict[str, Any]]) -> Decisions:
        d = Decisions()
        for r in rows:
            p, rid, actor = r["payload"], r["record_id"], r["actor"]
            if r["kind"] == "release":
                d.releases[rid] = (p["fingerprint"], actor, p["note"])
                d.rejections.pop(rid, None)
            elif r["kind"] == "reject":
                d.rejections[rid] = (actor, p["note"])
                d.releases.pop(rid, None)
            elif r["kind"] == "correct":
                d.corrections.setdefault(rid, {})[p["field"]] = (p["value"], actor, p["note"])
                d.releases.pop(rid, None)  # a changed record needs a new release
        return d

    # -- runs --------------------------------------------------------------------------------------------------------

    def run(self, dataset_file: str, inputs: list[tuple[str, str, bytes]], actor: str,
            references: dict[str, tuple[str, bytes]] | None = None, previous: tuple[str, bytes] | None = None) -> int:
        """inputs: (source id, file name, bytes). references: dataset name -> (file name, bytes)."""
        spec, version = self.spec(dataset_file)
        if not inputs:
            raise ActionError("Give at least one source file")
        stored = {"inputs": [{"source": s, "name": Path(n).name, "sha": self.store_file(n, b)} for s, n, b in inputs],
                  "references": {k: {"name": Path(n).name, "sha": self.store_file(n, b)} for k, (n, b) in (references or {}).items()},
                  "previous": {"name": Path(previous[0]).name, "sha": self.store_file(*previous)} if previous else None}
        return self._run(dataset_file, spec, version, stored, actor)

    def _run(self, dataset_file: str, spec: DatasetSpec, version: str, stored: dict[str, Any], actor: str) -> int:
        with self._run_lock:
            decisions = self._decision_rows(spec.id)
            key = content_hash([dataset_file, version, ENGINE_VERSION, stored, len(decisions)], 24)
            done = self.db.query("SELECT id FROM dq_runs WHERE dataset_id = ? AND run_key = ? AND status = 'succeeded' "
                                 "ORDER BY id DESC LIMIT 1", (spec.id, key))
            if done:
                with self.db.tx() as c:
                    self.db.append_event(c, "dq", f"dataset:{spec.id}", actor, "run_reused", {"run": done[0]["id"]})
                return int(done[0]["id"])
            with self.db.tx() as c:
                cur = c.execute("INSERT INTO dq_runs (dataset_file, dataset_id, config_version, engine_version, inputs, run_key, "
                                "decisions_seen, status, started_at, actor) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (dataset_file, spec.id, version, ENGINE_VERSION, json.dumps(stored), key, len(decisions),
                                 "running", now(), actor))
                run_id = int(cur.lastrowid or 0)
            try:
                result = self._gate(spec, version, stored, self._replay(decisions))
            except (GateInputError, ActionError) as exc:
                self._finish(run_id, spec.id, actor, "failed", str(exc))
                raise ActionError(str(exc)) from exc
            except Exception as exc:
                self._finish(run_id, spec.id, actor, "failed", type(exc).__name__)
                raise
            self._finish(run_id, spec.id, actor, "succeeded", None, result)
            return run_id

    def _gate(self, spec: DatasetSpec, version: str, stored: dict[str, Any], decisions: Decisions) -> GateResult:
        inputs = [SourceInput(i["source"], i["name"], self._file(i["sha"])[1]) for i in stored["inputs"]]
        refs = {k: (v["name"], self._file(v["sha"])[1]) for k, v in stored["references"].items()}
        prev = (stored["previous"]["name"], self._file(stored["previous"]["sha"])[1]) if stored["previous"] else None
        return gate(spec, inputs, refs, prev, decisions, version)

    def _finish(self, run_id: int, dataset_id: str, actor: str, status: str, error: str | None,
                result: GateResult | None = None) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE dq_runs SET status = ?, error = ?, finished_at = ?, counts = ?, result = ? WHERE id = ?",
                      (status, error, now(), json.dumps(result.counts()) if result else None,
                       result.model_dump_json() if result else None, run_id))
            self.db.append_event(c, "dq", f"dataset:{dataset_id}", actor, f"run_{status}",
                                 {"run": run_id, "counts": result.counts() if result else None, "error": error})

    def runs(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT id, dataset_file, dataset_id, config_version, status, error, started_at, finished_at, actor, "
                             "counts, inputs FROM dq_runs ORDER BY id DESC LIMIT 200")
        return [{**dict(r), "counts": json.loads(r["counts"]) if r["counts"] else None, "inputs": json.loads(r["inputs"])} for r in rows]

    def latest_run_id(self, dataset_id: str) -> int | None:
        r = self.db.query("SELECT MAX(id) AS id FROM dq_runs WHERE dataset_id = ? AND status = 'succeeded'", (dataset_id,))
        return r[0]["id"] if r and r[0]["id"] is not None else None

    def _row(self, run_id: int) -> Any:
        rows = self.db.query("SELECT * FROM dq_runs WHERE id = ?", (run_id,))
        if not rows:
            raise ActionError(f"run {run_id} does not exist")
        return rows[0]

    def get(self, run_id: int) -> dict[str, Any]:
        row = self._row(run_id)
        out = {k: row[k] for k in ("id", "dataset_file", "dataset_id", "config_version", "engine_version", "status", "error",
                                   "started_at", "finished_at", "actor", "decisions_seen")}
        out["inputs"] = json.loads(row["inputs"])
        out["counts"] = json.loads(row["counts"]) if row["counts"] else None
        out["result"] = json.loads(row["result"]) if row["result"] else None
        out["latest"] = self.latest_run_id(row["dataset_id"]) == run_id
        out["decisions"] = [{k: d[k] for k in ("id", "record_id", "kind", "actor", "at")} | {"note": d["payload"].get("note", "")}
                            for d in self._decision_rows(row["dataset_id"])]
        return out

    def result(self, run_id: int) -> GateResult:
        """The run's result regenerated in memory (with real values for the export) and checked against the stored one."""
        row = self._row(run_id)
        if row["status"] != "succeeded":
            raise ActionError(f"run {run_id} did not succeed")
        spec, version = self.spec(row["dataset_file"])
        if version != row["config_version"]:
            raise ActionError("The dataset configuration changed since this run; run the gate again to export")
        stored = json.loads(row["inputs"])
        res = self._gate(spec, version, stored, self._replay(self._decision_rows(row["dataset_id"], row["decisions_seen"])))
        if res.counts() != json.loads(row["counts"]):
            raise ActionError("Re-running this run did not reproduce its result; nothing was exported")
        return res

    def export(self, run_id: int, kind: str) -> tuple[str, bytes]:
        res = self.result(run_id)
        row = self._row(run_id)
        if kind == "accepted":
            rows = accepted_rows(res)
            body = _csv([res.columns] + [[r.get(c, "") for c in res.columns] for r in rows])
            name = f"{row['dataset_id']}-accepted-run{run_id}.csv"
        elif kind == "quarantine":
            body, name = _csv(quarantine_rows(res)), f"{row['dataset_id']}-quarantine-run{run_id}.csv"
        else:
            raise ActionError("export is 'accepted' or 'quarantine'")
        with self.db.tx() as c:
            self.db.append_event(c, "dq", f"dataset:{row['dataset_id']}", "export", "exported",
                                 {"run": run_id, "kind": kind, "rows": body.count(b"\n") - 1, "sha256": sha256_bytes(body)})
        return name, body

    # -- a person's decisions ----------------------------------------------------------------------------------------

    def decide(self, run_id: int, record_id: str, action: str, actor: str, note: str,
               field: str | None = None, value: str | None = None) -> int:
        """Record a release, rejection or correction, then re-run the same inputs. Returns the new run's id."""
        row = self._row(run_id)
        if row["status"] != "succeeded":
            raise ActionError(f"run {run_id} did not succeed")
        if self.latest_run_id(row["dataset_id"]) != run_id:
            raise ActionError("A newer run of this dataset exists; decide on the latest run")
        if action not in ACTIONS:
            raise ActionError(f"'{action}' is not a decision; use one of: {', '.join(sorted(ACTIONS))}")
        if not is_person(actor):
            raise ActionError("A named reviewer must decide; automated or anonymous actors cannot.")
        if len(note.strip()) < 5:
            raise ActionError("Write the reason for the decision (what you checked).")
        result = GateResult.model_validate_json(row["result"])
        rec = next((r for r in result.records if r.id == record_id), None)
        if rec is None:
            raise ActionError(f"record {record_id} is not in run {run_id}")
        spec, version = self.spec(row["dataset_file"])
        earlier = [d for d in self._decision_rows(spec.id) if d["record_id"] == record_id]
        payload: dict[str, Any] = {"note": note.strip()}
        if action == "release":
            if rec.decision != "review":
                raise ActionError("Only a record held for review can be released; a rejected record must be corrected")
            if any(d["kind"] == "correct" and same_person(d["actor"], actor) for d in earlier):
                raise ActionError("You corrected this record; a second person must review and release it")
            payload["fingerprint"] = rec.review_fingerprint()
            payload["codes"] = sorted({i.code for i in rec.issues if i.severity == "review"})
        elif action == "reject":
            if rec.decision not in ("review",):
                raise ActionError("Only a record held for review can be rejected here")
        else:
            if rec.decision not in ("review", "rejected"):
                raise ActionError("Only a held record can be corrected here; fix accepted data in the source system")
            if field not in spec.fields:
                raise ActionError(f"'{field}' is not a field of {spec.name}")
            payload.update({"field": field, "value": (value or "").strip()})
        with self.db.tx() as c:
            # Checked again inside the write transaction: a decision someone made a moment ago (whose re-run has not
            # finished yet) makes this screen stale too.
            latest = c.execute("SELECT MAX(id) FROM dq_runs WHERE dataset_id = ? AND status = 'succeeded'", (spec.id,)).fetchone()[0]
            made = c.execute("SELECT COUNT(*) FROM dq_decisions WHERE dataset_id = ?", (spec.id,)).fetchone()[0]
            if latest != run_id or made != row["decisions_seen"]:
                raise ActionError("Someone decided on this dataset a moment ago; reload the latest run and decide there")
            c.execute("INSERT INTO dq_decisions (dataset_id, run_id, record_id, kind, payload, actor, at) VALUES (?,?,?,?,?,?,?)",
                      (spec.id, run_id, record_id, action, json.dumps(payload), actor, now()))
            logged = dict(payload)
            if action == "correct" and field and spec.fields[field].sensitive:
                logged["value"] = mask(logged["value"])
            self.db.append_event(c, "dq", f"dataset:{spec.id}", actor, f"decision_{action}", {"run": run_id, "record": record_id, **logged})
        return self._run(row["dataset_file"], spec, version, json.loads(row["inputs"]), actor)

    def events(self, dataset_id: str) -> list[dict[str, Any]]:
        return self.db.events("dq", f"dataset:{dataset_id}")
