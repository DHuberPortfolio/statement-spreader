"""What the opt-in XBRL second reader (D37) does on the SEC sets, measured without the answer keys.

    .venv/Scripts/python scripts/eval_xbrl_check.py --sample 30

The SEC answer keys are built from the same tags, so grading this mode against them would be circular. Measured
instead: how often the two readers disagree (by kind), on dev and the holdout; and, for a fixed random sample of the
disagreements, which reader was right, decided by a person reading the printed filing. The sample, with the context
needed to check it, is written to eval/xbrl-check/sample.json; the verdicts go in eval/xbrl-check/verdicts.json
(one per sampled disagreement: "printed", "tag", "both wrong" or "unclear", with a note).
Every figure here is labelled as not independent of the key source.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from finops.core.evaluation import provenance, provenance_lines
from spreader.evaluation.stats import Rate
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile
from spreader.second_reader import compare, tagged_cells

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
OUT = ROOT / "eval" / "xbrl-check"
REPORTS = ROOT / "eval" / "reports"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261025)
    ap.add_argument("--save", default="xbrl-check")
    args = ap.parse_args()
    profile = load_profile()
    manifest = json.loads((SEC / "manifest.json").read_text())
    totals: dict[str, Counter[str]] = {"dev": Counter(), "holdout": Counter()}
    disagreements: list[dict[str, Any]] = []
    for t, m in sorted(manifest.items()):
        raw = SEC / "raw" / m["file"]
        if not raw.exists():
            continue
        data = raw.read_bytes()
        try:
            spread, _ = spread_document(read_document(m["file"], data), profile)
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            totals[m["split"]]["crashed"] += 1
            print(f"{t}: crashed ({type(exc).__name__})")
            continue
        comp = compare(spread, tagged_cells(data))
        c = totals[m["split"]]
        c["documents"] += 1
        c["cells"] += comp.cells
        c["agree"] += comp.agree
        for k, n in comp.kinds.items():
            c[k] += n
        headers = {p.key: p.label for r in spread.statements.values() for p in r.table.periods}
        flagged = {(v.line, v.period) for v in spread.values if v.flags}
        for d in comp.details:
            # Would a person have looked at this value anyway (tag-blind run)? Only the rest is new information.
            d["already_flagged"] = (d["line"], d["period"]) in flagged
            c["new_flags"] += int(not d["already_flagged"])
            res = spread.statements[d["statement"]]
            row = next(r for r in res.table.rows if r.index == int(d["row"]))
            disagreements.append({**d, "ticker": t, "split": m["split"], "file": m["file"], "table_title": res.table.title,
                                  "scale": f"{res.table.scale.multiplier} ({res.table.scale.evidence})",
                                  "column_header": headers.get(d["period"], ""), "cell_text": row.values[d["period"]].raw})
        print(f"{t:6s} {m['split']:8s} cells {comp.cells:4d}  disagree {len(comp.details):3d}  {dict(comp.kinds)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "disagreements.json").write_text(json.dumps(disagreements, indent=1), encoding="utf-8")
    rng = random.Random(args.seed)
    sample = rng.sample(disagreements, min(args.sample, len(disagreements)))
    sample.sort(key=lambda d: (d["ticker"], d["statement"], int(d["row"]), d["period"]))
    for i, d in enumerate(sample, 1):
        d["sample_id"] = i
    (OUT / "sample.json").write_text(json.dumps(sample, indent=1), encoding="utf-8")
    verdicts_path = OUT / "verdicts.json"
    verdicts = json.loads(verdicts_path.read_text(encoding="utf-8")) if verdicts_path.exists() else []
    report: dict[str, Any] = {"name": args.save, "independent_of_keys": False, "splits": {}, "sample_size": len(sample),
                              "seed": args.seed, "verdicts": Counter(v["verdict"] for v in verdicts)}
    lines = [f"# XBRL second reader: {args.save}", "",
             "**Not independent of the SEC answer keys**, which are built from the same tags. These figures say how often "
             "the printed-number reader and the tags disagree, and who was right on a hand-checked sample; they are not "
             "accuracy figures and are not comparable with the README's.", "",
             "| Split | Filings | Printed numbers with a tag on their cell | Readers agree | Disagree: value | scale | period | "
             "Disagreements on values not already sent to review |",
             "|---|---|---|---|---|---|---|---|"]
    for split, c in totals.items():
        dis = c["value"] + c["scale"] + c["period"]
        report["splits"][split] = {**c, "disagree": Rate(dis, c["cells"]).as_dict()}
        lines.append(f"| {split} | {c['documents']} | {c['cells']:,} | {Rate(c['agree'], c['cells']).text()} | {c['value']} | "
                     f"{c['scale']} | {c['period']} | {c['new_flags']} |")
    lines += ["", f"Hand-checked sample: {len(sample)} disagreements drawn at random (seed {args.seed}) from both splits; "
              f"verdicts recorded: {len(verdicts)}.", ""]
    if verdicts:
        lines += ["| Who was right (checked against the printed filing) | Disagreements |", "|---|---|"]
        lines += [f"| {k} | {n} |" for k, n in Counter(v["verdict"] for v in verdicts).most_common()]
    report["provenance"] = provenance(["sec-dev", "sec-holdout"], {"profile": f"{profile.id} {profile.version}+{profile.content_hash}",
                                                                   "second_reader": "on (measurement only)"})
    lines += provenance_lines(report["provenance"])
    (REPORTS / f"{args.save}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (REPORTS / f"{args.save}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
