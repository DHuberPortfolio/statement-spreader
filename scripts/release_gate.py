"""Run every evaluation set in the repository and compare with the committed baseline (finops.gate).

    .venv/Scripts/python scripts/release_gate.py                     # exit 1 if anything got worse
    .venv/Scripts/python scripts/release_gate.py --engines recon,dq  # a subset
    .venv/Scripts/python scripts/release_gate.py --write-baseline    # after a measured change was kept
    .venv/Scripts/python scripts/release_gate.py --out gate.md       # also write the comparison as Markdown

Needs nothing outside the repository (no SEC downloads), so CI runs it on every push.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from finops.gate import BASELINE, compare, report_lines, snapshot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default=None, help="comma-separated: statements,recon,invoice,dq,sheets")
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--out", default=None, help="write the comparison as Markdown here")
    args = ap.parse_args()
    t0 = time.perf_counter()
    run = snapshot(args.engines.split(",") if args.engines else None)
    took = time.perf_counter() - t0
    path = Path(args.baseline)
    if args.write_baseline:
        if args.engines and path.exists():  # refresh only the engines that ran
            old = json.loads(path.read_text(encoding="utf-8"))
            old["sets"] = {k: v for k, v in old["sets"].items() if v["engine"] not in set(args.engines.split(","))}
            run["sets"] = {**old["sets"], **run["sets"]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Baseline written: {path} ({len(run['sets'])} sets, {took:.0f} s).")
        return 0
    if not path.exists():
        print(f"No baseline at {path}: run with --write-baseline first.")
        return 1
    baseline = json.loads(path.read_text(encoding="utf-8"))
    if args.engines:  # compare only what ran
        wanted = set(args.engines.split(","))
        baseline = {**baseline, "sets": {k: v for k, v in baseline["sets"].items() if v["engine"] in wanted}}
    problems = compare(baseline, run)
    lines = report_lines(baseline, run, problems) + ["", f"{len(run['sets'])} sets in {took:.0f} s."]
    print("\n".join(lines))
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
