"""Many seeds, harder data: find the rare errors one set cannot show.

    .venv/Scripts/python scripts/stress_eval.py --seeds 10 --save recon-multiseed

Reconciliation, default (component) strategy, three kinds of set per seed:
  clean   unique amounts
  stress  40% round amounts that collide
  messy   20% round amounts, plus what bank exports do: truncated, abbreviated or padded descriptions,
          dropped and mistyped references, same-day payroll bursts that only names tell apart

Counts are pooled across seeds (every set is a different random draw) and every individual failure
is listed, so each can be read, not just counted.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict
from pathlib import Path

from finops.core.config import load_config
from finops.core.evaluation import Rate, write_report
from finops.recon.config import ReconProfile
from finops.recon.evaluate import evaluate
from finops.recon.synthetic import generate

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"clean": {"round_share": 0.0}, "stress": {"round_share": 0.4}, "messy": {"round_share": 0.2, "messy": True}}
RATES = ["false_match_rate", "review_cases_auto_accepted", "auto_recall", "review_cases_reaching_review", "exception_recall",
         "left_alone_accuracy", "proposal_precision", "unnecessary_exceptions"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first", type=int, default=101)
    ap.add_argument("--scale", type=int, default=300)
    ap.add_argument("--save", default="recon-multiseed")
    args = ap.parse_args()
    profile, version = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    pooled: dict[str, dict[str, list[int]]] = {k: defaultdict(lambda: [0, 0]) for k in KINDS}
    failures: dict[str, list[str]] = defaultdict(list)
    missed_kinds: dict[str, Counter[str]] = defaultdict(Counter)
    unstable, checks_failed, seconds = [], 0, 0.0
    for seed in range(args.first, args.first + args.seeds):
        for kind, opts in KINDS.items():
            bank, ledger, truth = generate(seed, args.scale, **opts)
            t0 = time.perf_counter()
            r = evaluate(profile, version, bank, ledger, truth)
            seconds += time.perf_counter() - t0
            for k in RATES:
                pooled[kind][k][0] += r["rates"][k].n
                pooled[kind][k][1] += r["rates"][k].d
            for f in r["false_matches"]:
                failures[kind].append(f"seed {seed}: FALSE AUTO {f['rule']} {f['left']} + {f['right']}")
            for m in r["missed_exceptions"]:
                missed_kinds[kind][f"{m['kind']} / {m['code']}"] += 1
                if len(failures[kind]) < 60:
                    failures[kind].append(f"seed {seed}: missed {m['code']} on {m['any_of']} ({m['kind']})")
            if not (r["order_stable"] and r["exceptions_stable"]):
                unstable.append(f"{kind} seed {seed}")
            checks_failed += len(r["checks_failed"])
    lines = [f"# Reconciliation, {args.seeds} seeds x 3 kinds of set (scale {args.scale})", "",
             f"Seeds {args.first}-{args.first + args.seeds - 1}; profile {profile.id} {version}; component strategy. "
             f"Order-unstable sets: {len(unstable)} {unstable[:5]}; completeness checks failed: {checks_failed}; "
             f"{seconds:.1f} s in all.", ""]
    report = {"name": args.save, "seeds": args.seeds, "scale": args.scale, "kinds": {}, "failures": failures,
              "missed_by_kind": {k: dict(v) for k, v in missed_kinds.items()}, "unstable": unstable, "checks_failed": checks_failed}
    for kind in KINDS:
        rates = {k: Rate(*pooled[kind][k]) for k in RATES}
        report["kinds"][kind] = rates
        lines += [f"## {kind}", "", "| Measure | Pooled |", "|---|---|"] + [f"| {k} | {v.text()} |" for k, v in rates.items()]
        if missed_kinds[kind]:
            lines += ["", "Planted problems not raised, by scenario / code:"] + [f"- {k}: {n}" for k, n in missed_kinds[kind].most_common()]
        if failures[kind]:
            lines += ["", "First failures:"] + [f"- {x}" for x in failures[kind][:25]]
        lines.append("")
    write_report(args.save, report, lines)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
