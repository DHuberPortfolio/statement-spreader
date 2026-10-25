"""Reviewer decisions as labelled outcomes: the feed that calibration learns from (DECISIONS D40).

Every decision a named reviewer makes that says whether a rule was right is written here as one line: which engine,
which rule or method, right or wrong, who decided, when, and on what. `scripts/calibrate.py --outcomes-dir` reads them
back and refits each rule's measured accuracy, so the uncertainty policy (finops.core.policy) moves on evidence from
the organisation's own reviewers instead of only the public answer keys.

Where they go: one append-only JSON Lines file per engine in a folder, `var/outcomes/` by default, or the folder named
by the environment variable FINOPS_OUTCOMES_DIR (a shared drive, or a folder another system collects from). Connecting
the platform to an organisation's own data store is pointing that variable at a folder their pipeline picks up; the
line format below is the contract. A file is only ever appended to.

What counts as an outcome (each engine says in its service):
- statements: at approval, every mapped row the reviewer left unchanged is a *right* outcome for its rule; a row the
  reviewer remapped or excluded is a *wrong* outcome for the rule that placed it; each statement's unit is right
  unless a value in it was corrected by a power of ten;
- reconciliation: an accepted proposal is right for its rule; a rejected proposal, or an automatic match a reviewer
  undid, is wrong.

Approval without a change is weaker evidence than a correction (a busy reviewer may approve what they did not check),
so every outcome says how it was decided (`how`) and calibration reports outcomes per source.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


class Outcome(BaseModel):
    engine: str  # statements | units | recon
    method: str  # the rule calibrated (policy.Calibration.methods key)
    right: bool
    how: str  # approved_unchanged | remapped | excluded | accepted | rejected | undone | corrected
    subject: str  # what it is about, readable ("balance_sheet row 12 'Cash and cash equivalents'")
    decided_by: str
    decided_at: str
    refs: dict[str, Any] = Field(default_factory=dict)  # run, document, company: enough to find the decision again

    @property
    def source(self) -> str:
        return f"reviewers ({self.how})"


def directory() -> Path:
    return Path(os.environ.get("FINOPS_OUTCOMES_DIR") or ROOT / "var" / "outcomes")


def record(outcomes: Iterable[Outcome], folder: Path | None = None) -> int:
    """Appends outcomes to <folder>/<engine>.jsonl. Never stops a decision: a failure is logged (the decision itself
    is in the engine's audit log, from which scripts/export_outcomes.py can rebuild the folder)."""
    by_engine: dict[str, list[str]] = {}
    for o in outcomes:
        by_engine.setdefault(o.engine, []).append(o.model_dump_json())
    n = 0
    try:
        target = folder or directory()
        target.mkdir(parents=True, exist_ok=True)
        for engine, lines in by_engine.items():
            with open(target / f"{engine}.jsonl", "a", encoding="utf-8") as f:
                f.write("".join(line + "\n" for line in lines))
            n += len(lines)
    except OSError:
        log.exception("could not write %d outcome(s); rebuild them with scripts/export_outcomes.py",
                      sum(len(v) for v in by_engine.values()))
    return n


def read(engine: str, folder: Path | None = None) -> list[Outcome]:
    path = (folder or directory()) / f"{engine}.jsonl"
    if not path.exists():
        return []
    return [Outcome.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def as_calibration_outcomes(outcomes: Iterable[Outcome]) -> list[tuple[str, bool, str]]:
    """The (method, right, source) triples policy.fit takes."""
    return [(o.method, o.right, o.source) for o in outcomes]


def summary(folder: Path | None = None) -> dict[str, Any]:
    """Counts per engine and method, for the platform's 'what reviewers have taught it' view."""
    target = folder or directory()
    out: dict[str, Any] = {"folder": str(target), "engines": {}}
    for path in sorted(target.glob("*.jsonl")) if target.exists() else []:
        rows = read(path.stem, target)
        methods: dict[str, Counter[str]] = {}
        for o in rows:
            methods.setdefault(o.method, Counter())["right" if o.right else "wrong"] += 1
        out["engines"][path.stem] = {"outcomes": len(rows),
                                     "methods": {m: dict(c) for m, c in sorted(methods.items())},
                                     "last": max((o.decided_at for o in rows), default=None)}
    return out


def write_lines(path: Path, outcomes: Iterable[Outcome]) -> None:
    """Rewrites one file whole (used only by scripts/export_outcomes.py --rebuild)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(o.model_dump_json() + "\n" for o in outcomes), encoding="utf-8")


def to_json(outcomes: Iterable[Outcome]) -> str:
    return json.dumps([o.model_dump() for o in outcomes], indent=1)
