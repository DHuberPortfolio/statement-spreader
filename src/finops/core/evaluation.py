"""What every engine's evaluation shares: rates with ranges and one report format.

Rates use the Wilson interval (z = 1.96) from the statement engine's evaluation, so a match
precision and a silent error rate read the same way. Reports go to eval/reports/<name>.json
and .md next to the statement engine's, so `scripts/run_eval.py --engine ...` is the one entry
point for all three engines.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spreader.evaluation.stats import Rate, wilson

__all__ = ["Rate", "wilson", "prf", "write_report", "rate_table", "provenance"]

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "eval" / "reports"


def git_state(root: Path = ROOT) -> dict[str, Any]:
    """The commit a run was made from, and whether the working tree had uncommitted changes (then the commit alone
    does not reproduce the run)."""
    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def provenance(datasets: list[str | dict[str, Any]], config: dict[str, str] | None = None) -> dict[str, Any]:
    """What a report records so that any number in it can be traced to exactly what produced it: when, from which
    commit, on which version of which evaluation sets (finops.evalsets), with which configuration."""
    from finops.evalsets import get, registry

    known = registry()
    sets = []
    for d in datasets:
        if isinstance(d, dict):
            sets.append(d)
        elif d in known:
            sets.append(get(d).summary())
        else:
            sets.append({"name": d, "version": None, "note": "not a registered evaluation set"})
    return {"created": datetime.now(UTC).isoformat(timespec="seconds"), **git_state(), "datasets": sets,
            "config": config or {}}


def provenance_lines(p: dict[str, Any]) -> list[str]:
    sets = ", ".join(f"{d['name']} {d.get('version') or '(unversioned)'}"
                     + ("" if d.get("matches_manifest") in (True, None) else " (DIFFERS FROM ITS MANIFEST)") for d in p["datasets"])
    commit = (p.get("commit") or "unknown")[:12] + (" with uncommitted changes" if p.get("dirty") else "")
    return ["", f"Provenance: {p['created']}, commit {commit}; datasets: {sets or 'none'}"
            + (f"; configuration: {', '.join(f'{k} {v}' for k, v in p['config'].items())}" if p.get("config") else "") + "."]


def prf(tp: int, fp: int, fn: int) -> dict[str, Rate]:
    """Precision (of what was claimed, how much was right) and recall (of what was there, how much was found)."""
    return {"precision": Rate(tp, tp + fp), "recall": Rate(tp, tp + fn)}


def rate_table(rows: list[tuple[str, Rate]]) -> list[str]:
    return ["| Measure | Result |", "|---|---|"] + [f"| {label} | {r.text()} |" for label, r in rows]


def write_report(name: str, report: dict[str, Any], lines: list[str], directory: Path | None = None,
                 datasets: list[str | dict[str, Any]] | None = None, config: dict[str, str] | None = None) -> Path:
    out = directory or REPORTS
    out.mkdir(parents=True, exist_ok=True)
    if "provenance" not in report:
        report["provenance"] = provenance(datasets or [], config)
        lines = lines + provenance_lines(report["provenance"])

    def enc(o: Any) -> Any:
        if isinstance(o, Rate):
            return o.as_dict()
        return str(o)

    (out / f"{name}.json").write_text(json.dumps(report, indent=1, default=enc), encoding="utf-8")
    (out / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out / f"{name}.md"
