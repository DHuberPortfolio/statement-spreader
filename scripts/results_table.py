"""Print the README's results table from saved evaluation reports (no number is typed by hand).

    .venv/Scripts/python scripts/results_table.py dev-final holdout-final holdout-final-model syn-final
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "eval" / "reports"
LABELS = {"sec-dev": "SEC dev (tuned on)", "sec-holdout": "SEC holdout (never tuned on)", "syn": "Synthetic, 3 formats"}


def fmt(r: dict) -> str:
    if not r["d"]:
        return "not measured"
    return f"{100 * r['rate']:.1f}% ({r['n']:,} of {r['d']:,}; {100 * r['low']:.1f}-{100 * r['high']:.1f}%)"


def main(names: list[str]) -> None:
    print("| Set | Documents | Values right | Silent error rate | Silent omissions | Sent to review | Wrong values caught |")
    print("|---|---|---|---|---|---|---|")
    for name in names:
        rep = json.loads((REPORTS / f"{name}.json").read_text())
        r = rep["rates"]
        model = " + local model" if rep.get("model") else ""
        print(f"| {name}{model} | {rep['documents']} | {fmt(r['accuracy'])} | {fmt(r['silent_error_rate'])} | "
              f"{fmt(r['silent_omission_rate'])} | {fmt(r['review_rate'])} | {fmt(r['catch_rate'])} |")


if __name__ == "__main__":
    main(sys.argv[1:])
