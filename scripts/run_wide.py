"""Measure the wide set (eval/wide, D66) in parallel, with results by industry, size and filing type.

    .venv/Scripts/python scripts/run_wide.py --save before            # the tuning half
    .venv/Scripts/python scripts/run_wide.py --split sealed --open-seal --save first-look    # once: logged in eval/wide/seal-log.txt

Each filing is graded with the profile for its industry, against a key built from the filing's own XBRL tags: a second
route to the numbers that never touches the table reader the spreader uses. Reports land in eval/reports/wide-<split>-<save>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any

from spreader.evaluation.ixbrl_truth import build_key
from spreader.evaluation.score import DocScore, score
from spreader.evaluation.truth import AnswerKey
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
WIDE = ROOT / os.environ.get("WIDE_SET", "eval/wide")
REPORTS = ROOT / "eval" / "reports"
PROFILE_FILES = {"us-bank": ROOT / "config/profiles/us-bank.yaml", "us-insurer": ROOT / "config/profiles/us-insurer.yaml",
                 "us-commercial": None}


def spread_profile_lines(profile: Any, skey: str) -> Any:
    return next(s.lines for k, s in profile.statements.items() if getattr(k, "value", k) == skey)


def one(item: tuple[str, dict[str, Any], bool]) -> dict[str, Any]:
    key_name, m, rebuild = item
    t0 = time.perf_counter()
    path = WIDE / "raw" / m["file"]
    key_path = WIDE / "keys" / f"{key_name}.json"
    data = path.read_bytes()
    profile = load_profile(PROFILE_FILES[m["profile"]])
    out: dict[str, Any] = {"doc": key_name, "sector": m["sector"], "size": m["size"], "form": m["form"], "profile": m["profile"],
                           "buckets": {}, "values": [], "error": None}
    try:
        if key_path.exists() and not rebuild:
            key = AnswerKey.load(key_path)
        else:
            cal = WIDE / "cal" / f"{key_name}_cal.xml"
            key, _ = build_key(path.name, data, profile, cal.read_bytes() if cal.exists() else None)
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key.save(key_path)
        ir = read_document(path.name, data)
        spread, _ = spread_document(ir, profile)
        s: DocScore = score(spread, key)
        out["buckets"] = dict(s.counts())
        out["statements"] = s.statements_found
        out["blockers"] = len([i for i in spread.review if i.severity.value == "blocker"])
        checks = [c for c in spread.checks if c.status.value != "skipped"]
        out["checks_run"], out["checks_failed"] = len(checks), sum(1 for c in checks if c.status.value == "fail")
        out["kinds"] = Counter(v.kind for v in s.values if v.kind)
        out["review_reasons"] = Counter(f.split(":")[0] for v in s.values if v.bucket == "correct_review" for f in v.flags)
        out["failed_checks"] = [c.id for c in checks if c.status.value == "fail"]
        # Was each statement's unit right? Its values match the key's only at the right scale.
        truth = {(t.line, t.period): t.value for t in key.spread}
        scales = {}
        for skey, res in spread.statements.items():
            lines = {ln.id for ln in spread_profile_lines(profile, skey)}
            pairs = [(v.value, truth[(v.line, v.period)]) for v in spread.values if v.line in lines and v.value and truth.get((v.line, v.period))]
            hits = sum(1 for a, b in pairs if abs(a - b) <= abs(b) * Decimal("0.001"))
            off = sum(1 for a, b in pairs if any(abs(a * f - b) <= abs(b) * Decimal("0.001") for f in (1000, 1000000, Decimal("0.001"), Decimal("0.000001"))))
            scales[skey] = {"rule": res.table.scale.rule, "right": hits, "off_by_scale": off}
        out["scales"] = scales
        out["values"] = [{"line": v.line, "period": v.period, "truth": str(v.truth), "predicted": None if v.predicted is None else str(v.predicted),
                          "bucket": v.bucket, "kind": v.kind, "flags": v.flags} for v in s.values
                         if v.bucket in {"wrong_auto", "wrong_review", "missing_silent", "missing_flagged"}]
    except Exception as exc:  # noqa: BLE001 - a crash is a result too
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    b: Counter[str] = Counter()
    for r in rows:
        b.update(r["buckets"])

    auto, wrong = b["correct_auto"] + b["wrong_auto"], b["wrong_auto"] + b["wrong_review"]
    present = b["correct_auto"] + b["correct_review"] + wrong
    total = present + b["missing_flagged"] + b["missing_silent"]
    pc = lambda n, d: round(n / d, 4) if d else None  # noqa: E731
    return {"filings": len(rows), "crashed": sum(1 for r in rows if r["error"]), "no_values": sum(1 for r in rows if not r["error"] and not total_of(r)),
            "values": total, "buckets": dict(b), "right": pc(b["correct_auto"] + b["correct_review"], total),
            "silent_wrong": [b["wrong_auto"], auto], "silent_rate": pc(b["wrong_auto"], auto), "right_alone": pc(b["correct_auto"], total),
            "caught": [b["wrong_review"], wrong], "blank_unflagged": [b["missing_silent"], total],
            "seconds_per_filing": round(sum(r["ms"] for r in rows) / 1000 / max(1, len(rows)), 1)}


def total_of(r: dict[str, Any]) -> int:
    return sum(v for k, v in r["buckets"].items() if k != "unjudged")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "sealed"])
    ap.add_argument("--save", required=True)
    ap.add_argument("--open-seal", action="store_true", help="required for the sealed half; the opening is logged")
    ap.add_argument("--rebuild-keys", action="store_true")
    ap.add_argument("--only", default=None, help="comma-separated filings")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()  # another collected set: set WIDE_SET=eval/vocab first, so the worker processes see it too
    if args.split == "sealed":
        if not args.open_seal:
            sys.exit("The sealed half is measured once: pass --open-seal to do that, knowing it is logged.")
        with (WIDE / "seal-log.txt").open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} opened: {args.save}\n")
    manifest = json.loads((WIDE / "manifest.json").read_text())
    items = [(k, m, args.rebuild_keys) for k, m in sorted(manifest.items()) if m["split"] == args.split
             and (not args.only or k in args.only.split(","))]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, items))
    report: dict[str, Any] = {"name": f"{WIDE.name}-{args.split}-{args.save}", "split": args.split, "wall_seconds": round(time.perf_counter() - t0, 1),
                              "all": summary(rows)}
    for field in ("sector", "size", "form", "profile"):
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(r[field], []).append(r)
        report[f"by_{field}"] = {k: summary(v) for k, v in sorted(groups.items())}
    report["documents"] = rows
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{report['name']}.json").write_text(json.dumps(report, indent=1, default=str))
    def line(k: str, s: dict[str, Any]) -> str:
        return (f"{k:20s} {s['filings']:3d} filings  right {s['right']}  alone {s['right_alone']}  silent {s['silent_wrong']}  "
                f"caught {s['caught']}  blank-unflagged {s['blank_unflagged']}  crashed {s['crashed']}  no-values {s['no_values']}  {s['seconds_per_filing']}s")
    print(line("ALL", report["all"]))
    if args.split == "dev":  # the sealed half's detail stays closed until the end
        for field in ("sector", "size", "form"):
            for k, s in report[f"by_{field}"].items():
                print(line(k, s))


if __name__ == "__main__":
    main()
