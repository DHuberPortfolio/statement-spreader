"""Run the pipeline over the evaluation sets and grade it.

    .venv/Scripts/python scripts/run_eval.py                       # SEC dev split
    .venv/Scripts/python scripts/run_eval.py --split holdout       # SEC held-out split
    .venv/Scripts/python scripts/run_eval.py --synthetic           # synthetic corpus (all formats)
    .venv/Scripts/python scripts/run_eval.py --split all --save baseline-2026-10-24

Writes eval/reports/<name>.md and .json. Tuning must only ever look at the dev split; the
holdout split is for measuring, so its numbers are not fitted to.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from spreader.evaluation.ixbrl_truth import build_key
from spreader.evaluation.score import DocScore, score, summarize
from spreader.evaluation.stats import Rate
from spreader.evaluation.truth import AnswerKey
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
SYN = ROOT / "eval" / "synthetic"
REPORTS = ROOT / "eval" / "reports"


def sec_docs(split: str) -> list[tuple[str, Path, Path]]:
    manifest = json.loads((SEC / "manifest.json").read_text())
    out = []
    for t, m in sorted(manifest.items()):
        if split != "all" and m["split"] != split:
            continue
        raw = SEC / "raw" / m["file"]
        if raw.exists():
            out.append((t, raw, SEC / "keys" / f"{t}.json"))
    return out


def synthetic_docs(formats: list[str]) -> list[tuple[str, Path, Path]]:
    out = []
    for case in sorted(p for p in SYN.iterdir() if p.is_dir()):
        for fmt in formats:
            f = case / f"statement.{fmt}"
            if f.exists() and (case / "key.json").exists():
                out.append((f"{case.name}.{fmt}", f, case / "key.json"))
    return out


def rates(scores: list[DocScore]) -> dict[str, Rate]:
    b = summarize(scores).buckets
    present = b["correct_auto"] + b["correct_review"] + b["wrong_auto"] + b["wrong_review"]
    total = present + b["missing_flagged"] + b["missing_silent"]
    auto = b["correct_auto"] + b["wrong_auto"]
    wrong = b["wrong_auto"] + b["wrong_review"]
    return {
        "accuracy": Rate(b["correct_auto"] + b["correct_review"], total),
        "silent_error_rate": Rate(b["wrong_auto"], auto),
        "silent_omission_rate": Rate(b["missing_silent"], total),
        "review_rate": Rate(b["correct_review"] + b["wrong_review"], present),
        "catch_rate": Rate(b["wrong_review"], wrong),
        "unnecessary_review_rate": Rate(b["correct_review"], b["correct_review"] + b["correct_auto"]),
        "coverage": Rate(present, total),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "holdout", "all", "none"])
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--formats", default="html,xlsx,pdf")
    ap.add_argument("--save", default=None, help="report name (default: latest-<set>)")
    ap.add_argument("--only", default=None, help="comma-separated document ids")
    ap.add_argument("--rebuild-keys", action="store_true", help="rebuild SEC answer keys from the filings")
    args = ap.parse_args()

    profile = load_profile()
    docs: list[tuple[str, Path, Path]] = []
    if args.split != "none":
        docs += [("sec:" + t, raw, k) for t, raw, k in sec_docs(args.split)]
    if args.synthetic:
        docs += [("syn:" + n, f, k) for n, f, k in synthetic_docs(args.formats.split(","))]
    if args.only:
        wanted = set(args.only.split(","))
        docs = [d for d in docs if d[0] in wanted or d[0].split(":", 1)[1] in wanted]
    if not docs:
        sys.exit("no documents")

    scores: list[DocScore] = []
    per_doc: list[dict] = []
    t_all = time.perf_counter()
    for doc_id, path, key_path in docs:
        data = path.read_bytes()
        t0 = time.perf_counter()
        try:
            if key_path.exists() and not (args.rebuild_keys and doc_id.startswith("sec:")):
                key = AnswerKey.load(key_path)
            else:
                key, _ = build_key(path.name, data, profile)
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key.save(key_path)
            ir = read_document(path.name, data)
            spread, _ = spread_document(ir, profile)
            s = score(spread, key)
        except Exception as exc:  # a crash is a result too: record it, keep going
            s = DocScore(document=doc_id, source=doc_id.split(":")[0], error=f"{type(exc).__name__}: {exc}")
            spread = None

        s.document = doc_id
        scores.append(s)
        c = s.counts()
        checks = [ch for ch in (spread.checks if spread else []) if ch.status.value != "skipped"]
        per_doc.append({"doc": doc_id, "ms": round((time.perf_counter() - t0) * 1000), "error": s.error,
                        "statements": s.statements_found, "buckets": dict(c),
                        "checks_failed": sum(1 for ch in checks if ch.status.value == "fail"), "checks_run": len(checks),
                        "review_items": len([i for i in (spread.review if spread else []) if i.severity.value != "info"]),
                        "expected_review_missing": s.expected_review_missing, "forbidden_present": s.forbidden_present})
        flag = " ERROR " + s.error if s.error else ""
        print(f"{doc_id:42s} {per_doc[-1]['ms']:6d} ms  {dict(c)}{flag}")

    summ = summarize(scores)
    r = rates(scores)
    name = args.save or f"latest-{args.split}{'-syn' if args.synthetic else ''}"
    REPORTS.mkdir(parents=True, exist_ok=True)
    wrong = [(s.document, v) for s in scores for v in s.values if v.bucket in {"wrong_auto", "wrong_review", "missing_silent"}]
    report = {
        "name": name, "documents": len(scores), "crashed": sum(1 for s in scores if s.error),
        "seconds": round(time.perf_counter() - t_all, 1), "profile": f"{profile.id} {profile.version}+{profile.content_hash}",
        "buckets": dict(summ.buckets), "error_kinds": dict(summ.kinds),
        "rates": {k: v.as_dict() for k, v in r.items()},
        "cells": {k: {"ok": v[0], "total": v[1]} for k, v in summ.cells.items()},
        "documents_detail": per_doc,
        "errors": [{"doc": d, "line": v.line, "period": v.period, "truth": str(v.truth),
                    "predicted": None if v.predicted is None else str(v.predicted), "bucket": v.bucket, "kind": v.kind,
                    "status": v.status, "flags": v.flags} for d, v in wrong],
    }
    (REPORTS / f"{name}.json").write_text(json.dumps(report, indent=1, default=str))
    lines = [f"# Evaluation: {name}", "", f"{len(scores)} documents ({report['crashed']} crashed), profile {report['profile']}, "
             f"{report['seconds']} s.", "", "| Measure | Result |", "|---|---|"]
    labels = {"accuracy": "Spread values right (of all values in the answer keys)",
              "silent_error_rate": "**Silent error rate** (wrong, of values with no review item)",
              "silent_omission_rate": "Silent omissions (missing and nothing flagged)",
              "review_rate": "Values sent to review", "catch_rate": "Wrong values caught by review",
              "unnecessary_review_rate": "Right values sent to review anyway", "coverage": "Answer-key values present in the spread"}
    for k, label in labels.items():
        lines.append(f"| {label} | {r[k].text()} |")
    lines.append(f"| Not judged (the answer key cannot place a row the value includes) | {summ.buckets['unjudged']} values |")
    cells = summ.cells
    if cells["found"][1]:
        lines += ["", "Printed numbers (SEC cells located by the answer key's tags):", "", "| Measure | Result |", "|---|---|"]
        for k, label in [("found", "Found at the right source cell"), ("value", "Value read right"), ("period", "Period right"),
                         ("mapping", "Template line right (where the key can judge)")]:
            lines.append(f"| {label} | {Rate(*cells[k]).text()} |")
    lines += ["", "Wrong values by kind: " + (", ".join(f"{k} {n}" for k, n in summ.kinds.most_common()) or "none"), ""]
    misses = Counter((v.line, v.bucket) for _, v in wrong)
    lines += ["Most frequent problems (line, outcome):", ""] + [f"- {ln} {b}: {n}" for (ln, b), n in misses.most_common(25)]
    (REPORTS / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
