"""One uncertainty policy for every engine: what a finding must say, and what may be accepted without a person.

Findings. Whatever an engine reports (a statement review item, a reconciliation or invoice exception, a held
record, a spreadsheet finding) can be read as one `Finding`: blocking or informational, the reason, the evidence,
the action it requires, and the rule or method that produced it. Each engine provides `as_findings(...)`.

Automation. Something may be accepted without a person only on one of three bases:
- **calibrated**: the method that produced it has a measured accuracy (`Calibration`, fitted by
  `scripts/calibrate.py` from labelled outcomes: answer keys now, reviewer decisions later), and the lower end of
  its 95% Wilson range clears the bar the engine sets. A method with few outcomes has a wide range, so it does not
  clear the bar until it has earned it;
- **person**: a named reviewer already decided this exact case (statement mapping memory);
- **derived**: the result follows from parts that each cleared their own bar (a total of rows that all feed one
  line takes its children's lowest confidence).
A model's own stated confidence is never a basis, and methods listed as `never_auto` (a language model's
suggestion, D8) always go to a person, whatever their measured accuracy. A method with no calibration is reviewed:
the policy fails closed. Deterministic checks (arithmetic, footing, a bank-detail change, a #REF!) are not
confidences: what they find is reported as a finding and blocks or informs by its severity.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from spreader.evaluation.stats import wilson

CALIBRATION_DIR = Path(__file__).resolve().parents[3] / "config" / "calibration"


class Finding(BaseModel):
    """The common shape of anything an engine asks a person to look at (or records for the audit trail)."""

    engine: str
    code: str
    blocking: bool  # stops automatic acceptance of what it is about
    reason: str  # one or two sentences a finance analyst understands
    evidence: dict[str, Any] = Field(default_factory=dict)  # cells, records, amounts: where to look
    required_action: str
    produced_by: str  # the rule, check or method that produced it
    subjects: list[str] = Field(default_factory=list)
    severity: str = ""  # the engine's own level (blocker, warning, info; error, risk, anomaly; ...), kept for display


class MethodStats(BaseModel):
    right: int
    total: int
    rate: float
    low: float  # 95% Wilson lower bound: what the policy compares with the bar
    high: float
    sources: dict[str, int] = Field(default_factory=dict)  # outcomes per labelled source (answer key, reviewers)


class AutoDecision(BaseModel):
    auto: bool
    basis: str  # calibrated | person | derived | never_auto | uncalibrated | below_bar
    confidence: float | None
    reason: str


class Calibration(BaseModel):
    engine: str
    unit: str  # what one outcome is ("a mapped statement row", "an automatic match")
    methods: dict[str, MethodStats] = Field(default_factory=dict)
    person_methods: list[str] = Field(default_factory=list)
    derived_methods: list[str] = Field(default_factory=list)
    never_auto: list[str] = Field(default_factory=list)
    fitted: dict[str, Any] = Field(default_factory=dict)  # when, from which commit, on which data

    def confidence(self, method: str) -> float | None:
        """The measured lower bound for a method, or None when it was never measured."""
        s = self.methods.get(method)
        return round(s.low, 4) if s else None

    def decide(self, method: str, bar: float, derived_confidence: float | None = None) -> AutoDecision:
        if method in self.never_auto:
            s = self.methods.get(method)
            measured = f" (measured {s.right} of {s.total} right)" if s else ""
            return AutoDecision(auto=False, basis="never_auto", confidence=self.confidence(method),
                                reason=f"'{method}' is always confirmed by a person{measured}.")
        if method in self.person_methods:
            return AutoDecision(auto=True, basis="person", confidence=self.confidence(method),
                                reason="A named reviewer decided this case before.")
        if method in self.derived_methods:
            ok = derived_confidence is not None and derived_confidence >= bar
            return AutoDecision(auto=ok, basis="derived" if ok else "below_bar", confidence=derived_confidence,
                                reason=f"Derived from parts whose lowest measured confidence is "
                                       f"{0 if derived_confidence is None else derived_confidence:.0%} (bar {bar:.0%}).")
        s = self.methods.get(method)
        if s is None:
            return AutoDecision(auto=False, basis="uncalibrated", confidence=None,
                                reason=f"'{method}' has no measured accuracy yet, so a person checks it.")
        ok = s.low >= bar
        return AutoDecision(auto=ok, basis="calibrated" if ok else "below_bar", confidence=round(s.low, 4),
                            reason=f"'{method}' was right {s.right} of {s.total} times when measured "
                                   f"({s.rate:.1%}, at least {s.low:.1%}); the bar is {bar:.0%}.")


def fit(engine: str, unit: str, outcomes: Iterable[tuple[str, bool, str]], *, person_methods: list[str] | None = None,
        derived_methods: list[str] | None = None, never_auto: list[str] | None = None,
        fitted: dict[str, Any] | None = None) -> Calibration:
    """Calibrate every method from (method, right, source) outcomes."""
    right: Counter[str] = Counter()
    total: Counter[str] = Counter()
    sources: dict[str, Counter[str]] = {}
    for method, ok, source in outcomes:
        total[method] += 1
        right[method] += int(ok)
        sources.setdefault(method, Counter())[source] += 1
    methods = {}
    for m in sorted(total):
        lo, hi = wilson(right[m], total[m])
        methods[m] = MethodStats(right=right[m], total=total[m], rate=right[m] / total[m], low=lo, high=hi,
                                 sources=dict(sources[m]))
    return Calibration(engine=engine, unit=unit, methods=methods, person_methods=person_methods or [],
                       derived_methods=derived_methods or [], never_auto=never_auto or [], fitted=fitted or {})


def save(cal: Calibration, directory: Path | None = None) -> Path:
    path = (directory or CALIBRATION_DIR) / f"{cal.engine}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal.model_dump(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    load.cache_clear()
    return path


@lru_cache(maxsize=16)
def load(engine: str, path: str | None = None) -> Calibration:
    """The committed calibration for an engine. A missing file is an empty calibration: nothing calibrated, so
    nothing confidence-driven is accepted without a person."""
    p = Path(path) if path else CALIBRATION_DIR / f"{engine}.json"
    if not p.exists():
        return Calibration(engine=engine, unit="(no calibration file)")
    return Calibration.model_validate_json(p.read_text(encoding="utf-8"))


def read_outcomes(path: Path) -> list[tuple[str, bool, str]]:
    """Labelled outcomes from elsewhere, one JSON object per line: {"method": ..., "right": true, "source": ...}.
    This is how reviewer decisions feed the calibration once there are enough of them."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append((str(d["method"]), bool(d["right"]), str(d.get("source", path.name))))
    return out


# -- engines' findings in the common shape ---------------------------------------------------------------------------

DEFAULT_ACTION = {"blocker": "Resolve it with a written note before the result is used.",
                  "warning": "Look at it, then resolve or accept it with your name.",
                  "info": "Nothing to do: recorded for the audit trail."}


def from_exception(item: Any) -> Finding:
    """A shared ExceptionItem (reconciliation, invoices). Each reason code is produced by exactly one check."""
    sev = item.severity.value
    return Finding(engine=item.engine, code=item.code, blocking=sev != "info", reason=f"{item.title} {item.detail}".strip(),
                   evidence={"records": list(item.subjects), **item.evidence}, required_action=item.suggested_action or DEFAULT_ACTION[sev],
                   produced_by=f"{item.engine} check {item.code}", subjects=list(item.subjects), severity=sev)
