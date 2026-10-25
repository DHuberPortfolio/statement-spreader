"""Reconciliation workspaces: files, runs, human decisions and the audit trail, in SQLite.

Idempotency, concretely:
- A run's key is the hash of (left file bytes, right file bytes, effective configuration,
  engine version, number of decisions so far). Asking for a run whose key already succeeded
  returns that run; nothing is recomputed or duplicated, and the reuse is logged.
- Decisions are append-only rows (triggers refuse UPDATE and DELETE). The current state is a
  replay of them in order, so it can always be rebuilt and explained.
- Every decision names the run it was made on, and only the workspace's latest run accepts
  decisions: nobody can act on a stale screen.
- A run that crashes or is interrupted leaves a 'failed' row and no partial result; the next
  run with the same inputs succeeds normally.
- A changed file or configuration is recorded as an event naming what changed, and prior
  decisions are re-checked against the new data by the engine (see engine.py).
"""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from finops.core.audit import Database, now
from finops.core.config import ConfigError, load_config
from finops.core.exceptions import ExceptionStatus, Resolution, ResolutionError, check_resolution
from finops.core.fingerprint import content_hash, sha256_bytes

from .config import ReconProfile
from .engine import ENGINE_VERSION, Decisions, reconcile, summary
from .model import MatchStatus, ReconResult
from .normalize import ReconInputError

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, stored_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS recon_workspaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, profile TEXT NOT NULL,
        created_at TEXT NOT NULL, created_by TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS recon_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL REFERENCES recon_workspaces(id),
        run_key TEXT NOT NULL, left_file TEXT NOT NULL, right_file TEXT NOT NULL,
        config_version TEXT NOT NULL, engine_version TEXT NOT NULL, decisions_seen INTEGER NOT NULL,
        status TEXT NOT NULL, error TEXT, started_at TEXT NOT NULL, finished_at TEXT, actor TEXT NOT NULL,
        result TEXT)""",
    """DROP INDEX IF EXISTS recon_runs_key""",
    """CREATE INDEX IF NOT EXISTS recon_runs_lookup ON recon_runs(workspace_id, run_key, status)""",
    """CREATE TABLE IF NOT EXISTS recon_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL REFERENCES recon_workspaces(id),
        run_id INTEGER NOT NULL REFERENCES recon_runs(id), kind TEXT NOT NULL, payload TEXT NOT NULL,
        actor TEXT NOT NULL, at TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS recon_decisions_no_update BEFORE UPDATE ON recon_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS recon_decisions_no_delete BEFORE DELETE ON recon_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
]

RESOLUTIONS = {"explained", "corrected_in_source", "journal_entry_posted", "write_off_approved", "timing_will_clear",
               "not_an_issue"}


class ActionError(ValueError):
    """A request the rules refuse; the message says why in plain words."""


class ReconService:
    def __init__(self, db: Database, files_dir: Path, profiles_dir: Path):
        self.db = db
        self._run_lock = threading.Lock()  # one run at a time per service: no half-finished twins
        self.files_dir = files_dir
        self.profiles_dir = profiles_dir.resolve()
        with db.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    # -- workspaces and files --------------------------------------------------------------------

    def profiles(self) -> list[dict[str, str]]:
        out = []
        for p in sorted(self.profiles_dir.glob("*.yaml")):
            try:
                prof, version = load_config(ReconProfile, p)
                out.append({"file": p.name, "id": prof.id, "name": prof.name, "version": version})
            except ConfigError as exc:
                out.append({"file": p.name, "id": "", "name": "", "error": str(exc)})
        return out

    def _profile(self, name: str) -> tuple[ReconProfile, str]:
        path = (self.profiles_dir / name).resolve()
        if path.parent != self.profiles_dir or path.suffix != ".yaml":
            raise ActionError(f"'{name}' is not a profile in {self.profiles_dir.name}/")
        try:
            return load_config(ReconProfile, path)
        except ConfigError as exc:
            raise ActionError(f"The profile is invalid: {exc}") from exc

    def create_workspace(self, name: str, profile: str, actor: str) -> int:
        prof, version = self._profile(profile)
        with self.db.tx() as c:
            cur = c.execute("INSERT INTO recon_workspaces (name, profile, created_at, created_by) VALUES (?,?,?,?)",
                            (name.strip()[:120] or "Reconciliation", profile, now(), actor))
            wid = int(cur.lastrowid or 0)
            self.db.append_event(c, "recon", f"workspace:{wid}", actor, "workspace_created",
                                 {"name": name, "profile": profile, "profile_id": prof.id, "config_version": version})
        return wid

    def workspaces(self) -> list[dict[str, Any]]:
        rows = self.db.query("""SELECT w.*, (SELECT MAX(id) FROM recon_runs r WHERE r.workspace_id = w.id
                                AND r.status = 'succeeded') AS latest_run FROM recon_workspaces w ORDER BY w.id DESC""")
        return [dict(r) for r in rows]

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

    # -- runs ------------------------------------------------------------------------------------

    def latest_run_id(self, wid: int) -> int | None:
        r = self.db.query("SELECT MAX(id) AS id FROM recon_runs WHERE workspace_id = ? AND status = 'succeeded'", (wid,))
        return r[0]["id"] if r and r[0]["id"] is not None else None

    def _decision_rows(self, wid: int) -> list[dict[str, Any]]:
        return [{**dict(r), "payload": json.loads(r["payload"])}
                for r in self.db.query("SELECT * FROM recon_decisions WHERE workspace_id = ? ORDER BY id", (wid,))]

    def decisions(self, wid: int) -> Decisions:
        d = Decisions()
        accepted: dict[frozenset[str], dict[str, Any]] = {}
        for row in self._decision_rows(wid):
            p, kind = row["payload"], row["kind"]
            if kind in ("accept", "manual"):
                accepted[frozenset(p["left"] + p["right"])] = {"decision_id": row["id"], "at": row["at"],
                                                               "left": p["left"], "right": p["right"], "hashes": p["hashes"],
                                                               "actor": row["actor"], "note": p.get("note", ""), "kind": kind}
            elif kind == "reject":
                accepted.pop(frozenset(p["members"]), None)
                d.rejected.append({"members": p["members"], "hashes": p["hashes"]})
            elif kind == "resolve":
                d.resolutions[p["exception_id"]] = Resolution(action=p["action"], note=p.get("note", ""),
                                                              actor=row["actor"], at=row["at"])
        d.accepted = list(accepted.values())
        return d

    def run(self, wid: int, actor: str, left: tuple[str, bytes] | None = None, right: tuple[str, bytes] | None = None,
            _engine: Any = None) -> dict[str, Any]:
        with self._run_lock:
            return self._run(wid, actor, left, right, _engine)

    def _run(self, wid: int, actor: str, left: tuple[str, bytes] | None, right: tuple[str, bytes] | None,
             _engine: Any) -> dict[str, Any]:
        ws = self.db.query("SELECT * FROM recon_workspaces WHERE id = ?", (wid,))
        if not ws:
            raise ActionError(f"no reconciliation {wid}")
        prev_id = self.latest_run_id(wid)
        prev = dict(self.db.query("SELECT * FROM recon_runs WHERE id = ?", (prev_id,))[0]) if prev_id else None
        if (left is None or right is None) and prev is None:
            raise ActionError("Upload both files for the first run")
        left_sha = self.store_file(*left) if left else prev["left_file"]  # type: ignore[index]
        right_sha = self.store_file(*right) if right else prev["right_file"]  # type: ignore[index]
        profile, version = self._profile(ws[0]["profile"])
        n_dec = len(self._decision_rows(wid))
        key = content_hash([left_sha, right_sha, version, ENGINE_VERSION, n_dec], 24)

        done = self.db.query("SELECT id FROM recon_runs WHERE workspace_id = ? AND run_key = ? AND status = 'succeeded' "
                             "ORDER BY id DESC LIMIT 1", (wid, key))
        if done and done[0]["id"] == prev_id:  # the same request as the latest run: return it (an older match is recomputed,
            # so the result becomes the latest run and can be decided on)
            with self.db.tx() as c:
                self.db.append_event(c, "recon", f"workspace:{wid}", actor, "run_reused",
                                     {"run_id": done[0]["id"], "reason": "same files, configuration and decisions"})
            return {**self.get_run(done[0]["id"]), "reused": True}

        changes = []
        if prev:
            for what, old, new in (("bank/left file", prev["left_file"], left_sha), ("ledger/right file", prev["right_file"], right_sha),
                                   ("configuration", prev["config_version"], version), ("engine", prev["engine_version"], ENGINE_VERSION)):
                if old != new:
                    changes.append({"what": what, "from": old[:16], "to": new[:16]})
        with self.db.tx() as c:
            c.execute("UPDATE recon_runs SET status = 'failed', error = 'interrupted: the process stopped before this run finished', "
                      "finished_at = ? WHERE workspace_id = ? AND status = 'running'", (now(), wid))
            cur = c.execute("""INSERT INTO recon_runs (workspace_id, run_key, left_file, right_file, config_version,
                               engine_version, decisions_seen, status, started_at, actor) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (wid, key, left_sha, right_sha, version, ENGINE_VERSION, n_dec, "running", now(), actor))
            run_id = int(cur.lastrowid or 0)
            self.db.append_event(c, "recon", f"workspace:{wid}", actor, "run_started",
                                 {"run_id": run_id, "changes": changes, "decisions": n_dec})
        try:
            lname, ldata = self._file(left_sha)
            rname, rdata = self._file(right_sha)
            result: ReconResult = (_engine or reconcile)(lname, ldata, rname, rdata, profile, version, self.decisions(wid))
        except (ReconInputError, ValueError) as exc:
            self._fail(wid, run_id, actor, str(exc))
            raise ActionError(str(exc)) from exc
        except Exception as exc:
            self._fail(wid, run_id, actor, f"{type(exc).__name__}: {exc}")
            raise
        with self.db.tx() as c:
            c.execute("UPDATE recon_runs SET status = 'succeeded', error = NULL, finished_at = ?, result = ? WHERE id = ?",
                      (now(), result.model_dump_json(), run_id))
            self.db.append_event(c, "recon", f"workspace:{wid}", actor, "run_succeeded", {"run_id": run_id, **summary(result)})
        return {**self.get_run(run_id), "reused": False}

    def _fail(self, wid: int, run_id: int, actor: str, error: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE recon_runs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?", (error[:2000], now(), run_id))
            self.db.append_event(c, "recon", f"workspace:{wid}", actor, "run_failed", {"run_id": run_id, "error": error[:500]})

    def get_run(self, run_id: int) -> dict[str, Any]:
        rows = self.db.query("SELECT * FROM recon_runs WHERE id = ?", (run_id,))
        if not rows:
            raise ActionError(f"no run {run_id}")
        r = dict(rows[0])
        result = json.loads(r.pop("result")) if r.get("result") else None
        latest = self.latest_run_id(r["workspace_id"])
        ws = dict(self.db.query("SELECT * FROM recon_workspaces WHERE id = ?", (r["workspace_id"],))[0])
        names = {row["sha256"]: row["name"] for row in self.db.query(
            "SELECT sha256, name FROM files WHERE sha256 IN (?, ?)", (r["left_file"], r["right_file"]))}
        return {"run": {**r, "is_latest": r["id"] == latest, "left_name": names.get(r["left_file"]),
                        "right_name": names.get(r["right_file"])}, "workspace": ws, "result": result}

    def result(self, run_id: int) -> ReconResult:
        r = self.db.query("SELECT result FROM recon_runs WHERE id = ? AND status = 'succeeded'", (run_id,))
        if not r:
            raise ActionError(f"run {run_id} has no result")
        return ReconResult.model_validate_json(r[0]["result"])

    # -- decisions -------------------------------------------------------------------------------

    def _decide(self, run_id: int, kind: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        rows = self.db.query("SELECT workspace_id FROM recon_runs WHERE id = ? AND status = 'succeeded'", (run_id,))
        if not rows:
            raise ActionError(f"no finished run {run_id}")
        wid = rows[0]["workspace_id"]
        if self.latest_run_id(wid) != run_id:
            raise ActionError("This run is out of date: a newer run exists. Open the latest run and decide there.")
        with self.db.tx() as c:
            # Checked again inside the write transaction: two decisions sent at once on the same screen must not both
            # land (a run that already has a decision is stale; its successor is computed right after).
            latest = c.execute("SELECT MAX(id) AS id FROM recon_runs WHERE workspace_id = ? AND status = 'succeeded'", (wid,)).fetchone()
            taken = c.execute("SELECT COUNT(*) AS n FROM recon_decisions WHERE run_id = ?", (run_id,)).fetchone()
            if latest["id"] != run_id or taken["n"]:
                raise ActionError("This run is out of date: a decision was just made on it. Open the latest run and decide there.")
            c.execute("INSERT INTO recon_decisions (workspace_id, run_id, kind, payload, actor, at) VALUES (?,?,?,?,?,?)",
                      (wid, run_id, kind, json.dumps(payload, default=str), actor, now()))
            self.db.append_event(c, "recon", f"workspace:{wid}", actor, f"decision_{kind}", {"run_id": run_id, **payload})
        return self.run(wid, actor)

    @staticmethod
    def _person(actor: str) -> None:
        from finops.core.exceptions import is_person

        if not is_person(actor):
            raise ActionError("Decisions need a named reviewer (set your name first); automated actors cannot decide.")

    def accept(self, run_id: int, group_id: str, actor: str, note: str = "") -> dict[str, Any]:
        self._person(actor)
        res = self.result(run_id)
        g = next((g for g in res.groups if g.id == group_id), None)
        if g is None or g.status is not MatchStatus.PROPOSED:
            raise ActionError("Only a proposed match can be accepted")
        if g.difference != 0 and len(note.strip()) < 5:
            raise ActionError(f"This match differs by {g.difference}; write a note saying how the difference is handled.")
        members = g.left + g.right
        return self._decide(run_id, "accept", {"group_id": g.id, "left": g.left, "right": g.right, "note": note.strip(),
                                               "hashes": {m: res.records[m].content_hash for m in members},
                                               "difference": str(g.difference)}, actor)

    def reject(self, run_id: int, group_id: str, actor: str, note: str = "") -> dict[str, Any]:
        self._person(actor)
        res = self.result(run_id)
        g = next((g for g in res.groups if g.id == group_id), None)
        if g is None:
            raise ActionError("No such match in this run")
        if g.status is not MatchStatus.PROPOSED and len(note.strip()) < 5:
            raise ActionError("Undoing a match that was already accepted needs a note saying why.")
        members = g.left + g.right
        return self._decide(run_id, "reject", {"group_id": g.id, "members": members, "was": g.status.value, "note": note.strip(),
                                               "hashes": {m: res.records[m].content_hash for m in members}}, actor)

    def manual_match(self, run_id: int, left_ids: list[str], right_ids: list[str], actor: str, note: str) -> dict[str, Any]:
        self._person(actor)
        res = self.result(run_id)
        if not left_ids or not right_ids:
            raise ActionError(f"Pick at least one {res.left_label} record and one {res.right_label} record")
        if len(note.strip()) < 5:
            raise ActionError("A manual match needs a note saying what links the records.")
        gof = res.group_of()
        for rid, side in [(i, res.left_name) for i in left_ids] + [(i, res.right_name) for i in right_ids]:
            rec = res.records.get(rid)
            if rec is None or rec.source != side:
                raise ActionError(f"{rid} is not a {side} record in this run")
            if rid in gof and gof[rid].status is not MatchStatus.PROPOSED:
                raise ActionError(f"{rid} is already matched; undo that match first")
        if len({res.records[i].currency for i in left_ids + right_ids}) > 1:
            raise ActionError("Records in different currencies cannot be matched here")
        members = sorted(set(left_ids)) + sorted(set(right_ids))
        diff = sum((res.records[i].amount for i in set(left_ids)), Decimal(0)) - sum((res.records[i].amount for i in set(right_ids)), Decimal(0))
        return self._decide(run_id, "manual", {"left": sorted(set(left_ids)), "right": sorted(set(right_ids)), "note": note.strip(),
                                               "hashes": {m: res.records[m].content_hash for m in members},
                                               "difference": str(diff)}, actor)

    def resolve(self, run_id: int, exception_id: str, action: str, actor: str, note: str = "") -> dict[str, Any]:
        res = self.result(run_id)
        item = next((e for e in res.exceptions if e.id == exception_id), None)
        if item is None:
            raise ActionError("No such exception in this run")
        if item.status is not ExceptionStatus.OPEN:
            raise ActionError("This exception is already resolved")
        try:
            check_resolution(item, action, note, actor, RESOLUTIONS)
        except ResolutionError as exc:
            raise ActionError(str(exc)) from exc
        return self._decide(run_id, "resolve", {"exception_id": item.id, "code": item.code, "action": action,
                                                "note": note.strip(), "subjects": item.subjects}, actor)

    def events(self, wid: int) -> list[dict[str, Any]]:
        return self.db.events("recon", f"workspace:{wid}")
