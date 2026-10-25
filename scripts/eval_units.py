"""How well each statement's unit (thousands, millions) is read, judged against the filer's inline XBRL tags.

    .venv/Scripts/python scripts/eval_units.py dev        # fit on this: current and prior-year dev filings
    .venv/Scripts/python scripts/eval_units.py holdout    # measure once per change; never fit on it
    .venv/Scripts/python scripts/eval_units.py dev --calibrate   # also write config/calibration/units.json

Truth for one statement: every money cell the spread read that carries a tag is compared with the tag's value. The
ratio is a power of ten (1 when the unit was read right, 1,000 when "in thousands" was missed). The statement's true
multiplier is the read multiplier times the ratio most cells agree on; a statement with fewer than 3 tagged money cells,
or where fewer than 80% of them agree, has no truth and is left out (counted). Each statement's outcome is credited to
the rule that set its unit (Scale.rule), which is what the policy calibrates (DECISIONS D39).

The fallback rules rarely fire (a statement without its own unit line is rare), so each is also asked of every
statement that does print its unit, as if that line were missing ("unit line hidden"): would the other statements'
unit (scale.sibling), or the document-wide statement (scale.document), have given the true unit? Those outcomes are
reported apart from the real ones and labelled by their own source in the calibration file, counted once per filing
(statements of one filing share their unit, so they are not independent evidence). Caveat: a statement that really
lacks its unit line may differ from one that has it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
sys.path.insert(0, str(ROOT / "src"))

from finops.core import policy  # noqa: E402
from finops.core.evaluation import provenance  # noqa: E402
from spreader.contracts import ValueUnit  # noqa: E402
from spreader.ingest import read_document  # noqa: E402
from spreader.pipeline import spread_document  # noqa: E402
from spreader.profile import load_profile  # noqa: E402
from spreader.second_reader import tagged_cells  # noqa: E402
from spreader.units import document_unit  # noqa: E402

POWERS = [Decimal(10) ** k for k in range(-9, 10)]


def filings(split: str) -> list[tuple[str, Path]]:
    out = []
    for manifest, folder, suffix in (("manifest.json", "raw", ""), ("manifest-prior.json", "raw-prior", "-prior")):
        m = json.loads((SEC / manifest).read_text())
        current = json.loads((SEC / "manifest.json").read_text())
        for t, entry in sorted(m.items()):
            if current.get(t, {}).get("split") == split and (SEC / folder / entry["file"]).exists():
                out.append((t + suffix, SEC / folder / entry["file"]))
    return out


def statement_truth(res, tags) -> tuple[int | None, int]:  # type: ignore[no-untyped-def]
    """(true multiplier or None, tagged money cells)."""
    mult = Decimal(res.table.scale.multiplier)
    ratios: Counter[Decimal] = Counter()
    for row in res.table.rows:
        if row.unit is not ValueUnit.MONEY:
            continue
        for pv in row.values.values():
            if pv.displayed in (None, 0) or pv.ref is None or not pv.ref.xpath or pv.ref.xpath not in tags:
                continue
            facts = [f for f in tags[pv.ref.xpath] if not f.dimensional] or tags[pv.ref.xpath]
            read = abs(pv.displayed) * mult
            for p in POWERS:
                if any(abs(f.magnitude - read * p) <= max(Decimal(1), read * p * Decimal("0.0005")) for f in facts):
                    ratios[p] += 1
                    break
    n = sum(ratios.values())
    if n < 3:
        return None, n
    ratio, top = ratios.most_common(1)[0]
    if top < 0.8 * n:
        return None, n
    return int(mult * ratio), n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["dev", "holdout"])
    ap.add_argument("--calibrate", action="store_true", help="write config/calibration/units.json (dev only)")
    ap.add_argument("--outcomes-dir", default=None, help="with --calibrate: also fit on reviewers' unit outcomes "
                                                          "(finops.core.outcomes; 'default' for the configured folder)")
    args = ap.parse_args()
    if args.calibrate and args.split != "dev":
        sys.exit("Calibration is fitted on dev only; the holdout is measured, never fitted on.")
    profile = load_profile()
    rows, no_truth, hidden = [], 0, []
    for name, path in filings(args.split):
        data = path.read_bytes()
        doc = read_document(path.name, data)
        spread, _ = spread_document(doc, profile)
        tags = tagged_cells(data)
        for skey, res in spread.statements.items():
            truth, cells = statement_truth(res, tags)
            if truth is None:
                no_truth += 1
                continue
            s = res.table.scale
            rows.append({"filing": name, "statement": skey, "read": s.multiplier, "truth": truth, "rule": s.rule,
                         "flagged": s.assumed, "evidence": s.evidence[:120], "currency": s.currency, "cells": cells})
            if s.rule == "scale.table":  # the fallbacks, asked as if this table printed no unit line
                others = {o.table.scale.multiplier for k, o in spread.statements.items()
                          if k != skey and o.table.scale.rule == "scale.table"}
                if len(others) == 1:
                    hidden.append({"filing": name, "statement": skey, "rule": "scale.sibling", "guess": next(iter(others)),
                                   "truth": truth})
                document = document_unit(doc.unit_statements)
                if document is not None:
                    hidden.append({"filing": name, "statement": skey, "rule": "scale.document", "guess": document[0],
                                   "truth": truth})
        print(f"{name:12s} " + " ".join(f"{r['statement'][:4]}:{r['rule']}={'ok' if r['read'] == r['truth'] else 'WRONG'}"
                                        for r in rows if r["filing"] == name))
    by_rule: dict[str, list[int]] = {}
    for r in rows:
        by_rule.setdefault(r["rule"], [0, 0])
        by_rule[r["rule"]][0] += int(r["read"] == r["truth"])
        by_rule[r["rule"]][1] += 1
    silent = [r for r in rows if r["read"] != r["truth"] and not r["flagged"]]
    unit_hidden: dict[str, dict[str, Any]] = {}
    for h in hidden:
        u = unit_hidden.setdefault(h["rule"], {"right": 0, "total": 0, "filings": set(), "wrong": []})
        u["right"] += int(h["guess"] == h["truth"])
        u["total"] += 1
        u["filings"].add(h["filing"])
        if h["guess"] != h["truth"]:
            u["wrong"].append(h)
    for u in unit_hidden.values():
        u["filings"] = len(u["filings"])
    report = {"split": args.split, "statements": len(rows), "without_truth": no_truth,
              "by_rule": {k: {"right": v[0], "total": v[1]} for k, v in sorted(by_rule.items())},
              "unit_line_hidden": unit_hidden, "hidden_rows": hidden,
              "wrong_unflagged": silent, "flagged": sum(r["flagged"] for r in rows),
              "rows": rows, "provenance": provenance(datasets=[f"sec-{args.split}", f"sec-{args.split}-prior"])}
    out = ROOT / "eval" / "units" / f"{args.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"\n{len(rows)} statements judged ({no_truth} without enough tagged cells); flagged {report['flagged']}; "
          f"wrong and unflagged {len(silent)}")
    for k, v in report["by_rule"].items():
        print(f"  {k:24s} {v['right']} of {v['total']} right")
    for k, v in unit_hidden.items():
        print(f"  {k:24s} {v['right']} of {v['total']} right with the table's unit line hidden ({v['filings']} filings)")
    if args.calibrate:
        labelled = [(r["rule"], r["read"] == r["truth"], "sec-dev tags") for r in rows]
        # One outcome per filing and rule (right only if every statement was): statements of one filing share their
        # unit, so counting them separately would overstate the evidence.
        per_filing: dict[tuple[str, str], bool] = {}
        for h in hidden:
            k = (h["filing"], h["rule"])
            per_filing[k] = per_filing.get(k, True) and h["guess"] == h["truth"]
        labelled += [(rule, ok, "sec-dev tags, unit line hidden (per filing)") for (_, rule), ok in per_filing.items()]
        if args.outcomes_dir:
            from finops.core import outcomes as decisions

            labelled += decisions.as_calibration_outcomes(
                decisions.read("units", None if args.outcomes_dir == "default" else Path(args.outcomes_dir)))
        cal = policy.fit("units", "a statement's unit (scale)", labelled,
                         fitted={**provenance(datasets=["sec-dev", "sec-dev-prior"]), "fitted_by": "scripts/eval_units.py",
                                 "statements": len(rows)})
        print("wrote", policy.save(cal))


if __name__ == "__main__":
    main()
