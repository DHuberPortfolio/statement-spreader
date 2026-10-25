"""Measure company memory: does last year's approved spread make this year's safer?

    .venv/Scripts/python scripts/fetch_sec.py --prior && .venv/Scripts/python scripts/fetch_sec_calc.py --prior
    .venv/Scripts/python scripts/eval_company_memory.py --split dev --save company-memory-dev
    .venv/Scripts/python scripts/eval_company_memory.py --split holdout --save company-memory-holdout   # once

For each company: the prior-year 10-K is spread and "approved" against its own answer key, as a stand-in for an
analyst (the key's value replaces the engine's wherever the key has one, the key's line replaces a wrong mapping,
everything else stays as the engine spread it). Then the current 10-K is spread twice, without and with what that
approval left behind (spreader.company), and both are scored against the current key.

The comparison's review items are labelled with the keys: a *restatement* is a period where the current key's value
differs from the prior approval (the company changed the number); a *misread* is where this spread differs from the
current key (the engine read it wrong). Both, neither (a false alarm), or unknown (the current key has no value).
Writes eval/reports/<name>.json and .md, and the memory's labelled mapping outcomes as JSONL for calibrate.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from finops.core.evaluation import provenance, provenance_lines
from spreader.company import ApprovedValue, CompanyContext, confirmed_mappings, verdict_of
from spreader.contracts import Spread
from spreader.evaluation.ixbrl_truth import build_key
from spreader.evaluation.score import DocScore, score, summarize
from spreader.evaluation.stats import Rate
from spreader.evaluation.truth import AnswerKey
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import Profile, load_profile

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
REPORTS = ROOT / "eval" / "reports"


def prior_key(t: str, m: dict[str, Any], profile: Profile) -> AnswerKey:
    """The prior filing's answer key, built like the current ones (calculation links included) and cached."""
    path = SEC / "keys-prior" / f"{t}.json"
    if path.exists():
        return AnswerKey.load(path)
    raw = (SEC / "raw-prior" / m["file"]).read_bytes()
    cal = SEC / "cal-prior" / f"{t}_cal.xml"
    key, _ = build_key(m["file"], raw, profile, cal.read_bytes() if cal.exists() else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    key.save(path)
    return key


def approve_against_key(spread: Spread, key: AnswerKey, s: DocScore, company_id: str) -> CompanyContext:
    """What an analyst's approval of the prior spread would leave behind: corrected values and mappings."""
    scale = {}
    for r in spread.statements.values():
        for p in r.table.periods:
            scale.setdefault(p.key, r.table.scale.multiplier)
    approved: dict[tuple[str, str], ApprovedValue] = {}
    for v in spread.values:  # the engine's values first, as spread
        if v.value is not None:
            tol = Decimal(scale.get(v.period, 1)) / 2 * max(1, len(v.refs))
            approved[(v.period, v.line)] = ApprovedValue(v.period, v.line, v.value, tol, None, "prior", "analyst (key)")
    corrected: set[str] = set()
    for t in key.spread:  # then the analyst's corrections: the key wherever it has a value
        engine = approved.get((t.period, t.line))
        if engine is None or abs(engine.value - t.value) > engine.tolerance + t.precision / 2:
            corrected.add(t.line)  # the analyst changed (or added) this line's value
        approved[(t.period, t.line)] = ApprovedValue(t.period, t.line, t.value, t.precision / 2, None, "prior", "analyst (key)")
    mappings = confirmed_mappings(spread, corrected)
    wrong_rows = {c.row: c.line_truth for c in s.cells if c.found and c.mapping_ok is False and c.line_truth and c.row}
    for skey, res in spread.statements.items():
        rows = {r.index: r for r in res.table.rows}
        for row_key, line in wrong_rows.items():
            st, idx = row_key.split(":")
            if st != skey or int(idx) not in rows:
                continue
            row = rows[int(idx)]
            section = row.section.split(" > ")[-1] if row.section else ""
            mappings[(skey, row.label_clean, section)] = line  # the analyst moved the row to its right line
    return CompanyContext(company_id=company_id, mappings=mappings, approved=approved)


def rates(scores: list[DocScore]) -> dict[str, Rate]:
    b = summarize(scores).buckets
    auto = b["correct_auto"] + b["wrong_auto"]
    total = b["correct_auto"] + b["correct_review"] + b["wrong_auto"] + b["wrong_review"] + b["missing_flagged"] + b["missing_silent"]
    return {"accuracy": Rate(b["correct_auto"] + b["correct_review"], total), "silent_error_rate": Rate(b["wrong_auto"], auto),
            "silent_omission_rate": Rate(b["missing_silent"], total),
            "catch_rate": Rate(b["wrong_review"], b["wrong_review"] + b["wrong_auto"]),
            "unnecessary_review_rate": Rate(b["correct_review"], b["correct_review"] + b["correct_auto"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    ap.add_argument("--save", default=None)
    ap.add_argument("--outcomes", default=None, help="write memory.company mapping outcomes (JSONL) here")
    args = ap.parse_args()
    name = args.save or f"company-memory-{args.split}"
    profile = load_profile()
    cur_manifest = json.loads((SEC / "manifest.json").read_text())
    prior_manifest = json.loads((SEC / "manifest-prior.json").read_text())
    tickers = sorted(t for t, m in cur_manifest.items() if m["split"] == args.split and t in prior_manifest
                     and (SEC / "raw" / m["file"]).exists() and (SEC / "raw-prior" / prior_manifest[t]["file"]).exists())
    without, with_mem, prior_scores = [], [], []
    items_by: Counter[str] = Counter()
    verdicts: Counter[tuple[str, str]] = Counter()
    review_items = {"without": [], "with": []}
    newly_caught = newly_silent = 0
    crashes: list[str] = []
    outcomes: list[dict[str, Any]] = []
    per_doc = []
    for t in tickers:
        m, pm = cur_manifest[t], prior_manifest[t]
        try:  # a crash is a result: recorded and counted, never a reason to stop (as in run_eval.py)
            pkey = prior_key(t, pm, profile)
            praw = (SEC / "raw-prior" / pm["file"]).read_bytes()
            pspread, _ = spread_document(read_document(pm["file"], praw), profile)
            ps = score(pspread, pkey)
            prior_scores.append(ps)
            ctx = approve_against_key(pspread, pkey, ps, f"cik:{m['cik']}")
        except Exception as exc:  # noqa: BLE001
            crashes.append(f"{t} prior year: {type(exc).__name__}: {exc}")
            print(f"{t:6s} PRIOR YEAR CRASHED ({type(exc).__name__}: {exc}); not counted")
            continue
        key = AnswerKey.load(SEC / "keys" / f"{t}.json")
        ir = read_document(m["file"], (SEC / "raw" / m["file"]).read_bytes())
        try:
            base, _ = spread_document(ir, profile)
            mem, _ = spread_document(ir, profile, company=ctx)
        except Exception as exc:  # noqa: BLE001
            crashes.append(f"{t} current year: {type(exc).__name__}: {exc}")
            print(f"{t:6s} CURRENT YEAR CRASHED ({type(exc).__name__}: {exc}); not counted")
            continue
        sb, sm = score(base, key), score(mem, key)
        sb.document = sm.document = f"sec:{t}"
        without.append(sb)
        with_mem.append(sm)
        review_items["without"].append(len([i for i in base.review if i.severity.value != "info"]))
        review_items["with"].append(len([i for i in mem.review if i.severity.value != "info"]))
        bb = {(v.line, v.period): v.bucket for v in sb.values}
        for v in sm.values:
            was = bb.get((v.line, v.period))
            newly_caught += int(was == "wrong_auto" and v.bucket == "wrong_review")
            newly_silent += int(was == "wrong_review" and v.bucket == "wrong_auto")
        # The comparison's items, labelled with the keys.
        truth = {(tv.period, tv.line): tv for tv in key.spread}
        spread_val = {(v.period, v.line): v.value for v in mem.values}
        doc_items = []
        for it in mem.prior_items:
            period, line = it.periods[0], it.lines[0]
            tv, a, sv = truth.get((period, line)), ctx.approved[(period, line)], spread_val.get((period, line))
            if tv is None or sv is None:
                label = "unknown (no key value)"
            else:
                tol = tv.precision / 2 + a.tolerance
                misread, restated = abs(sv - tv.value) > tol, abs(tv.value - a.value) > tol
                label = ("misread and restatement" if misread and restated else "misread" if misread else
                         "restatement" if restated else "neither (false alarm)")
            items_by[label] += 1
            verdicts[(label, verdict_of(it))] += 1
            doc_items.append({"line": line, "period": period, "truth": label, "verdict": verdict_of(it), "message": it.message})
        # memory.company mapping outcomes, one per mapped row, for calibration
        rows: dict[str, list[Any]] = {}
        for c in sm.cells:
            if c.found and c.mapping_ok is not None and c.rule == "memory.company" and c.row:
                r = rows.setdefault(c.row, [True])
                r[0] = r[0] and bool(c.mapping_ok)
        outcomes += [{"method": "memory.company", "right": ok, "source": f"company-memory {args.split} answer keys"}
                     for (ok,) in rows.values()]
        per_doc.append({"doc": t, "prior_items": doc_items, "buckets_without": dict(sb.counts()), "buckets_with": dict(sm.counts()),
                        "memory_rows": len(rows), "memory_rows_right": sum(1 for (ok,) in rows.values() if ok)})
        print(f"{t:6s} prior items {len(doc_items):3d}  memory rows {len(rows):3d} ({per_doc[-1]['memory_rows_right']} right)  "
              f"silent {sb.counts().get('wrong_auto', 0)} -> {sm.counts().get('wrong_auto', 0)}")
    rw, rm = rates(without), rates(with_mem)
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0  # noqa: E731
    report: dict[str, Any] = {
        "name": name, "split": args.split, "documents": len(tickers) - len(crashes), "crashes": crashes,
        "without": {k: v.as_dict() for k, v in rw.items()}, "with": {k: v.as_dict() for k, v in rm.items()},
        "review_items_median": {"without": med(review_items["without"]), "with": med(review_items["with"])},
        "review_items_mean": {k: round(sum(v) / len(v), 1) if v else 0 for k, v in review_items.items()},
        "values_newly_caught": newly_caught, "values_newly_silent": newly_silent,
        "prior_items": dict(items_by), "verdicts": {f"{a} | {b}": n for (a, b), n in sorted(verdicts.items())},
        "memory_rows": sum(d["memory_rows"] for d in per_doc), "memory_rows_right": sum(d["memory_rows_right"] for d in per_doc),
        "prior_year_spread": {k: v.as_dict() for k, v in rates(prior_scores).items()}, "documents_detail": per_doc,
    }
    report["provenance"] = provenance([f"sec-{args.split}", f"sec-{args.split}-prior"],
                                      {"profile": f"{profile.id} {profile.version}+{profile.content_hash}"})
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    lines = [f"# Company memory: {name}", "", f"{len(tickers) - len(crashes)} {args.split} companies: the prior-year 10-K approved "
             "against its own key, then the current 10-K spread without and with what that approval left behind."
             + (f" Not counted, because the engine crashed: {'; '.join(crashes)}." if crashes else ""), "",
             "| Measure | Without memory | With memory |", "|---|---|---|"]
    for k, label in [("silent_error_rate", "**Silent error rate**"), ("catch_rate", "Wrong values caught by review"),
                     ("silent_omission_rate", "Silent omissions"), ("accuracy", "Values right"),
                     ("unnecessary_review_rate", "Right values sent to review")]:
        lines.append(f"| {label} | {rw[k].text()} | {rm[k].text()} |")
    lines.append(f"| Open review items per document | median {report['review_items_median']['without']}, mean "
                 f"{report['review_items_mean']['without']} | median {report['review_items_median']['with']}, mean "
                 f"{report['review_items_mean']['with']} |")
    lines += ["", f"Wrong values that were silent without memory and are caught with it: {newly_caught}; caught before and "
              f"silent now: {newly_silent}.", "",
              f"Rows placed by the company's confirmed mappings: {report['memory_rows']} judged, {report['memory_rows_right']} right.",
              "", "Comparison items (differences from the approved prior year), labelled with the keys:", "",
              "| What it really was | Items |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(items_by.items())]
    lines += ["", "What the item said, against what it really was:", "", "| Really | Item said | Items |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {n} |" for (a, b), n in sorted(verdicts.items())]
    lines += provenance_lines(report["provenance"])
    (REPORTS / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if args.outcomes:
        Path(args.outcomes).write_text("".join(json.dumps(o) + "\n" for o in outcomes), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
