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
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from finops.core.outcomes import record as record_outcomes

from . import __version__
from .checks import add_derived, run_checks, run_ratios
from .company import (
    ApprovedValue,
    CompanyContext,
    approved_from_spread,
    confirmed_mappings,
    detect_company_id,
)
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
from .learning import approval_outcomes, remap_outcome
from .mapping import MemoryKey
from .pipeline import spread_document
from .profile import Profile, load_profile
from .review import attach_flags, build_review, unresolved_blockers
from .second_reader import tagged_cells
from .shadow import in_sample, review_days, second_opinions
from .shadow import summary as shadow_summary
from .store import Store, now

log = logging.getLogger("spreader")
ENGINE_VERSION = __version__
SHADOW_ACTOR = "system:shadow-model"  # who the audit log names for the second opinion (D52)
DEADLINE_ACTOR = "system:review-deadline"  # who settles a disagreement no senior ruled on in time (D53)
HIDDEN_FROM_RUN_HISTORY = ("shadow_opinion", "disagreements")


class StaleError(Exception):
    """The person acted on a version of the spread that is no longer current (HTTP 409)."""


class _StateMoved(Exception):
    """Internal: another person's unrelated change landed first; the action is applied again to the new state."""


def state_version(state: dict[str, Any]) -> str:
    """A short fingerprint of a run's review state, shown to the person as `version`."""
    import hashlib

    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]


def _target(kind: Any, action: dict[str, Any]) -> tuple[str | None, str]:
    """Which part of the review state an action changes; approving and reopening change all of it (None)."""
    if kind == "correct_value":
        return "overrides", f"{action.get('line', '')}@{action.get('period', '')}"
    if kind == "resolve_item":
        return "resolved", str(action.get("item", ""))
    return None, ""


class SeparationError(Exception):
    """Separation of duties forbids this person doing this (HTTP 403)."""


class ActionError(ValueError):
    """A reviewer action that is not allowed (bad input or wrong state). Safe to show."""


@dataclass
class RunView:
    run: dict[str, Any]
    spread: Spread | None


class Service:
    def __init__(self, store: Store, profile: Profile | None = None, model: Any = None, model_id: str = "none",
                 shadow: Any = None, shadow_id: str = "none", shadow_sync: bool = False) -> None:
        """shadow: a model giving the hidden second opinion after each run (D52), on one background thread so the
        analyst never waits for it; shadow_sync runs it before `run` returns (tests, the backfill command)."""
        self.store = store
        self.profile = profile or load_profile()
        self.model = model
        self.model_id = model_id
        self.shadow_model = shadow
        self.shadow_id = shadow_id
        if shadow is not None:  # a nonsense setting stops the start, not every upload (D53)
            in_sample("0" * 8)
            review_days()
        self._shadow_pool = None if shadow is None or shadow_sync else ThreadPoolExecutor(1, thread_name_prefix="shadow")

    # ---- memory ----
    def memory(self) -> dict[MemoryKey, str]:
        return {MemoryKey(r["profile_id"], r["statement"], r["label"], r["section"]): r["canonical"]
                for r in self.store.memory_rows(self.profile.id)}

    # ---- upload and run ----
    def upload(self, filename: str, data: bytes, actor: str, company_id: str | None = None) -> tuple[dict[str, Any], RunView]:
        """company_id: any identifier the organisation uses for the borrower or client; for an SEC filing it defaults to
        the CIK on its cover page. Documents of one company share its approved spreads and confirmed mappings."""
        try:
            fmt = sniff_format(filename, data)
        except IngestError as exc:
            raise ActionError(str(exc)) from exc
        company = (company_id or "").strip()[:100] or detect_company_id(data)
        doc_id = doc_id_for(data)
        new = self.store.save_document(doc_id, _safe_name(filename), fmt.value, data)
        with self.store.tx() as c:
            if company:
                c.execute("UPDATE documents SET company_id=? WHERE id=?", (company, doc_id))
            self.store.log(c, "upload" if new else "upload_duplicate", {"filename": _safe_name(filename), "size": len(data),
                                                                        "company_id": company}, actor, document_id=doc_id)
        run = self.run(doc_id, actor)
        doc = dict(self.store.document(doc_id))  # type: ignore[arg-type]
        return doc, run

    def set_company(self, doc_id: str, company_id: str, actor: str) -> RunView:
        """Says which company a document is about after upload, then re-runs it so last year's approvals apply. Refused
        once one of the document's runs is approved: that approval was remembered under the earlier company."""
        doc = self.store.document(doc_id)
        if doc is None:
            raise ActionError("Unknown document")
        company = company_id.strip()[:100]
        if not company:
            raise ActionError("A company needs a name or identifier")
        approved = [r for r in self.store.query("SELECT state FROM runs WHERE document_id=?", (doc_id,))
                    if json.loads(r["state"] or "{}").get("approved")]
        if approved and company != doc["company_id"]:
            raise ActionError("This document has an approved spread; reopen it before changing its company")
        with self.store.tx() as c:
            c.execute("UPDATE documents SET company_id=? WHERE id=?", (company, doc_id))
            self.store.log(c, "set_company", {"company_id": company, "previous": doc["company_id"]}, actor,
                           document_id=doc_id)
        return self.run(doc_id, actor)

    def companies(self) -> list[dict[str, Any]]:
        """Every company with a document, for the upload screen's suggestions: how many documents and approved spreads
        each has (an approved spread is what the next year is compared with)."""
        withdrawn = "SELECT run_id FROM approval_withdrawals"
        rows = self.store.query(
            "SELECT d.company_id AS company_id, COUNT(DISTINCT d.id) AS documents, MAX(d.uploaded_at) AS last_upload, "
            f"(SELECT COUNT(DISTINCT a.run_id) FROM approved_values a WHERE a.company_id = d.company_id AND a.profile_id=? "
            f"AND a.run_id NOT IN ({withdrawn})) AS approved_spreads "
            "FROM documents d WHERE d.company_id IS NOT NULL AND d.company_id != '' GROUP BY d.company_id "
            "ORDER BY last_upload DESC", (self.profile.id,))
        return [dict(r) for r in rows]

    def company_context(self, doc_id: str) -> CompanyContext | None:
        """What the company's earlier approvals left behind, without the document's own approvals (a document is never
        compared with itself) and without withdrawn ones."""
        doc = self.store.document(doc_id)
        company = doc["company_id"] if doc is not None else None
        if not company:
            return None
        withdrawn = "SELECT run_id FROM approval_withdrawals"
        ctx = CompanyContext(company_id=company)
        for r in self.store.query("SELECT * FROM company_mappings WHERE company_id=? AND profile_id=? AND run_id NOT IN "
                                  f"(SELECT id FROM runs WHERE document_id=?) AND run_id NOT IN ({withdrawn}) ORDER BY rowid",
                                  (company, self.profile.id, doc_id)):
            ctx.mappings[(r["statement"], r["label"], r["section"])] = r["canonical"]
        for r in self.store.query(f"SELECT * FROM approved_values WHERE company_id=? AND profile_id=? AND document_id != ? "
                                  f"AND run_id NOT IN ({withdrawn}) ORDER BY rowid", (company, self.profile.id, doc_id)):
            ctx.approved[(r["period"], r["line"])] = ApprovedValue(r["period"], r["line"], Decimal(r["value"]),
                                                                   Decimal(r["tolerance"]), r["run_id"], r["document_id"],
                                                                   r["approved_by"], r["approved_at"])
        return ctx

    def idempotency_key(self, doc_id: str) -> str:
        ctx = self.company_context(doc_id)
        parts = [doc_id, self.profile.id, f"{self.profile.version}+{self.profile.content_hash}",
                 str(self.store.memory_version(self.profile.id)), self.model_id, ENGINE_VERSION,
                 ctx.version if ctx else "no-company", "xbrl-check" if os.environ.get("SPREADER_XBRL_CHECK") == "1" else ""]
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
            tags = tagged_cells(data) if os.environ.get("SPREADER_XBRL_CHECK") == "1" else None  # opt-in (D37)
            spread, timings = spread_document(ir, self.profile, self.memory(), self.model, self.company_context(doc_id),
                                              tags)
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
        if self.shadow_model is not None and in_sample(doc_id):
            if self._shadow_pool is None:
                self.record_shadow(run_id)
            else:
                self._shadow_pool.submit(self.record_shadow, run_id)
        return self.get(run_id)

    def record_shadow(self, run_id: int) -> dict[str, Any] | None:
        """Ask the shadow model for its opinion on every row of a succeeded run and store it apart from the run (D52).
        Once per run and model. Never raises: a failure is logged and the run is untouched."""
        if self.shadow_model is None:
            return None
        try:
            done = self.store.query("SELECT outcome, COUNT(*) AS n FROM shadow_opinions WHERE run_id=? AND model_id=? "
                                    "GROUP BY outcome", (run_id, self.shadow_id))
            if done:
                counts = {"rows": 0, "agree": 0, "disagree": 0, "no_answer": 0}
                for r in done:
                    counts[r["outcome"]] = r["n"]
                    counts["rows"] += r["n"]
                return counts
            rows = self.store.query("SELECT document_id, spread FROM runs WHERE id=? AND status='succeeded'", (run_id,))
            if not rows or not rows[0]["spread"]:
                return None
            opinions = second_opinions(Spread.model_validate_json(rows[0]["spread"]), self.profile, self.shadow_model)
            counts = shadow_summary(opinions)
            with self.store.tx() as c:
                at = now()
                c.executemany(
                    "INSERT OR IGNORE INTO shadow_opinions(run_id, model_id, statement, row_index, label, section, "
                    "platform_line, platform_excluded, platform_rule, model_line, outcome, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(run_id, self.shadow_id, o.statement, o.row_index, o.label, o.section, o.platform_line,
                      int(o.platform_excluded), o.platform_rule, o.model_line, o.outcome, at) for o in opinions])
                self.store.log(c, "shadow_opinion", {"model": self.shadow_id, **counts}, SHADOW_ACTOR, run_id,
                               rows[0]["document_id"])
            self.collect_disagreements(run_id)  # the analyst may have approved before the opinion was ready
            return counts
        except Exception as exc:  # noqa: BLE001 - the second opinion must never disturb the analyst's work
            log.exception("shadow opinion for run %s failed", run_id)
            try:
                with self.store.tx() as c:
                    self.store.log(c, "shadow_opinion", {"model": self.shadow_id, "failed": type(exc).__name__},
                                   SHADOW_ACTOR, run_id)
            except Exception:  # noqa: BLE001
                log.exception("could not record the failed shadow opinion for run %s", run_id)
            return None

    def collect_disagreements(self, run_id: int) -> int:
        """Every row of an approved run where the model's opinion differs from the approved placement becomes a
        disagreement waiting for a senior's ruling (D53). Runs at approval and when a late opinion arrives; a
        re-approval after a reopen opens the run's withdrawn disagreements again. Returns how many are open now.
        Never raises: the analyst's approval already stands."""
        try:
            rows = self.store.query("SELECT document_id, state FROM runs WHERE id=?", (run_id,))
            approved = json.loads(rows[0]["state"] or "{}").get("approved") if rows else None
            if not approved:
                return 0
            due = (datetime.fromisoformat(approved["at"]) + timedelta(days=review_days())).isoformat(timespec="seconds")
            with self.store.tx() as c:
                before = c.execute("SELECT COUNT(*) FROM disagreements WHERE run_id=? AND status='open'",
                                   (run_id,)).fetchone()[0]
                c.execute(
                    "INSERT INTO disagreements(opinion_id, run_id, document_id, model_id, statement, row_index, label, "
                    "section, analyst_line, analyst_rule, model_line, approved_by, approved_at, due_at, status, created_at) "
                    "SELECT id, run_id, ?, model_id, statement, row_index, label, section, "
                    "CASE WHEN platform_line IS NULL OR platform_excluded THEN 'none' ELSE platform_line END, "
                    "platform_rule, model_line, ?, ?, ?, 'open', ? FROM shadow_opinions "
                    "WHERE run_id=? AND outcome='disagree' "
                    "ON CONFLICT(opinion_id) DO UPDATE SET status='open', approved_by=excluded.approved_by, "
                    "approved_at=excluded.approved_at, due_at=excluded.due_at WHERE disagreements.status='withdrawn'",
                    (rows[0]["document_id"], approved["by"], approved["at"], due, now(), run_id))
                after = c.execute("SELECT COUNT(*) FROM disagreements WHERE run_id=? AND status='open'",
                                  (run_id,)).fetchone()[0]
                if after != before:
                    self.store.log(c, "disagreements", {"open": after}, SHADOW_ACTOR, run_id, rows[0]["document_id"])
            return after
        except Exception:  # noqa: BLE001
            log.exception("collecting disagreements for run %s failed", run_id)
            return 0

    def settle_overdue(self, at: str | None = None) -> int:
        """Disagreements past their deadline without a senior's ruling: the analyst's answer stands (D53)."""
        at = at or now()
        with self.store.tx() as c:
            n = c.execute("UPDATE disagreements SET status='analyst_stands', verdict='analyst', ruled_by=?, ruled_at=? "
                          "WHERE status='open' AND due_at <= ?", (DEADLINE_ACTOR, at, at)).rowcount
            if n:
                self.store.log(c, "disagreements_settled", {"analyst_stands": n}, DEADLINE_ACTOR)
        return n

    def disagreements(self, status: str | None = None) -> list[dict[str, Any]]:
        """For seniors and the learning-period report, never for analysts (D53). Settles overdue ones first."""
        self.settle_overdue()
        where, args = ("WHERE status=?", (status,)) if status else ("", ())
        return [dict(r) for r in self.store.query(f"SELECT * FROM disagreements {where} ORDER BY id", args)]

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
        run["version"] = state_version(run["state"])
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
        review = build_review(spread.statements, values, checks, self.profile, ratios) + [
            i.model_copy() for i in spread.prior_items + spread.second_reader_items]
        human = {(v.line, v.period) for v in values if v.status is ValueStatus.HUMAN}
        for it in review:
            if it.id in resolved:
                r = resolved[it.id]
                if isinstance(r, dict) and r.get("fingerprint") not in (None, _fingerprint(it.message)):
                    continue  # the numbers it was resolved on have changed: open again
                it.resolved = True
                it.resolution = r["note"] if isinstance(r, dict) else r
            elif it.kind is not ReviewKind.FAILED_CHECK and it.lines and all(
                    (ln, p) in human for ln in it.lines for p in it.periods):
                it.resolved = True
                it.resolution = "Every value it concerns was corrected by a reviewer."
        attach_flags(values, review)
        order = {ln: i for i, ln in enumerate(self.profile.lines)}
        values.sort(key=lambda v: (order.get(v.line, 999), v.period))
        return spread.model_copy(update={"values": values, "checks": checks, "ratios": ratios, "review": review})

    # ---- reviewer actions ----
    def approval_conflict(self, run_id: int, actor: str, not_uploader: bool, not_corrector: bool) -> str | None:
        """Why `actor` may not approve this run under separation of duties, or None (DECISIONS D43).

        The uploader is whoever uploaded the document (first upload or a duplicate); a corrector is anyone who corrected
        a value, remapped or excluded a row on any run of the document. Both are read from the audit log."""
        from finops.core.exceptions import same_person

        run = self.get(run_id).run
        rows = self.store.query("SELECT actor, kind FROM events WHERE document_id=? AND kind IN "
                                "('upload','upload_duplicate','correct_value','remap_row','exclude_row')", (run["document_id"],))
        uploaders = {r["actor"] for r in rows if r["kind"].startswith("upload")}
        correctors = {r["actor"] for r in rows if not r["kind"].startswith("upload")}
        for o in run["state"].get("overrides", {}).values():
            correctors.add(o.get("actor", ""))
        if not_uploader and any(same_person(actor, u) for u in uploaders):
            return "You uploaded this document; separation of duties needs someone else to approve its spread"
        if not_corrector and any(same_person(actor, x) for x in correctors):
            return "You corrected or remapped values in this spread; separation of duties needs someone else to approve it"
        return None

    def act(self, run_id: int, action: dict[str, Any], actor: str,
            separation: tuple[bool, bool] | None = None) -> RunView:
        """Apply one reviewer action (DECISIONS D47).

        Two people working on one spread: an action whose target nobody else touched in the meantime is applied to
        the latest state (so two corrections to different cells both land); an action on a value, item or approval
        someone else changed a moment ago is refused, never silently overwritten. Approving and reopening also refuse
        when the spread changed since the person loaded it (`expected_version`, the `version` they were shown), so
        nobody approves numbers they have not seen. `separation` = (approver not uploader, approver not corrector) is
        checked inside the write transaction (D43)."""
        action = dict(action)
        expected = action.pop("expected_version", None)
        for attempt in range(20):
            try:
                return self._act_once(run_id, action, actor, separation, expected)
            except _StateMoved:  # someone else's unrelated change landed first: apply this one to the new state
                time.sleep(random.uniform(0.005, 0.05) * (1 + attempt))  # spread out writers that keep colliding
        raise ActionError("This spread is being changed by several people at once. Reload it and try again.")

    def _act_once(self, run_id: int, action: dict[str, Any], actor: str, separation: tuple[bool, bool] | None,
                  expected: str | None) -> RunView:
        view = self.get(run_id)
        run, spread = view.run, view.spread
        if run["status"] != "succeeded" or spread is None:
            raise ActionError("Only a finished run can be reviewed")
        state = run["state"]
        before = json.loads(json.dumps(state))
        if state.get("approved") and action.get("type") not in {"reopen"}:
            raise ActionError("This spread is approved. Reopen it before changing anything.")
        kind = action.get("type")
        if kind in {"approve", "reopen"} and expected is not None and expected != state_version(before):
            raise StaleError("This spread changed since you opened it. Reload it, check the changes, then try again.")
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
            state.setdefault("resolved", {})[item_id] = {"note": f"{note[:500]} ({actor}, {now()})",
                                                        "fingerprint": _fingerprint(item.message)}
        elif kind in {"remap_row", "exclude_row"}:
            return self._remap(run, spread, action, actor)
        elif kind == "approve":
            blockers = unresolved_blockers(spread.review)
            if blockers:
                raise ActionError(f"{len(blockers)} blocking review item(s) are still open: " + "; ".join(
                    b.message[:80] for b in blockers[:3]))
            state["approved"] = {"by": actor, "at": now()}
            company = (self.store.document(run["document_id"]) or {})["company_id"]
            if company:
                payload["company_id"] = company
        elif kind == "reopen":
            if not state.get("approved"):
                raise ActionError("This spread is not approved")
            state.pop("approved")
        else:
            raise ActionError(f"Unknown action '{kind}'")
        with self.store.tx() as c:
            current = json.loads(c.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()["state"] or "{}")
            if current != before:
                section, key = _target(kind, action)
                if section is None or current.get(section, {}).get(key) != before.get(section, {}).get(key) or \
                        current.get("approved") != before.get("approved"):
                    raise ActionError("Someone else changed this a moment ago. Reload the spread and try again.")
                raise _StateMoved()
            if kind == "approve" and separation is not None:
                why = self.approval_conflict(run_id, actor, *separation)
                if why:
                    raise SeparationError(why)
            c.execute("UPDATE runs SET state=? WHERE id=?", (json.dumps(state), run_id))
            self.store.log(c, kind, payload, actor, run_id, run["document_id"])
            if kind == "approve" and payload.get("company_id"):
                self._remember(c, run_id, run["document_id"], payload["company_id"], spread, state, actor)
            elif kind == "reopen":
                c.execute("INSERT INTO approval_withdrawals(run_id, withdrawn_by, withdrawn_at) VALUES (?,?,?)",
                          (run_id, actor, now()))
                # the approval they compared with is withdrawn; a ruling already made stays (D53)
                c.execute("UPDATE disagreements SET status='withdrawn' WHERE run_id=? AND status='open'", (run_id,))
        if kind == "approve":  # what the approval says about each rule, for calibration (D40)
            record_outcomes(approval_outcomes(spread, state, {"run": run_id, "document": run["document_id"],
                                                              "company": payload.get("company_id")},
                                              actor, state["approved"]["at"], self.profile.line_statement))
            self.collect_disagreements(run_id)
        return self.get(run_id)

    def _remember(self, c: Any, run_id: int, doc_id: str, company: str, spread: Spread, state: dict[str, Any],
                  actor: str) -> None:
        """An approval leaves the company's approved values and confirmed mappings behind (append-only). Lines whose
        value the reviewer corrected do not confirm the rows behind them (spreader.company.confirmed_mappings)."""
        at = now()
        corrected = {k.split("@", 1)[0] for k in state.get("overrides", {})}
        for a in approved_from_spread(spread, run_id, doc_id, actor, at):
            c.execute("INSERT INTO approved_values(company_id, profile_id, run_id, document_id, period, line, value, tolerance,"
                      " approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (company, self.profile.id, run_id, doc_id, a.period, a.line, str(a.value), str(a.tolerance), actor, at))
        for (stmt, label, section), line in confirmed_mappings(spread, corrected).items():
            c.execute("INSERT INTO company_mappings(company_id, profile_id, statement, label, section, canonical, run_id,"
                      " confirmed_by, confirmed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (company, self.profile.id, stmt, label, section, line, run_id, actor, at))

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
        mapping = next((m for m in res.mappings if m.row_index == row_index), None)
        with self.store.tx() as c:
            c.execute("INSERT OR REPLACE INTO mapping_memory(profile_id, statement, label, section, canonical, created_at,"
                      " created_by, source_run) VALUES (?,?,?,?,?,?,?,?)",
                      (self.profile.id, stmt, row.label_clean, section, target, now(), actor, run["id"]))
            self.store.log(c, action.get("type", "remap_row"),
                           {"statement": stmt, "row": row_index, "label": row.label, "section": section, "line": target,
                            "previous_line": mapping.canonical if mapping else None,
                            "previous_rule": (mapping.rule or mapping.method.value) if mapping else None},
                           actor, run["id"], run["document_id"])
        wrong = remap_outcome(stmt, row, mapping, target, actor, now(), {"run": run["id"], "document": run["document_id"]})
        if wrong is not None:
            record_outcomes([wrong])
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
        # The second opinion's entries stay in the audit log but not in the run's history: even its counts would tell
        # the analyst where the model disagreed (D52).
        marks = ",".join("?" * len(HIDDEN_FROM_RUN_HISTORY))
        rows = self.store.query(f"SELECT * FROM events WHERE run_id=? AND kind NOT IN ({marks}) ORDER BY id",
                                (run_id, *HIDDEN_FROM_RUN_HISTORY))
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


def _fingerprint(message: str) -> str:
    return hashlib.sha256(message.encode()).hexdigest()[:16]


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
