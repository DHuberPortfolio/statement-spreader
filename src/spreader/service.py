"""Application services: upload, run, review actions, approval. The API is a thin layer over this.

Rules this module enforces:
- Idempotent runs. A run is keyed by (document, profile version, reviewer-memory version, model,
  engine version). Asking again for the same key returns the existing run instead of a duplicate.
- No partial runs. A run row is written as "running", the pipeline runs, and the row becomes
  "succeeded" with its spread or "failed" with a safe error message, in one transaction each.
- Reviewer changes are events. The computed spread is never edited; corrections, resolutions
  and approval live in the run's state and are replayed on top of it, and every change is logged.
- Approval is refused while a blocking review item is open.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from . import __version__
from .checks import add_derived, run_checks, run_ratios
from .contracts import (
    ProvenanceStep,
    ReviewKind,
    Severity,
    Spread,
    SpreadValue,
    StatementType,
    ValueStatus,
)
from .ingest import IngestError, doc_id_for, read_document, sniff_format
from .mapping import MemoryKey
from .pipeline import spread_document
from .profile import Profile, load_profile
from .review import attach_flags, build_review, unresolved_blockers
from .store import Store, now

log = logging.getLogger("spreader")
ENGINE_VERSION = __version__


class ActionError(ValueError):
    """A reviewer action that is not allowed (bad input or wrong state). Safe to show."""


@dataclass
class RunView:
    run: dict[str, Any]
    spread: Spread | None


class Service:
    def __init__(self, store: Store, profile: Profile | None = None, model: Any = None, model_id: str = "none") -> None:
        self.store = store
        self.profile = profile or load_profile()
        self.model = model
        self.model_id = model_id

    # ---- memory ----
    def memory(self) -> dict[MemoryKey, str]:
        return {MemoryKey(r["profile_id"], r["statement"], r["label"], r["section"]): r["canonical"]
                for r in self.store.memory_rows(self.profile.id)}

    # ---- upload and run ----
    def upload(self, filename: str, data: bytes, actor: str) -> tuple[dict[str, Any], RunView]:
        try:
            fmt = sniff_format(filename, data)
        except IngestError as exc:
            raise ActionError(str(exc)) from exc
        doc_id = doc_id_for(data)
        new = self.store.save_document(doc_id, _safe_name(filename), fmt.value, data)
        with self.store.tx() as c:
            self.store.log(c, "upload" if new else "upload_duplicate", {"filename": _safe_name(filename), "size": len(data)},
                           actor, document_id=doc_id)
        run = self.run(doc_id, actor)
        doc = dict(self.store.document(doc_id))  # type: ignore[arg-type]
        return doc, run

    def idempotency_key(self, doc_id: str) -> str:
        parts = [doc_id, self.profile.id, f"{self.profile.version}+{self.profile.content_hash}",
                 str(self.store.memory_version(self.profile.id)), self.model_id, ENGINE_VERSION]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    def run(self, doc_id: str, actor: str, parent: int | None = None) -> RunView:
        doc = self.store.document(doc_id)
        if doc is None:
            raise ActionError("Unknown document")
        key = self.idempotency_key(doc_id)
        existing = self.store.query("SELECT * FROM runs WHERE idempotency_key=? AND status != 'failed'", (key,))
        if existing:
            return self._view(dict(existing[0]))
        with self.store.tx() as c:
            try:
                cur = c.execute(
                    "INSERT INTO runs(document_id, idempotency_key, profile_id, profile_version, engine_version, memory_version,"
                    " model, status, started_at, parent_run) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, key, self.profile.id, f"{self.profile.version}+{self.profile.content_hash}", ENGINE_VERSION,
                     self.store.memory_version(self.profile.id), self.model_id, "running", now(), parent))
            except Exception:
                # Another request started the same run a moment ago: return that one.
                rows = self.store.query("SELECT * FROM runs WHERE idempotency_key=? AND status != 'failed'", (key,))
                if rows:
                    return self._view(dict(rows[0]))
                raise
            run_id = cur.lastrowid
        try:
            data = self.store.document_bytes(doc_id, doc["format"])
            ir = read_document(doc["filename"], data)
            spread, timings = spread_document(ir, self.profile, self.memory(), self.model)
        except IngestError as exc:
            return self._fail(run_id, f"Could not read the document: {exc}", actor)
        except Exception as exc:  # noqa: BLE001 - recorded as a failed run, never a half-written one
            log.exception("run %s failed", run_id)
            return self._fail(run_id, f"Processing failed ({type(exc).__name__}). The run was not saved.", actor)
        with self.store.tx() as c:
            c.execute("UPDATE runs SET status='succeeded', finished_at=?, timings=?, spread=? WHERE id=?",
                      (now(), json.dumps(timings), spread.model_dump_json(), run_id))
            self.store.log(c, "run", {"status": "succeeded", "values": len(spread.values),
                                      "review_items": len(spread.review), "parent": parent}, actor, run_id, doc_id)
        return self.get(run_id)

    def _fail(self, run_id: int, message: str, actor: str) -> RunView:
        with self.store.tx() as c:
            c.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?", (now(), message, run_id))
            self.store.log(c, "run", {"status": "failed", "error": message}, actor, run_id)
        return self.get(run_id)

    # ---- reading ----
    def get(self, run_id: int) -> RunView:
        rows = self.store.query("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            raise ActionError("Unknown run")
        return self._view(dict(rows[0]))

    def _view(self, run: dict[str, Any]) -> RunView:
        run["state"] = json.loads(run.get("state") or "{}")
        run["timings"] = json.loads(run["timings"]) if run.get("timings") else {}
        spread = None
        if run.get("spread"):
            spread = self.effective(Spread.model_validate_json(run["spread"]), run["state"])
        run.pop("spread", None)
        return RunView(run, spread)

    def effective(self, spread: Spread, state: dict[str, Any]) -> Spread:
        """The computed spread with the reviewer's corrections applied and everything recomputed."""
        overrides: dict[str, dict[str, Any]] = state.get("overrides", {})
        resolved: dict[str, str] = state.get("resolved", {})
        if not overrides and not resolved:
            return spread
        values: list[SpreadValue] = [v.model_copy(deep=True) for v in spread.values if v.status is not ValueStatus.CALCULATED]
        index = {(v.line, v.period): v for v in values}
        for k, o in overrides.items():
            line, period = k.split("@", 1)
            new = Decimal(o["value"])
            v = index.get((line, period))
            step = ProvenanceStep(kind="correct", detail=f"Set to {new:,} by {o['actor']} ({o['at']}): {o['reason']}")
            if v is None:
                v = SpreadValue(line=line, period=period, value=new, status=ValueStatus.HUMAN, steps=[step])
                values.append(v)
                index[(line, period)] = v
            else:
                v.steps.append(step)
                v.value = new
                v.status = ValueStatus.HUMAN
                v.confidence = 1.0
        periods = spread.periods
        period_keys = {StatementType(k): {p.key for p in r.table.periods} for k, r in spread.statements.items()}
        scales = {StatementType(k): r.table.scale.multiplier for k, r in spread.statements.items()}
        derived, skip = add_derived(values, periods, self.profile, period_keys)
        values.extend(derived)
        checks = run_checks(values, periods, self.profile, period_keys, scales, skip)
        ratios = run_ratios(values, periods, self.profile)
        review = build_review(spread.statements, values, checks, self.profile)
        human = {(v.line, v.period) for v in values if v.status is ValueStatus.HUMAN}
        for it in review:
            if it.id in resolved:
                it.resolved = True
                it.resolution = resolved[it.id]
            elif it.kind is not ReviewKind.FAILED_CHECK and it.lines and all(
                    (ln, p) in human for ln in it.lines for p in it.periods):
                it.resolved = True
                it.resolution = "Every value it concerns was corrected by a reviewer."
        attach_flags(values, review)
        order = {ln: i for i, ln in enumerate(self.profile.lines)}
        values.sort(key=lambda v: (order.get(v.line, 999), v.period))
        return spread.model_copy(update={"values": values, "checks": checks, "ratios": ratios, "review": review})

    # ---- reviewer actions ----
    def act(self, run_id: int, action: dict[str, Any], actor: str) -> RunView:
        view = self.get(run_id)
        run, spread = view.run, view.spread
        if run["status"] != "succeeded" or spread is None:
            raise ActionError("Only a finished run can be reviewed")
        state = run["state"]
        if state.get("approved") and action.get("type") not in {"reopen"}:
            raise ActionError("This spread is approved. Reopen it before changing anything.")
        kind = action.get("type")
        payload: dict[str, Any] = {k: v for k, v in action.items() if k != "type"}
        if kind == "correct_value":
            line, period = str(action.get("line", "")), str(action.get("period", ""))
            if line not in self.profile.lines:
                raise ActionError(f"Unknown line '{line}'")
            if period not in {p.key for p in spread.periods}:
                raise ActionError(f"Unknown period '{period}'")
            reason = str(action.get("reason", "")).strip()
            if not reason:
                raise ActionError("A correction needs a reason")
            try:
                value = Decimal(str(action.get("value")).replace(",", ""))
            except (InvalidOperation, ValueError) as exc:
                raise ActionError("The value is not a number") from exc
            if not value.is_finite() or abs(value) > Decimal("1e16"):
                raise ActionError("The value is out of range")
            old = spread.value(line, period)
            state.setdefault("overrides", {})[f"{line}@{period}"] = {
                "value": str(value), "reason": reason[:500], "actor": actor, "at": now(),
                "previous": None if old is None or old.value is None else str(old.value)}
        elif kind == "resolve_item":
            item_id = str(action.get("item", ""))
            item = next((i for i in spread.review if i.id == item_id), None)
            if item is None:
                raise ActionError("Unknown review item")
            note = str(action.get("note", "")).strip()
            if not note:
                raise ActionError("Resolving an item needs a note saying why")
            if item.kind is ReviewKind.ASSUMED_SCALE and "confirm" not in note.lower():
                raise ActionError("An assumed unit can only be resolved by confirming it (include the word 'confirm')")
            state.setdefault("resolved", {})[item_id] = f"{note[:500]} ({actor}, {now()})"
        elif kind in {"remap_row", "exclude_row"}:
            return self._remap(run, spread, action, actor)
        elif kind == "approve":
            blockers = unresolved_blockers(spread.review)
            if blockers:
                raise ActionError(f"{len(blockers)} blocking review item(s) are still open: " + "; ".join(
                    b.message[:80] for b in blockers[:3]))
            state["approved"] = {"by": actor, "at": now()}
        elif kind == "reopen":
            if not state.get("approved"):
                raise ActionError("This spread is not approved")
            state.pop("approved")
        else:
            raise ActionError(f"Unknown action '{kind}'")
        with self.store.tx() as c:
            c.execute("UPDATE runs SET state=? WHERE id=?", (json.dumps(state), run_id))
            self.store.log(c, kind, payload, actor, run_id, run["document_id"])
        return self.get(run_id)

    def _remap(self, run: dict[str, Any], spread: Spread, action: dict[str, Any], actor: str) -> RunView:
        stmt = str(action.get("statement", ""))
        res = spread.statements.get(stmt)
        if res is None:
            raise ActionError("Unknown statement")
        try:
            row_index = int(action.get("row", -1))
        except (TypeError, ValueError) as exc:
            raise ActionError("Unknown row") from exc
        row = next((r for r in res.table.rows if r.index == row_index), None)
        if row is None:
            raise ActionError("Unknown row")
        target = "" if action.get("type") == "exclude_row" else str(action.get("line", ""))
        if target:
            if target not in self.profile.lines:
                raise ActionError(f"Unknown line '{target}'")
            if self.profile.line_statement[target].value != stmt:
                raise ActionError("That line belongs to a different statement")
        section = row.section.split(" > ")[-1] if row.section else ""
        with self.store.tx() as c:
            c.execute("INSERT OR REPLACE INTO mapping_memory(profile_id, statement, label, section, canonical, created_at,"
                      " created_by, source_run) VALUES (?,?,?,?,?,?,?,?)",
                      (self.profile.id, stmt, row.label_clean, section, target, now(), actor, run["id"]))
            self.store.log(c, action.get("type", "remap_row"),
                           {"statement": stmt, "row": row_index, "label": row.label, "section": section, "line": target},
                           actor, run["id"], run["document_id"])
        new = self.run(run["document_id"], actor, parent=run["id"])
        # Carry the reviewer's earlier corrections and resolutions over to the new run.
        if new.run["status"] == "succeeded" and run["state"] and new.run["id"] != run["id"]:
            carried = {k: v for k, v in run["state"].items() if k in {"overrides", "resolved"}}
            with self.store.tx() as c:
                c.execute("UPDATE runs SET state=? WHERE id=?", (json.dumps(carried), new.run["id"]))
                self.store.log(c, "carry_over", {"from_run": run["id"], "overrides": carried.get("overrides", {}),
                                                 "resolved": carried.get("resolved", {})}, actor, new.run["id"],
                               run["document_id"])
            new = self.get(new.run["id"])
        return new

    def events(self, run_id: int) -> list[dict[str, Any]]:
        rows = self.store.query("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def documents(self) -> list[dict[str, Any]]:
        rows = self.store.query(
            "SELECT d.*, r.id AS run_id, r.status AS run_status, r.started_at AS run_at, r.state AS run_state "
            "FROM documents d LEFT JOIN runs r ON r.id = (SELECT MAX(id) FROM runs WHERE document_id = d.id) "
            "ORDER BY d.uploaded_at DESC")
        out = []
        for r in rows:
            d = dict(r)
            st = json.loads(d.pop("run_state") or "{}")
            d["approved"] = bool(st.get("approved"))
            d["summary"] = None
            if d.get("run_id") and d.get("run_status") == "succeeded":
                view = self.get(int(d["run_id"]))
                if view.spread is not None:
                    d["summary"] = {**severity_counts(view.spread), "values": len(view.spread.values),
                                    "auto_accepted": sum(1 for v in view.spread.values if not v.flags)}
            out.append(d)
        return out


def _safe_name(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    keep = "".join(ch for ch in name if ch.isalnum() or ch in "._- ()")
    return (keep or "document")[:120]


def severity_counts(spread: Spread) -> dict[str, int]:
    out = {s.value: 0 for s in Severity}
    for it in spread.review:
        if not it.resolved:
            out[it.severity.value] += 1
    return out
