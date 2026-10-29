"""What the platform and the model learn from a senior's ruling, and the evidence for going live (DECISIONS D55).

A ruling is the strongest decision the platform records: a senior, with the two answers in front of them, said where a
line belongs. So it is used four ways:

1. Memory. The correct line is remembered for the label under its section, the way an analyst's remap is, so the same
   label is placed that way next time without the model. If the document belongs to a company, the company's own
   memory (which is consulted first) gets the correction too, so a wrong approved line cannot keep winning there.
2. Calibration. The ruling says whether the rule that placed the approved line was right, and whether the model was.
3. Examples for the model. Earlier rulings on similar labels are shown to the model in its prompt (spreader.llm.local).
4. A golden placement set and training examples, exported for evaluation and for training a model later.

A disagreement that no senior ruled on before the deadline (the analyst's answer stands, D53) is weaker evidence: it
is used as a training example marked as such and as a prompt example after the senior rulings, but never as a golden
case, never in memory, and never in the go-live measure.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finops.core.outcomes import Outcome

from .contracts import Spread, StatementRow
from .learning import NOT_JUDGED

MODEL_METHOD = "model.shadow"  # the method name the model's ruled opinions are recorded under (calibration)


def row_of(spread: Spread, statement: str, row_index: int) -> StatementRow | None:
    res = spread.statements.get(statement)
    if res is None:
        return None
    return next((r for r in res.table.rows if r.index == row_index), None)


def memory_section(row: StatementRow) -> str:
    """The section key mapping memory uses (the nearest header), as a reviewer's remap writes it."""
    return row.section.split(" > ")[-1] if row.section else ""


def ruling_outcomes(d: dict[str, Any], actor: str, at: str) -> list[Outcome]:
    """What one ruling says about the rule behind the approved line and about the model."""
    refs = {"run": d["run_id"], "document": d["document_id"], "statement": d["statement"], "row": d["row_index"],
            "disagreement": d["id"], "correct": d["correct_line"]}
    subject = f"{d['statement'].replace('_', ' ')}: '{d['label']}'"
    out = []
    if d["analyst_line"] != "none" and (d["analyst_rule"] or "") not in NOT_JUDGED:
        right = d["correct_line"] == d["analyst_line"]
        out.append(Outcome(engine="statements", method=d["analyst_rule"], right=right,
                           how="ruled_right" if right else "ruled_wrong", subject=f"{subject} -> {d['analyst_line']}",
                           decided_by=actor, decided_at=at, refs={**refs, "line": d["analyst_line"]}))
    right = d["correct_line"] == d["model_line"]
    out.append(Outcome(engine="statements", method=MODEL_METHOD, right=right, how="ruled_right" if right else "ruled_wrong",
                       subject=f"{subject} -> {d['model_line']} ({d['model_id']})", decided_by=actor, decided_at=at,
                       refs={**refs, "line": d["model_line"], "model": d["model_id"]}))
    return out


# ---- examples for the model's prompt ----

# How labels are compared for examples. Measured on the SEC dev split (scripts/measure_ruling_examples.py, D55):
# token_set fixed 27 rows and broke 3 (a short ruled label matched longer labels containing its words); token_sort
# fixed 24 and broke none, for the same 906 of 976 right.
SIMILARITY = "token_sort"


def _similar(a: str, b: str, how: str | None = None) -> float:
    """How alike two labels read, 0..1. `token_set` (rapidfuzz's token set ratio) scores 1 when one label's words are
    all in the other ("Other current liabilities" against "Accrued expenses and other current liabilities");
    `token_sort` compares the whole of both labels."""
    from rapidfuzz import fuzz

    scorer = fuzz.token_sort_ratio if (how or SIMILARITY) == "token_sort" else fuzz.token_set_ratio
    return scorer(a.lower(), b.lower()) / 100


@dataclass(frozen=True)
class Example:
    label: str
    section: str
    line: str  # a line id or "none"
    source: str  # senior | analyst_default


class RulingExamples:
    """Earlier decisions on similar labels, for the model's prompt. Senior rulings first, then disagreements where the
    analyst's answer stood by default. Never from the document being asked about (that would let a document's own
    ruling answer its own re-run, and make the model look better than it is)."""

    MIN_SIMILARITY = 0.8
    LIMIT = 3

    def __init__(self, store: Any) -> None:
        self.store = store
        self._cache: dict[tuple[str, str], list[Any]] = {}  # (statement, version) -> candidate rows

    def version(self) -> str:
        """Changes whenever the set of examples changes: part of a live run's idempotency key (a new example can change
        the model's answer, so it must not reuse a run made without it)."""
        rows = self.store.query("SELECT COUNT(*) AS n, MAX(COALESCE(ruled_at, '')) AS at FROM disagreements "
                                "WHERE status IN ('ruled', 'analyst_stands')")
        return f"examples:{rows[0]['n']}:{rows[0]['at'] or '-'}"

    def for_row(self, statement: str, label: str, doc_id: str, allowed: set[str]) -> list[Example]:
        # One read of the candidates per statement until the examples change, not one per row asked about.
        key = (statement, self.version())
        if key not in self._cache:
            self._cache = {k: v for k, v in self._cache.items() if k[1] == key[1]}
            self._cache[key] = [dict(r) for r in self.store.query(
                "SELECT label, section, status, document_id, CASE WHEN status='ruled' THEN correct_line "
                "ELSE analyst_line END AS line FROM disagreements WHERE statement=? AND status IN ('ruled', "
                "'analyst_stands') ORDER BY id DESC LIMIT 2000", (statement,))]
        scored = []
        for r in self._cache[key]:
            if r["document_id"] == doc_id:
                continue
            line = r["line"]
            if line not in allowed and line != "none":
                continue
            s = _similar(label, r["label"])
            if s >= self.MIN_SIMILARITY:
                scored.append((r["status"] != "ruled", -s, Example(r["label"], r["section"], line,
                                                                     "senior" if r["status"] == "ruled" else "analyst_default")))
        scored.sort(key=lambda t: (t[0], t[1]))
        seen: set[tuple[str, str]] = set()
        out = []
        for _, _, ex in scored:
            key = (ex.label.lower(), ex.line)
            if key in seen:
                continue
            seen.add(key)
            out.append(ex)
            if len(out) == self.LIMIT:
                break
        return out


# ---- export: a golden placement set and training examples ----

def export(store: Any, profile: Any, out: Path, prompt_of: Any) -> dict[str, Any]:
    """Writes golden-placements.jsonl (senior rulings only), training.jsonl (chat-format examples: senior rulings, and
    analyst-stands defaults marked as weaker) and manifest.json. `prompt_of(table, row, lines)` builds the user prompt
    the model would see. The files hold document labels: treat them like the documents (they are not erased with them)."""
    from .contracts import StatementType
    from .llm.local import SYSTEM
    from .mapping import _unit_ok

    out.mkdir(parents=True, exist_ok=True)
    rows = store.query("SELECT * FROM disagreements WHERE status IN ('ruled', 'analyst_stands') ORDER BY id")
    spreads: dict[int, Spread | None] = {}
    golden, training, skipped = [], [], 0
    for r in rows:
        d = dict(r)
        line = d["correct_line"] if d["status"] == "ruled" else d["analyst_line"]
        if d["run_id"] not in spreads:
            raw = store.query("SELECT spread FROM runs WHERE id=?", (d["run_id"],))
            spreads[d["run_id"]] = Spread.model_validate_json(raw[0]["spread"]) if raw and raw[0]["spread"] else None
        spread = spreads[d["run_id"]]
        row = row_of(spread, d["statement"], d["row_index"]) if spread else None
        if spread is None or row is None:
            skipped += 1  # the document was erased: nothing left to learn from
            continue
        table = spread.statements[d["statement"]].table
        lines = [ln for ln in profile.statements[StatementType(d["statement"])].lines if _unit_ok(ln, row)]
        source = "senior" if d["status"] == "ruled" else "analyst_default"
        if source == "senior":
            golden.append({"id": d["id"], "document_id": d["document_id"], "run_id": d["run_id"],
                           "statement": d["statement"], "row": d["row_index"], "label": d["label"],
                           "section": d["section"], "line": line, "verdict": d["verdict"], "reason": d["reason"],
                           "note": d["note"], "approved_line": d["analyst_line"], "model_line": d["model_line"],
                           "model": d["model_id"], "ruled_by": d["ruled_by"], "ruled_at": d["ruled_at"]})
        training.append({"messages": [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": prompt_of(table, row, lines)},
                                      {"role": "assistant", "content": json.dumps({"line": line})}],
                         "source": source, "weight": 1.0 if source == "senior" else 0.5, "disagreement": d["id"]})
    files = {"golden-placements.jsonl": golden, "training.jsonl": training}
    manifest: dict[str, Any] = {"profile": f"{profile.id} {profile.version}", "golden": len(golden),
                                "training": len(training), "skipped_erased": skipped, "files": {},
                                "note": "Holds labels from the organisation's documents; not erased with them."}
    for name, items in files.items():
        body = "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items).encode("utf-8")
        (out / name).write_bytes(body)  # bytes: text mode on Windows would turn \n into \r\n and break the digest
        manifest["files"][name] = hashlib.sha256(body).hexdigest()
    (out / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode("utf-8"))
    return manifest


# ---- the go-live report ----

def _wilson(n: int, d: int) -> tuple[float, float]:
    from .evaluation.stats import wilson

    return wilson(n, d)


def golive_settings() -> tuple[int, float]:
    """SPREADER_GOLIVE_MIN_RULINGS (default 100) and SPREADER_GOLIVE_MARGIN (default 0.05): the model is ready when at
    least that many disagreements have a senior's verdict for the analyst or the model and, with 95% confidence (Wilson,
    z = 1.96), seniors side with the model at least (0.5 - margin) of the time. The company's executives set both."""
    raw_n, raw_m = os.environ.get("SPREADER_GOLIVE_MIN_RULINGS", "100"), os.environ.get("SPREADER_GOLIVE_MARGIN", "0.05")
    if not raw_n.isdigit() or int(raw_n) < 10:
        raise ValueError(f"SPREADER_GOLIVE_MIN_RULINGS must be a whole number of at least 10, not {raw_n!r}")
    try:
        margin = float(raw_m)
    except ValueError:
        margin = -1.0
    if not 0 <= margin <= 0.2:
        raise ValueError(f"SPREADER_GOLIVE_MARGIN must be between 0 and 0.2, not {raw_m!r}")
    return int(raw_n), margin


def golive_report(store: Any, model_id: str | None = None) -> dict[str, Any]:
    """Everything the go-live decision rests on (D53 point 4, D55), for one model (default: the most recent one)."""
    min_rulings, margin = golive_settings()
    models = [r["model_id"] for r in store.query(
        "SELECT model_id, MAX(id) AS last FROM disagreements GROUP BY model_id ORDER BY last DESC")]
    model = model_id or (models[0] if models else None)
    rows = [dict(r) for r in store.query("SELECT * FROM disagreements WHERE model_id=?", (model,))] if model else []
    status: dict[str, int] = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    ruled = [r for r in rows if r["status"] == "ruled"]
    wins = {"model": 0, "analyst": 0, "neither": 0}
    reasons: dict[str, int] = {}
    seniors: dict[str, int] = {}
    for r in ruled:
        wins[r["verdict"]] += 1
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        seniors[r["ruled_by"]] = seniors.get(r["ruled_by"], 0) + 1
    decided = wins["model"] + wins["analyst"]
    share = None
    if decided:
        lo, hi = _wilson(wins["model"], decided)
        share = {"model": wins["model"], "of": decided, "rate": wins["model"] / decided, "low": lo, "high": hi}
    # Rows the model saw on spreads that are still approved: how often it agreed with the analyst at all.
    seen = store.query(
        "SELECT o.outcome, COUNT(*) AS n FROM shadow_opinions o JOIN runs r ON r.id = o.run_id "
        "WHERE o.model_id=? AND json_extract(r.state, '$.approved') IS NOT NULL GROUP BY o.outcome", (model,)) if model else []
    seen_counts = {r["outcome"]: r["n"] for r in seen}
    judged = seen_counts.get("agree", 0) + seen_counts.get("disagree", 0)
    agreement = None
    if judged:
        lo, hi = _wilson(seen_counts.get("agree", 0), judged)
        agreement = {"agree": seen_counts.get("agree", 0), "of": judged, "rate": seen_counts.get("agree", 0) / judged,
                     "low": lo, "high": hi, "no_answer": seen_counts.get("no_answer", 0)}
    # The same label ruled two different ways: the second ruling replaced the first in memory. Worth a senior's look.
    by_label: dict[tuple[str, str, str], set[str]] = {}
    for r in ruled:
        by_label.setdefault((r["statement"], r["label"].lower(), r["section"].lower()), set()).add(r["correct_line"])
    conflicts = [{"statement": k[0], "label": k[1], "section": k[2], "lines": sorted(v)} for k, v in by_label.items()
                 if len(v) > 1]
    if share is None or decided < min_rulings:
        verdict, why = "not_enough", (f"{decided} of the {min_rulings} rulings needed between the analyst and the model "
                                      "so far")
    elif share["low"] > 0.5:
        verdict, why = "better", "seniors side with the model more often than with the analysts, beyond chance"
    elif share["low"] >= 0.5 - margin:
        verdict, why = "as_good", (f"seniors side with the model at least {0.5 - margin:.0%} of the time with 95% "
                                   "confidence: as good as the analysts within the agreed margin")
    else:
        verdict, why = "not_yet", (f"with 95% confidence seniors side with the model at least {share['low']:.0%} of the "
                                   f"time; it needs {0.5 - margin:.0%}")
    return {"model": model, "models": models, "settings": {"min_rulings": min_rulings, "margin": margin, "z": 1.96},
            "status": status, "wins": wins, "model_share": share, "agreement": agreement, "reasons": reasons,
            "seniors": seniors, "conflicts": conflicts, "ready": verdict in {"as_good", "better"}, "verdict": verdict,
            "why": why,
            "limits": ["Rows where the model and the analyst agree are counted as agreement, not as right: both can be "
                       "wrong, which only the golden sets reveal.",
                       "Disagreements no senior ruled on (the analyst's answer stood by default) are not evidence and "
                       "are left out of the measure.",
                       "The model judges where lines go, not the values."]}
