"""Scans, a person's reviews of findings and the findings export, in the platform's SQLite database.

A scan stores the workbook (and the earlier version, when one is given) by content hash and the scanner's result.
Scanning the same bytes under the same settings again returns the earlier scan. The workbook itself is never
changed: the scanner reads a copy in memory, and a person fixes the workbook in Excel.

Reviews: a person confirms a finding (it is a real problem to fix) or dismisses it (it is deliberate), with their
name and a reason. Reviews belong to a model (the workbook's name without its version, unless the uploader names
one) and are keyed by the finding's stable key, which uses labels rather than addresses. So a dismissal carries to
the next version of the same model, and stops applying when the formula or its labels change. Reviews are
append-only rows; the latest one for a key counts. A definite error cannot be dismissed: it must be fixed in the
workbook.
"""

from __future__ import annotations

import csv
import io
import json
import re
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from finops.core.audit import Database, now
from finops.core.config import ConfigError, load_config
from finops.core.exceptions import is_person
from finops.core.fingerprint import content_hash, sha256_bytes
from finops.core.vault import vault

from .config import ScanSpec
from .diff import Change, compare
from .scan import ENGINE_VERSION, Finding, scan_workbook
from .workbook import WorkbookError, load

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, stored_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sheet_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, name TEXT NOT NULL, sha256 TEXT NOT NULL,
        previous_name TEXT, previous_sha256 TEXT, config_version TEXT NOT NULL, engine_version TEXT NOT NULL,
        scan_key TEXT NOT NULL, status TEXT NOT NULL, error TEXT, at TEXT NOT NULL, actor TEXT NOT NULL,
        counts TEXT, result TEXT)""",
    """CREATE INDEX IF NOT EXISTS sheet_scans_key ON sheet_scans(scan_key, status)""",
    """CREATE TABLE IF NOT EXISTS sheet_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, finding_key TEXT NOT NULL, scan_id INTEGER NOT NULL,
        finding_id TEXT NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS sheet_reviews_no_update BEFORE UPDATE ON sheet_reviews
       BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS sheet_reviews_no_delete BEFORE DELETE ON sheet_reviews
       BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END""",
]
ACTIONS = {"confirm", "dismiss"}


class ActionError(ValueError):
    """A request the rules refuse; the message says why in plain words."""


class ScanResult(BaseModel):
    workbook: str
    sha256: str
    previous: str | None = None
    engine_version: str = ENGINE_VERSION
    config_version: str = ""
    sheets: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    change_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c = {s: sum(1 for f in self.findings if f.severity == s) for s in ("error", "risk", "anomaly")}
        c["material_changes"] = sum(1 for ch in self.changes if ch.material)
        c["formulas"] = sum(s["formulas"] for s in self.sheets)
        return c


def scan_bytes(name: str, data: bytes, spec: ScanSpec, version: str = "",
               previous: tuple[str, bytes] | None = None) -> ScanResult:
    wb = load(name, data, spec)
    findings, notes = scan_workbook(wb, spec)
    res = ScanResult(workbook=Path(name).name, sha256=wb.sha256, config_version=version, findings=findings, notes=notes,
                     sheets=[{"name": n, "state": wb.sheets[n].state, "cells": len(wb.sheets[n].cells),
                              "formulas": sum(1 for c in wb.sheets[n].cells.values() if c.kind == "formula")}
                             for n in wb.sheet_order])
    if previous is not None:
        old = load(previous[0], previous[1], spec)
        comp = compare(old, wb)
        res.previous = Path(previous[0]).name
        res.changes, res.change_summary = comp.changes, comp.summary
    return res


def model_name(file_name: str) -> str:
    """'Budget FY26 v3 (final).xlsx' -> 'budget fy26': the model a version belongs to."""
    stem = Path(file_name).stem.lower()
    stem = re.sub(r"[\s_-]*(\(.*?\)|v\d+|version\s*\d+|final|draft|copy|rev\s*\d+|\d{4}-\d{2}-\d{2})\s*$", "", stem)
    stem = re.sub(r"[\s_-]*(\(.*?\)|v\d+|final|draft|copy)\s*$", "", stem)
    return re.sub(r"\s+", " ", stem).strip(" -_") or "workbook"


def _safe(text: str) -> str:
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class SheetsService:
    def __init__(self, db: Database, files_dir: Path, config_path: Path):
        self.db = db
        self.files_dir = files_dir
        self.config_path = config_path
        self._lock = threading.Lock()
        with db.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    def spec(self) -> tuple[ScanSpec, str]:
        try:
            return load_config(ScanSpec, self.config_path)
        except ConfigError as exc:
            raise ActionError(f"The scanner configuration is invalid: {exc}") from exc

    def _store(self, name: str, data: bytes) -> str:
        sha = sha256_bytes(data)
        path = self.files_dir / sha
        if not path.exists():
            vault().write(path, data)
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO files (sha256, name, size, stored_at) VALUES (?,?,?,?)",
                      (sha, Path(name).name[:200], len(data), now()))
        return sha

    def scan(self, name: str, data: bytes, actor: str, previous: tuple[str, bytes] | None = None,
             model: str | None = None) -> int:
        spec, version = self.spec()
        model = (model or "").strip().lower() or model_name(name)
        key = content_hash([sha256_bytes(data), sha256_bytes(previous[1]) if previous else None, version, ENGINE_VERSION, model], 24)
        with self._lock:
            done = self.db.query("SELECT id FROM sheet_scans WHERE scan_key = ? AND status = 'succeeded' ORDER BY id DESC LIMIT 1", (key,))
            if done:
                return int(done[0]["id"])
            sha = self._store(name, data)
            psha = self._store(*previous) if previous else None
            try:
                res = scan_bytes(name, data, spec, version, previous)
                status, error = "succeeded", None
            except WorkbookError as exc:
                res, status, error = None, "failed", str(exc)
            with self.db.tx() as c:
                cur = c.execute("INSERT INTO sheet_scans (model, name, sha256, previous_name, previous_sha256, config_version, "
                                "engine_version, scan_key, status, error, at, actor, counts, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (model, Path(name).name, sha, Path(previous[0]).name if previous else None, psha, version,
                                 ENGINE_VERSION, key, status, error, now(), actor,
                                 json.dumps(res.counts()) if res else None, res.model_dump_json() if res else None))
                scan_id = int(cur.lastrowid or 0)
                self.db.append_event(c, "sheets", f"model:{model}", actor, f"scan_{status}",
                                     {"scan": scan_id, "workbook": Path(name).name, "sha256": sha,
                                      "counts": res.counts() if res else None, "error": error})
            if error:
                raise ActionError(error)
            return scan_id

    def scans(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT id, model, name, previous_name, status, error, at, actor, counts FROM sheet_scans "
                             "ORDER BY id DESC LIMIT 200")
        return [{**dict(r), "counts": json.loads(r["counts"]) if r["counts"] else None} for r in rows]

    def _row(self, scan_id: int) -> Any:
        rows = self.db.query("SELECT * FROM sheet_scans WHERE id = ?", (scan_id,))
        if not rows:
            raise ActionError(f"scan {scan_id} does not exist")
        return rows[0]

    def _reviews(self, model: str) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.db.query("SELECT * FROM sheet_reviews WHERE model = ? ORDER BY id", (model,)):
            latest[r["finding_key"]] = {k: r[k] for k in ("action", "note", "actor", "at", "scan_id")}
        return latest

    def get(self, scan_id: int) -> dict[str, Any]:
        row = self._row(scan_id)
        out = {k: row[k] for k in ("id", "model", "name", "previous_name", "config_version", "engine_version", "status",
                                   "error", "at", "actor")}
        out["counts"] = json.loads(row["counts"]) if row["counts"] else None
        res = json.loads(row["result"]) if row["result"] else None
        if res:
            reviews = self._reviews(row["model"])
            for f in res["findings"]:
                f["review"] = reviews.get(f["key"])
            open_ = [f for f in res["findings"] if f["severity"] != "anomaly" and not (f["review"] and f["review"]["action"] == "dismiss")]
            out["open"] = {s: sum(1 for f in open_ if f["severity"] == s) for s in ("error", "risk")}
        out["result"] = res
        return out

    def review(self, scan_id: int, finding_id: str, action: str, actor: str, note: str) -> dict[str, Any]:
        row = self._row(scan_id)
        if row["status"] != "succeeded":
            raise ActionError(f"scan {scan_id} did not succeed")
        if action not in ACTIONS:
            raise ActionError(f"'{action}' is not a review; use confirm or dismiss")
        if not is_person(actor):
            raise ActionError("A named reviewer must decide; automated or anonymous actors cannot.")
        if len(note.strip()) < 5:
            raise ActionError("Write the reason (what you checked).")
        res = ScanResult.model_validate_json(row["result"])
        f = next((x for x in res.findings if x.id == finding_id), None)
        if f is None:
            raise ActionError(f"finding {finding_id} is not in scan {scan_id}")
        if action == "dismiss" and f.severity == "error":
            raise ActionError("A definite error cannot be dismissed: fix it in the workbook and scan the new version.")
        with self.db.tx() as c:
            c.execute("INSERT INTO sheet_reviews (model, finding_key, scan_id, finding_id, action, note, actor, at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (row["model"], f.key, scan_id, finding_id, action, note.strip(), actor, now()))
            self.db.append_event(c, "sheets", f"model:{row['model']}", actor, f"finding_{action}",
                                 {"scan": scan_id, "finding": finding_id, "key": f.key, "note": note.strip()})
        return self.get(scan_id)

    def export(self, scan_id: int) -> tuple[str, bytes]:
        out = self.get(scan_id)
        res = out["result"]
        if not res:
            raise ActionError(f"scan {scan_id} did not succeed")
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["severity", "kind", "sheet", "cell", "also_in", "row_label", "column_label", "formula", "expected",
                    "detail", "dependents", "downstream", "feeds", "review", "reviewed_by", "review_note"])
        for f in res["findings"]:
            rv = f.get("review") or {}
            w.writerow([_safe(str(x)) for x in [f["severity"], f["kind"], f["sheet"] or "", f["cell"] or "", " ".join(f["group"]),
                        f["row_label"], f["column_label"], f["formula"] or "", f["expected"] or "", f["detail"], f["dependents"],
                        f["downstream"], " ".join(f["feeds"]), rv.get("action", ""), rv.get("actor", ""), rv.get("note", "")]])
        for ch in res["changes"]:
            if ch["material"]:
                w.writerow([_safe(str(x)) for x in ["change", ch["kind"], ch["sheet"], ch["cell"] or "", "", ch["row_label"],
                            ch["column_label"], ch["after"] or "", ch["before"] or "", ch["detail"], "", "", "", "", "", ""]])
        body = buf.getvalue().encode("utf-8")
        with self.db.tx() as c:
            self.db.append_event(c, "sheets", f"model:{out['model']}", "export", "exported",
                                 {"scan": scan_id, "sha256": sha256_bytes(body)})
        return f"{Path(out['name']).stem}-findings-scan{scan_id}.csv", body

    def events(self, model: str) -> list[dict[str, Any]]:
        return self.db.events("sheets", f"model:{model}")
