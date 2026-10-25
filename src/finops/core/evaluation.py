"""What every engine's evaluation shares: rates with ranges and one report format.

Rates use the Wilson interval (z = 1.96) from the statement engine's evaluation, so a match
precision and a silent error rate read the same way. Reports go to eval/reports/<name>.json
and .md next to the statement engine's, so `scripts/run_eval.py --engine ...` is the one entry
point for all three engines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spreader.evaluation.stats import Rate, wilson

__all__ = ["Rate", "wilson", "prf", "write_report", "rate_table"]

REPORTS = Path(__file__).resolve().parents[3] / "eval" / "reports"


def prf(tp: int, fp: int, fn: int) -> dict[str, Rate]:
    """Precision (of what was claimed, how much was right) and recall (of what was there, how much was found)."""
    return {"precision": Rate(tp, tp + fp), "recall": Rate(tp, tp + fn)}


def rate_table(rows: list[tuple[str, Rate]]) -> list[str]:
    return ["| Measure | Result |", "|---|---|"] + [f"| {label} | {r.text()} |" for label, r in rows]


def write_report(name: str, report: dict[str, Any], lines: list[str], directory: Path | None = None) -> Path:
    out = directory or REPORTS
    out.mkdir(parents=True, exist_ok=True)

    def enc(o: Any) -> Any:
        if isinstance(o, Rate):
            return o.as_dict()
        return str(o)

    (out / f"{name}.json").write_text(json.dumps(report, indent=1, default=enc), encoding="utf-8")
    (out / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out / f"{name}.md"
