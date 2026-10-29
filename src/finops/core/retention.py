"""Retention, erasure and legal holds (DECISIONS D46; inventory in DATA_LIFECYCLE.md).

What is deleted is a *unit*, the thing a person uploads and works on:

| engine     | unit                       | audit scope                |
|------------|----------------------------|----------------------------|
| statement  | a statement document       | events with its document id (statement database) |
| invoice    | an invoice document        | `doc:<first 12 hex>`       |
| recon      | a reconciliation workspace | `workspace:<id>`           |
| dq         | a data-quality dataset     | `dataset:<id>`             |
| sheets     | a workbook model           | `model:<name>`             |

Erasing a unit removes its business content: the stored files (unless another live unit uses the same file), file
names, extracted values, spreads and results, review notes and decisions, company memory it left behind, reviewer
outcomes that point at it, and the payloads of its audit events. What stays is the minimal record that work and the
erasure happened: event kinds, actors and times, content hashes, and a row in `erasures` with who asked and why.

A unit under a legal hold is never erased. A retention period of None never deletes anything automatically, which
is the default: an organisation sets its own periods (config/finops/retention/*.yaml); there is no universal one.

Every step is idempotent. An erasure is recorded as started before anything is removed and as completed after the
files are gone, so an interrupted erasure is visible (`completed_at` empty) and running it again finishes it.
"""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .audit import ERASED, Database, now
from .config import load_config

ENGINES = ("statement", "invoice", "recon", "dq", "sheets")
ERASED_NAME = "[erased]"


class RetentionError(Exception):
    pass


class HoldError(RetentionError):
    """The unit is under a legal hold."""


class ClassPolicy(BaseModel):
    keep_days: int | None = Field(default=None, ge=1)  # after the unit's last activity; None: never automatically


class RetentionPolicy(BaseModel):
    statement: ClassPolicy = Field(default_factory=ClassPolicy)
    invoice: ClassPolicy = Field(default_factory=ClassPolicy)
    recon: ClassPolicy = Field(default_factory=ClassPolicy)
    dq: ClassPolicy = Field(default_factory=ClassPolicy)
    sheets: ClassPolicy = Field(default_factory=ClassPolicy)
    temporary_files_hours: int = Field(default=24, ge=1)
    ended_sessions_days: int = Field(default=30, ge=1)


def load_policy(path: str | Path) -> RetentionPolicy:
    return load_config(RetentionPolicy, path)[0]


def operator() -> str:
    """Who runs a command-line job: the operating-system account (the CLI already has the data folder)."""
    try:
        return f"cli:{getpass.getuser()}"
    except Exception:  # noqa: BLE001
        return "cli:unknown"


@dataclass
class Unit:
    engine: str
    unit: str
    last_activity: str
    label: str = ""


@dataclass
class Platform:
    """Where everything lives: the statement store, the platform database and the data folder."""
    store: Any  # spreader.store.Store
    db: Database
    data_dir: Path
    outcomes_dir: Path | None = None
    files: dict[str, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        fd = self.data_dir / "finops-files"
        self.files = {"recon": fd, "invoice": fd / "invoices", "dq": fd / "dq", "sheets": fd / "sheets"}


# -- legal holds --------------------------------------------------------------------------------------------------


def place_hold(db: Database, engine: str, unit: str, reason: str, actor: str) -> int:
    if engine not in ENGINES:
        raise RetentionError(f"Unknown engine '{engine}'")
    if len(reason.strip()) < 5:
        raise RetentionError("A legal hold needs a reason (the matter or instruction it serves)")
    with db.tx() as c:
        cur = c.execute("INSERT INTO legal_holds (engine, unit, reason, placed_by, placed_at) VALUES (?,?,?,?,?)",
                        (engine, unit, reason.strip()[:500], actor, now()))
        db.append_event(c, "retention", "holds", actor, "hold_placed", {"engine": engine, "unit": unit, "hold": cur.lastrowid})
    return int(cur.lastrowid or 0)


def release_hold(db: Database, hold_id: int, actor: str, note: str) -> None:
    if len(note.strip()) < 5:
        raise RetentionError("Releasing a hold needs a note (who authorised it)")
    with db.tx() as c:
        row = c.execute("SELECT * FROM legal_holds WHERE id = ? AND released_at IS NULL", (hold_id,)).fetchone()
        if row is None:
            raise RetentionError("No active hold with that id")
        c.execute("UPDATE legal_holds SET released_by = ?, released_at = ? WHERE id = ?", (actor, now(), hold_id))
        db.append_event(c, "retention", "holds", actor, "hold_released",
                        {"engine": row["engine"], "unit": row["unit"], "hold": hold_id, "note": note.strip()[:500]})


def holds(db: Database, active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM legal_holds" + (" WHERE released_at IS NULL" if active_only else "") + " ORDER BY id"
    return [dict(r) for r in db.query(sql)]


def is_held(db: Database, engine: str, unit: str) -> bool:
    return bool(db.query("SELECT 1 FROM legal_holds WHERE engine = ? AND unit = ? AND released_at IS NULL",
                         (engine, unit)))


# -- units --------------------------------------------------------------------------------------------------------


def _tables(db: Database) -> set[str]:
    return {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}


def units(p: Platform) -> list[Unit]:
    """Every unit that holds content (not yet erased), with its last activity."""
    out: list[Unit] = []
    erased_docs = {r["document_id"] for r in p.store.query("SELECT document_id FROM erasures")}
    for r in p.store.query("SELECT d.id, d.uploaded_at, (SELECT MAX(COALESCE(finished_at, started_at)) FROM runs "
                           "WHERE document_id = d.id) AS last_run FROM documents d"):
        if r["id"] not in erased_docs:
            out.append(Unit("statement", r["id"], max(filter(None, [r["uploaded_at"], r["last_run"]]))))
    erased = {(r["engine"], r["unit"]) for r in p.db.query("SELECT engine, unit FROM erasures")}
    t = _tables(p.db)
    queries = {
        "invoice": ("inv_documents", "SELECT 'doc:' || substr(doc_id, 1, 12) AS unit, MAX(uploaded_at) AS last "
                    "FROM inv_documents GROUP BY unit"),
        "recon": ("recon_workspaces", "SELECT 'workspace:' || w.id AS unit, MAX(COALESCE(r.finished_at, w.created_at)) "
                  "AS last FROM recon_workspaces w LEFT JOIN recon_runs r ON r.workspace_id = w.id GROUP BY w.id"),
        "dq": ("dq_runs", "SELECT 'dataset:' || dataset_id AS unit, MAX(started_at) AS last FROM dq_runs GROUP BY dataset_id"),
        "sheets": ("sheet_scans", "SELECT 'model:' || model AS unit, MAX(at) AS last FROM sheet_scans GROUP BY model"),
    }
    for engine, (table, sql) in queries.items():
        if table in t:
            out += [Unit(engine, r["unit"], r["last"]) for r in p.db.query(sql) if (engine, r["unit"]) not in erased]
    return out


def due(p: Platform, policy: RetentionPolicy, at: datetime | None = None) -> list[Unit]:
    """Units past their retention period and not under a legal hold."""
    at = at or datetime.now(UTC)
    out = []
    for u in units(p):
        days = getattr(policy, u.engine).keep_days
        if days is None or is_held(p.db, u.engine, u.unit):
            continue
        last = datetime.fromisoformat(u.last_activity)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if at - last > timedelta(days=days):
            out.append(u)
    return out


# -- erasure ------------------------------------------------------------------------------------------------------

_GATED = {  # append-only decision tables: deletions allowed only for an erased unit
    "recon_decisions": ("recon", "'workspace:' || OLD.workspace_id", "decisions are append-only"),
    "inv_decisions": ("invoice", "'doc:' || substr(OLD.doc_id, 1, 12)", "decisions are append-only"),
    "dq_decisions": ("dq", "'dataset:' || OLD.dataset_id", "decisions are append-only"),
    "sheet_reviews": ("sheets", "'model:' || OLD.model", "reviews are append-only"),
}


def ensure_gates(db: Database) -> None:
    """Replace the engines' unconditional no-delete triggers with ones that allow deletion only for erased units."""
    t = _tables(db)
    with db.tx() as c:
        for table, (engine, unit_sql, msg) in _GATED.items():
            if table not in t:
                continue
            name = f"{table}_no_delete"
            c.execute(f"DROP TRIGGER IF EXISTS {name}")
            c.execute(f"""CREATE TRIGGER {name} BEFORE DELETE ON {table}
                WHEN NOT EXISTS (SELECT 1 FROM erasures e WHERE e.engine = '{engine}' AND e.unit = {unit_sql})
                BEGIN SELECT RAISE(ABORT, '{msg}'); END""")


def erase(p: Platform, engine: str, unit: str, reason: str, actor: str) -> dict[str, int]:
    """Erase one unit's content (see the module docstring). Refused under a legal hold; safe to run again."""
    if engine not in ENGINES:
        raise RetentionError(f"Unknown engine '{engine}'")
    if len(reason.strip()) < 5:
        raise RetentionError("An erasure needs a reason (the retention rule or the request it serves)")
    if is_held(p.db, engine, unit):
        raise HoldError(f"{engine} {unit} is under a legal hold")
    counts = _erase_statement(p, unit, reason, actor) if engine == "statement" else _erase_platform(p, engine, unit, reason, actor)
    counts["outcome_lines"] = _erase_outcomes(p, engine, unit)
    counts["files"] = _delete_unreferenced_files(p, engine, unit)
    when = now()
    if engine == "statement":
        with p.store.tx() as c:
            c.execute("UPDATE erasures SET completed_at = ?, counts = ? WHERE document_id = ?", (when, json.dumps(counts), unit))
    else:
        with p.db.tx() as c:
            c.execute("UPDATE erasures SET completed_at = ?, counts = ? WHERE engine = ? AND unit = ?",
                      (when, json.dumps(counts), engine, unit))
    with p.db.tx() as c:
        p.db.append_event(c, "retention", "erasures", actor, "erased", {"engine": engine, "unit": unit, "counts": counts,
                                                                         "reason": reason.strip()[:500]})
    return counts


def _erase_statement(p: Platform, doc_id: str, reason: str, actor: str) -> dict[str, int]:
    store = p.store
    if not store.query("SELECT 1 FROM documents WHERE id = ?", (doc_id,)):
        raise RetentionError("Unknown statement document")
    from spreader.store import ERASED as S_ERASED

    with store.tx() as c:
        c.execute("INSERT OR IGNORE INTO erasures (document_id, reason, requested_by, requested_at) VALUES (?,?,?,?)",
                  (doc_id, reason.strip()[:500], actor, now()))
        runs = [r["id"] for r in c.execute("SELECT id FROM runs WHERE document_id = ?", (doc_id,))]
        marks = ",".join("?" * len(runs)) or "NULL"
        n = {}
        n["audit_payloads"] = c.execute(
            f"UPDATE events SET payload = ? WHERE (document_id = ? OR run_id IN ({marks})) AND payload != ?",
            (S_ERASED, doc_id, *runs, S_ERASED)).rowcount
        n["approved_values"] = c.execute("DELETE FROM approved_values WHERE document_id = ?", (doc_id,)).rowcount
        n["company_mappings"] = c.execute(f"DELETE FROM company_mappings WHERE run_id IN ({marks})", tuple(runs)).rowcount
        n["shadow_opinions"] = c.execute(f"DELETE FROM shadow_opinions WHERE run_id IN ({marks})", tuple(runs)).rowcount
        n["runs"] = c.execute("UPDATE runs SET spread = NULL, state = '{}', error = NULL, timings = NULL "
                              "WHERE document_id = ?", (doc_id,)).rowcount
        c.execute("UPDATE documents SET filename = ?, label = NULL, company_id = NULL WHERE id = ?", (ERASED_NAME, doc_id))
        n["work_session_notes"] = c.execute("UPDATE work_sessions SET note = NULL WHERE document_id = ? AND note IS NOT NULL",
                                            (doc_id,)).rowcount
    return n


def _erase_platform(p: Platform, engine: str, unit: str, reason: str, actor: str) -> dict[str, int]:
    db = p.db
    ensure_gates(db)
    t = _tables(db)
    kind, _, key = unit.partition(":")
    n: dict[str, int] = {}
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO erasures (engine, unit, reason, requested_by, requested_at) VALUES (?,?,?,?,?)",
                  (engine, unit, reason.strip()[:500], actor, now()))
        n["audit_payloads"] = c.execute(
            "UPDATE audit_events SET payload = ? WHERE engine = ? AND scope = ? AND payload_sha != '' AND payload != ?",
            (ERASED, engine, unit, ERASED)).rowcount
        n["audit_payloads_not_erasable"] = c.execute(  # written before 2026-10-28 (module docstring of finops.core.audit)
            "SELECT COUNT(*) FROM audit_events WHERE engine = ? AND scope = ? AND payload_sha = ''", (engine, unit)).fetchone()[0]
        if engine == "invoice" and kind == "doc" and "inv_documents" in t:
            docs = [r["doc_id"] for r in c.execute("SELECT doc_id FROM inv_documents WHERE substr(doc_id, 1, 12) = ?", (key,))]
            if not docs:
                raise RetentionError("Unknown invoice document")
            marks = ",".join("?" * len(docs))
            n["results"] = c.execute(f"UPDATE inv_outcomes SET outcome = ? WHERE doc_id IN ({marks})", (ERASED, *docs)).rowcount
            n["decisions"] = c.execute(f"DELETE FROM inv_decisions WHERE doc_id IN ({marks})", tuple(docs)).rowcount
            c.execute(f"UPDATE inv_documents SET name = ? WHERE doc_id IN ({marks})", (ERASED_NAME, *docs))
        elif engine == "recon" and kind == "workspace" and "recon_workspaces" in t:
            if not c.execute("SELECT 1 FROM recon_workspaces WHERE id = ?", (key,)).fetchone():
                raise RetentionError("Unknown reconciliation workspace")
            n["results"] = c.execute("UPDATE recon_runs SET result = ?, error = NULL WHERE workspace_id = ?", (ERASED, key)).rowcount
            n["decisions"] = c.execute("DELETE FROM recon_decisions WHERE workspace_id = ?", (key,)).rowcount
            c.execute("UPDATE recon_workspaces SET name = ? WHERE id = ?", (ERASED_NAME, key))
        elif engine == "dq" and kind == "dataset" and "dq_runs" in t:
            if not c.execute("SELECT 1 FROM dq_runs WHERE dataset_id = ?", (key,)).fetchone():
                raise RetentionError("Unknown data-quality dataset")
            for r in c.execute("SELECT id, inputs FROM dq_runs WHERE dataset_id = ?", (key,)).fetchall():
                kept = _shas(r["inputs"])
                c.execute("UPDATE dq_runs SET inputs = ? WHERE id = ?", (json.dumps({"erased": True, "shas": kept}), r["id"]))
            n["results"] = c.execute("UPDATE dq_runs SET result = ?, error = NULL WHERE dataset_id = ?", (ERASED, key)).rowcount
            n["decisions"] = c.execute("DELETE FROM dq_decisions WHERE dataset_id = ?", (key,)).rowcount
        elif engine == "sheets" and kind == "model" and "sheet_scans" in t:
            if not c.execute("SELECT 1 FROM sheet_scans WHERE model = ?", (key,)).fetchone():
                raise RetentionError("Unknown workbook model")
            n["results"] = c.execute("UPDATE sheet_scans SET result = ?, error = NULL, name = ?, previous_name = "
                                     "CASE WHEN previous_name IS NULL THEN NULL ELSE ? END WHERE model = ?",
                                     (ERASED, ERASED_NAME, ERASED_NAME, key)).rowcount
            n["decisions"] = c.execute("DELETE FROM sheet_reviews WHERE model = ?", (key,)).rowcount
        else:
            raise RetentionError(f"'{unit}' is not a {engine} unit")
    return n


def _shas(raw: Any) -> list[str]:
    """Every 64-hex value in a JSON document (the stored files a run read)."""
    import re

    return sorted(set(re.findall(r"\b[0-9a-f]{64}\b", raw if isinstance(raw, str) else json.dumps(raw))))


def _files_of(p: Platform, engine: str, unit: str) -> set[str]:
    kind, _, key = unit.partition(":")
    q = p.db.query
    t = _tables(p.db)
    if engine == "recon" and "recon_runs" in t:
        return {x for r in q("SELECT left_file, right_file FROM recon_runs WHERE workspace_id = ?", (key,))
                for x in (r["left_file"], r["right_file"]) if x}
    if engine == "dq" and "dq_runs" in t:
        return {s for r in q("SELECT inputs FROM dq_runs WHERE dataset_id = ?", (key,)) for s in _shas(r["inputs"])}
    if engine == "sheets" and "sheet_scans" in t:
        return {x for r in q("SELECT sha256, previous_sha256 FROM sheet_scans WHERE model = ?", (key,))
                for x in (r["sha256"], r["previous_sha256"]) if x}
    if engine == "invoice" and "inv_documents" in t:
        return {r["doc_id"] for r in q("SELECT doc_id FROM inv_documents WHERE substr(doc_id, 1, 12) = ?", (key,))}
    return set()


def _live_references(p: Platform) -> set[str]:
    """Files still used by a unit that is not erased (the same bytes can be uploaded under two units)."""
    live: set[str] = set()
    erased = {(r["engine"], r["unit"]) for r in p.db.query("SELECT engine, unit FROM erasures")}
    for u in units(p):
        if u.engine != "statement" and (u.engine, u.unit) not in erased:
            live |= _files_of(p, u.engine, u.unit)
    return live


def _delete_unreferenced_files(p: Platform, engine: str, unit: str) -> int:
    removed = 0
    if engine == "statement":
        for f in (p.data_dir / "documents").glob(f"{unit}.*"):
            f.unlink(missing_ok=True)
            removed += 1
        return removed
    live = _live_references(p)
    folder = p.files[engine]
    gone = []
    for sha in _files_of(p, engine, unit) - live:
        for path in (folder / sha, folder / f"{sha}.tmp"):
            if path.exists():
                path.unlink()
                removed += 1
        gone.append(sha)
    if gone and "files" in _tables(p.db):
        with p.db.tx() as c:
            c.execute(f"UPDATE files SET name = ? WHERE sha256 IN ({','.join('?' * len(gone))})", (ERASED_NAME, *gone))
    return removed


def _erase_outcomes(p: Platform, engine: str, unit: str) -> int:
    """Remove reviewer outcomes that point at the unit (they quote labels and values)."""
    folder = p.outcomes_dir
    if folder is None or not folder.exists():
        return 0
    removed = 0
    for f in folder.glob("*.jsonl"):
        kept, dropped = [], 0
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                refs = json.loads(line).get("refs", {})
            except json.JSONDecodeError:
                kept.append(line)
                continue
            hit = (engine == "statement" and refs.get("document") == unit) or (
                engine == "recon" and f"workspace:{refs.get('workspace')}" == unit)
            if hit:
                dropped += 1
            else:
                kept.append(line)
        if dropped:
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text("".join(x + "\n" for x in kept), encoding="utf-8")
            tmp.replace(f)
            removed += dropped
    return removed


# -- the scheduled job --------------------------------------------------------------------------------------------


def run(p: Platform, policy: RetentionPolicy, actor: str, apply: bool, at: datetime | None = None) -> dict[str, Any]:
    """Plan (apply=False) or apply the policy. Errors on one unit are reported and the job goes on; the exit status
    of the CLI is non-zero when any unit failed, so a scheduler notices."""
    at = at or datetime.now(UTC)
    plan = due(p, policy, at)
    report: dict[str, Any] = {"at": at.isoformat(timespec="seconds"), "applied": apply,
                              "due": [u.__dict__ for u in plan], "erased": [], "failed": [],
                              "held": [h for h in holds(p.db)], "incomplete": incomplete(p)}
    temp_cut = at.timestamp() - policy.temporary_files_hours * 3600
    temps = [f for f in p.data_dir.rglob("*.tmp") if f.is_file() and f.stat().st_mtime < temp_cut]
    report["temporary_files"] = len(temps)
    if not apply:
        return report
    for u in plan:
        try:
            report["erased"].append({"engine": u.engine, "unit": u.unit,
                                     "counts": erase(p, u.engine, u.unit, "retention period ended", actor)})
        except Exception as exc:  # noqa: BLE001 - one unit's failure must not stop the rest
            report["failed"].append({"engine": u.engine, "unit": u.unit, "error": f"{type(exc).__name__}: {exc}"[:300]})
    for f in temps:
        f.unlink(missing_ok=True)
    cut = at.timestamp() - policy.ended_sessions_days * 86400
    if "auth_sessions" in _tables(p.db):
        with p.db.tx() as c:
            report["sessions_removed"] = c.execute(
                "DELETE FROM auth_sessions WHERE expires_at < ? OR (revoked = 1 AND last_seen < ?)", (cut, cut)).rowcount
            c.execute("DELETE FROM auth_pending WHERE created_at < ?", (at.timestamp() - 3600,))
    with p.db.tx() as c:
        p.db.append_event(c, "retention", "runs", actor, "retention_run",
                          {"erased": len(report["erased"]), "failed": len(report["failed"]),
                           "temporary_files": len(temps)})
    return report


def incomplete(p: Platform) -> list[dict[str, Any]]:
    """Erasures that started and did not finish (run the job or the erasure again)."""
    out = [{"engine": "statement", "unit": r["document_id"], "requested_at": r["requested_at"]}
           for r in p.store.query("SELECT * FROM erasures WHERE completed_at IS NULL")]
    out += [{"engine": r["engine"], "unit": r["unit"], "requested_at": r["requested_at"]}
            for r in p.db.query("SELECT * FROM erasures WHERE completed_at IS NULL")]
    return out


def platform_from_env(data_dir: Path | None = None) -> Platform:
    from spreader.store import Store

    d = Path(data_dir or os.environ.get("SPREADER_DATA") or Path(__file__).resolve().parents[3] / "var")
    from .outcomes import directory

    return Platform(store=Store(d / "spreader.sqlite3"), db=Database(d / "finops.sqlite3"), data_dir=d,
                    outcomes_dir=directory())
