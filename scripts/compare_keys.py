"""Compare two sets of SEC answer keys and two evaluation reports: what a scorer change changed, value by value.

    .venv/Scripts/python scripts/compare_keys.py <keys dir A> <keys dir B> [--reports <report A> <report B>]

Prints every (filing, line, period) whose key value differs, and, with --reports, the headline rates per split
(dev, holdout) recomputed from each report's per-document buckets, so a measurement change is shown as numbers
before and after, not just described.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(d: Path) -> dict[tuple[str, str, str], str]:
    out = {}
    for f in sorted(d.glob("*.json")):
        k = json.loads(f.read_text(encoding="utf-8"))
        for v in k.get("spread", []):
            out[(f.stem, v["line"], v["period"])] = str(v["value"])
    return out


def rates(report: dict, split: str, manifest: dict) -> dict[str, tuple[int, int]]:
    b: Counter[str] = Counter()
    for d in report["documents_detail"]:
        t = d["doc"].split(":", 1)[1]
        if d["doc"].startswith("sec:") and manifest.get(t, {}).get("split") == split:
            b.update(d["buckets"])
    present = b["correct_auto"] + b["correct_review"] + b["wrong_auto"] + b["wrong_review"]
    total = present + b["missing_flagged"] + b["missing_silent"]
    return {"values right": (b["correct_auto"] + b["correct_review"], total),
            "silent errors": (b["wrong_auto"], b["correct_auto"] + b["wrong_auto"]),
            "silent omissions": (b["missing_silent"], total),
            "wrong values caught": (b["wrong_review"], b["wrong_auto"] + b["wrong_review"]),
            "unjudged": (b["unjudged"], b["unjudged"] + total)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--reports", nargs=2)
    args = ap.parse_args()
    a, b = load(Path(args.a)), load(Path(args.b))
    changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    print(f"{len(changed)} key values differ ({len(a)} vs {len(b)} values in all)")
    for k in changed:
        print(f"  {k[0]:6s} {k[1]:28s} {k[2]:16s} {a.get(k, '-'):>18s} -> {b.get(k, '-')}")
    if args.reports:
        manifest = json.loads((ROOT / "eval" / "sec" / "manifest.json").read_text())
        ra, rb = (json.loads((ROOT / "eval" / "reports" / f"{n}.json").read_text()) for n in args.reports)
        for split in ("dev", "holdout"):
            print(f"\n{split}: {args.reports[0]} -> {args.reports[1]}")
            x, y = rates(ra, split, manifest), rates(rb, split, manifest)
            for m in x:
                (n1, d1), (n2, d2) = x[m], y[m]
                print(f"  {m:20s} {n1}/{d1} ({100 * n1 / d1 if d1 else 0:.1f}%) -> {n2}/{d2} ({100 * n2 / d2 if d2 else 0:.1f}%)")
        # Per filing, how many values each bucket gained or lost: where the rates above moved, exactly.
        print("\nbucket changes per filing:")
        da = {d["doc"]: Counter(d["buckets"]) for d in ra["documents_detail"]}
        for d in rb["documents_detail"]:
            delta = Counter(d["buckets"])
            delta.subtract(da.get(d["doc"], Counter()))
            moved = {k: n for k, n in delta.items() if n}
            if moved:
                print(f"  {d['doc']:12s} " + ", ".join(f"{k} {n:+d}" for k, n in sorted(moved.items())))


if __name__ == "__main__":
    main()
