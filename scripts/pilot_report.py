"""Analyst pilot report: timed by-hand spreading against timed review of the tool's spread (PILOT_PROTOCOL.md).

    .venv/Scripts/python scripts/pilot_report.py [--data var] [--out pilot-report.md]

Reads the timed work sessions from the statement database and writes what was observed, nothing more. Until at
least 3 sessions of each kind are finished it says PENDING and computes no saving. Every figure says whether it is
observed or derived; money is not computed here (the ROI page applies the organisation's own assumptions).
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MIN_SESSIONS = 3


def sessions(data: Path) -> list[dict[str, Any]]:
    from spreader.store import Store

    rows = Store(data / "spreader.sqlite3").query(
        "SELECT * FROM work_sessions WHERE ended_at IS NOT NULL AND active_seconds > 0 ORDER BY id")
    return [dict(r) for r in rows]


def _minutes(xs: list[float]) -> str:
    if not xs:
        return "-"
    m = [x / 60 for x in xs]
    return f"median {statistics.median(m):.1f} (range {min(m):.1f} to {max(m):.1f}), n={len(m)}"


def report(rows: list[dict[str, Any]]) -> str:
    base = [r for r in rows if r["mode"] == "baseline"]
    assist = [r for r in rows if r["mode"] == "assisted"]
    ready = len(base) >= MIN_SESSIONS and len(assist) >= MIN_SESSIONS
    out = ["# Analyst pilot report", ""]
    out.append(f"**Status: {'FEASIBILITY DATA (not a benchmark)' if ready else 'PENDING'}**: {len(base)} of "
               f"{MIN_SESSIONS} by-hand sessions and {len(assist)} of {MIN_SESSIONS} assisted sessions finished.")
    if not ready:
        out += ["", "No time saving is computed until both arms have at least three finished sessions."]
    out += ["", "| Arm | Active minutes (observed) | Analysts | Difficulty | Experience |", "|---|---|---|---|---|"]
    for name, arm in (("By hand", base), ("Assisted (review the tool's spread)", assist)):
        diff = ", ".join(f"{k} {sum(1 for r in arm if r.get('difficulty') == k)}" for k in ("low", "medium", "high")
                         if any(r.get("difficulty") == k for r in arm)) or "not recorded"
        exp = ", ".join(sorted({r.get("analyst_experience") or "not recorded" for r in arm})) or "-"
        out.append(f"| {name} | {_minutes([r['active_seconds'] for r in arm])} | {len({r['actor'] for r in arm})} | "
                   f"{diff} | {exp} |")
    checked = sum(r["values_checked"] or 0 for r in base)
    wrong = sum(r["errors_found"] or 0 for r in base)
    out += ["", "## Quality (observed)", "",
            f"- By hand: {wrong} of {checked} keyed values disagreed with the approved spread of the same document"
            + ("" if checked else " (no keyed values checked yet)") + ".",
            f"- Assisted: {sum(r['corrections'] or 0 for r in assist)} corrections made while reviewing "
            f"{len(assist)} spreads. Whether the approved spreads still hold errors is checked separately, against an "
            "answer key or a second reviewer (protocol step 6); it is not inferred here."]
    shared = {r["document_id"] for r in base} & {r["document_id"] for r in assist}
    out += ["", "## Design checks", "",
            f"- Documents timed in both arms (by different analysts): {len(shared)}.",
            "- The same analyst cannot be timed twice on one document (the app refuses it).",
            f"- Analysts in both arms: {len({r['actor'] for r in base} & {r['actor'] for r in assist})}."]
    if ready:
        mb = statistics.median([r["active_seconds"] for r in base]) / 60
        ma = statistics.median([r["active_seconds"] for r in assist]) / 60
        out += ["", "## Difference (derived from the observed medians)", "",
                f"- Median by hand {mb:.1f} min, median assisted {ma:.1f} min: {mb - ma:+.1f} min per document "
                f"({(mb - ma) / mb:+.0%} of the by-hand time).",
                f"- With {len(base)} and {len(assist)} sessions this is a feasibility signal, not an estimate with a "
                "known error. It is released analyst capacity, not cash, until a finance owner says otherwise."]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("SPREADER_DATA") or str(ROOT / "var"))
    ap.add_argument("--out")
    a = ap.parse_args()
    text = report(sessions(Path(a.data)))
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
