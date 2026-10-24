"""Write the synthetic evaluation corpus: documents with exactly known answers.

    python scripts/make_synthetic.py --out eval/synthetic --seed 7 --count 40

Each case gets a folder eval/synthetic/<case_id>/ with statement.html, statement.xlsx,
statement.pdf (printed by headless Microsoft Edge) and key.json (one answer key for every format).
eval/synthetic/index.json lists the cases, their tags and the formats written. The same seed and
count always produce the same documents and keys (PDF bytes carry Edge's timestamps).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from spreader.evaluation.synthetic import EDGE_PATH, generate_corpus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="eval/synthetic", help="output folder (default eval/synthetic)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--count", type=int, default=40, help="number of cases, adversarial ones included")
    ap.add_argument("--formats", default="html,xlsx,pdf", help="comma-separated: html,xlsx,pdf")
    ap.add_argument("--edge", default=EDGE_PATH, help="path to msedge.exe (for PDFs)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    unknown = set(formats) - {"html", "xlsx", "pdf"}
    if unknown:
        ap.error(f"unknown format(s): {', '.join(sorted(unknown))}")
    out = Path(args.out)
    index = generate_corpus(out, seed=args.seed, count=args.count, formats=formats, edge=args.edge,
                            log=(lambda *_: None) if args.quiet else print)

    kinds = Counter(c["kind"] for c in index["cases"])
    fmts = Counter(f for c in index["cases"] for f in c["formats"])
    print(f"\nWrote {len(index['cases'])} cases to {out}")
    print("  by kind:   " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    print("  by format: " + ", ".join(f"{k} {n}" for k, n in sorted(fmts.items())))
    print(f"  PDF: {index['pdf']['status']}")
    for problem in index["pdf"]["problems"][:5]:
        print(f"    {problem}")
    stale = sorted(p.name for p in out.iterdir() if p.is_dir() and p.name not in {c['id'] for c in index["cases"]})
    if stale:
        print(f"  Note: {len(stale)} folder(s) in {out} are not in this corpus (left untouched): {', '.join(stale[:5])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
