"""Consistent backups, restore checks and audit anchors (DECISIONS D47).

`backup` takes a consistent copy of a running platform: both SQLite databases through SQLite's online backup API (a
snapshot that never contains half a transaction, taken while the app keeps serving) and every stored file exactly
as stored (encrypted when a data key is configured; the key is never copied). A manifest records each file's SHA-256
and both audit chains' heads.

`verify_backup` checks a backup without changing it: every file against the manifest, and both audit chains (on a
temporary copy, because opening a database upgrades it).

An *anchor* is the latest event id and hash of both audit chains, written somewhere the database's owner cannot
change (another system, a ticket, an email to audit). `check_anchor` later proves the chains still contain those
events unchanged: someone who rebuilds a chain from an earlier point cannot keep an anchored hash. This is what turns
the hash chain from "detects partial edits" into "detects a rebuild of anything before the last anchor" (T41).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .audit import Database, now

DATABASES = ("spreader.sqlite3", "finops.sqlite3")
FILE_DIRS = ("documents", "finops-files")


class BackupError(Exception):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def anchor(data_dir: Path) -> dict[str, Any]:
    from spreader.store import Store

    out: dict[str, Any] = {"at": now(), "statement": Store(data_dir / "spreader.sqlite3").chain_head()}
    db = Database(data_dir / "finops.sqlite3")
    rows = db.query("SELECT id, hash FROM audit_events ORDER BY id DESC LIMIT 1")
    out["platform"] = {"id": int(rows[0]["id"]), "hash": rows[0]["hash"]} if rows else {"id": 0, "hash": "genesis"}
    return out


def check_anchor(data_dir: Path, a: dict[str, Any]) -> list[str]:
    """Problems found (empty: both chains verify and still hold the anchored events unchanged)."""
    from spreader.store import Store

    problems = []
    store, db = Store(data_dir / "spreader.sqlite3"), Database(data_dir / "finops.sqlite3")
    for name, (ok, bad) in {"statement": store.verify_chain(), "platform": db.verify_chain()}.items():
        if not ok:
            problems.append(f"{name} chain broken at event {bad}")
    for name, query in {"statement": store.query, "platform": db.query}.items():
        head = a.get(name) or {}
        if not head.get("id"):
            continue
        table = "events" if name == "statement" else "audit_events"
        rows = query(f"SELECT hash FROM {table} WHERE id = ?", (int(head["id"]),))
        if not rows or rows[0]["hash"] != head["hash"]:
            problems.append(f"{name} event {head['id']} no longer matches the anchor taken at {a.get('at')}: "
                            "the history before it was rewritten")
    return problems


def backup(data_dir: Path, out_dir: Path) -> dict[str, Any]:
    data_dir, out_dir = data_dir.resolve(), out_dir.resolve()
    if out_dir == data_dir or data_dir in out_dir.parents:
        raise BackupError("Write the backup outside the data folder")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise BackupError(f"{out_dir} is not empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in DATABASES:
        src = data_dir / name
        if not src.exists():
            continue
        with sqlite3.connect(src) as s, sqlite3.connect(out_dir / name) as d:
            s.backup(d)  # consistent snapshot while the app keeps running
        d.close()
        s.close()
    files: dict[str, str] = {}
    for folder in FILE_DIRS:
        for p in sorted((data_dir / folder).rglob("*")) if (data_dir / folder).exists() else []:
            if p.is_file() and not p.name.endswith(".tmp"):
                rel = p.relative_to(data_dir).as_posix()
                (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out_dir / rel)
                files[rel] = _sha(out_dir / rel)
    manifest = {"created_at": now(), "source": str(data_dir), "databases": [n for n in DATABASES if (out_dir / n).exists()],
                "files": files, "database_sha256": {n: _sha(out_dir / n) for n in DATABASES if (out_dir / n).exists()},
                "anchor": anchor(out_dir_copy(out_dir)), "key_included": False}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def out_dir_copy(out_dir: Path) -> Path:
    """A throwaway copy of the backup's databases (opening one upgrades it, and a backup must stay as taken)."""
    tmp = Path(tempfile.mkdtemp(prefix="backup-check-"))
    for n in DATABASES:
        if (out_dir / n).exists():
            shutil.copy2(out_dir / n, tmp / n)
    return tmp


def verify_backup(out_dir: Path) -> list[str]:
    mf = out_dir / "manifest.json"
    if not mf.exists():
        return ["no manifest.json: not a backup made by `spreader backup`"]
    m = json.loads(mf.read_text(encoding="utf-8"))
    problems = []
    for rel, sha in m["files"].items():
        p = out_dir / rel
        if not p.exists():
            problems.append(f"missing {rel}")
        elif _sha(p) != sha:
            problems.append(f"changed since the backup: {rel}")
    for n, sha in m.get("database_sha256", {}).items():
        if _sha(out_dir / n) != sha:
            problems.append(f"changed since the backup: {n}")
    problems += check_anchor(out_dir_copy(out_dir), m["anchor"])
    return problems
