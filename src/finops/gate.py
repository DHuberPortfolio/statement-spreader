"""The release gate: a run on every evaluation set that lives in the repository, compared with a committed baseline.

    .venv/Scripts/python scripts/release_gate.py                  # compare with eval/baseline/release-gate.json
    .venv/Scripts/python scripts/release_gate.py --write-baseline # after a change that was measured and kept

A run fails the gate when, on any set:
- the set's dataset version differs from the baseline's (a changed key or generator is never compared silently);
- a document crashes that did not crash before;
- a *bad* rate (silent errors, silent omissions, false automatic matches, false touchless, faults missed, false
  quarantines, wrong claims, ...) rises above the baseline's 95% Wilson upper bound;
- an item that was right in the baseline is now wrong. Every set is deterministic, so this is exact, not
  statistical: per value for statements (a value that moves from caught to silent counts too), per listed failure
  for the other engines, and, where an engine reports only a count, a count that rises.

The rate rule alone would be too loose to protect a release: on the synthetic statement corpus the baseline has 6
silent errors in 13,452 auto-accepted values, whose upper bound (about 0.1%) would let a dozen new ones through. The
SEC filings are not in the repository, so the gate does not cover them: the dev split is still measured by hand
before keeping a change (TESTING.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finops.core.evaluation import provenance
from finops.evalsets import DQ_SEEDS, EVAL, RECON_SCALE, RECON_SEEDS, ROOT, SHEETS_SEEDS, get
from spreader.evaluation.stats import Rate, wilson

BASELINE = EVAL / "baseline" / "release-gate.json"

# Statement value buckets by how bad they are: right, caught by review, silent.
SEVERITY = {"correct_auto": 0, "correct_review": 0, "unjudged": 0, "wrong_review": 1, "missing_flagged": 1,
            "wrong_auto": 2, "missing_silent": 2}


@dataclass
class SetResult:
    name: str
    dataset: str | None
    metrics: dict[str, tuple[int, int]] = field(default_factory=dict)  # bad count, out of
    failures: dict[str, int] = field(default_factory=dict)  # item id -> severity (1 caught, 2 silent; lists: 1)
    crashes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"dataset": self.dataset, "metrics": {k: list(v) for k, v in self.metrics.items()},
                "failures": dict(sorted(self.failures.items())), "crashes": sorted(self.crashes)}


def _bad(r: Rate) -> tuple[int, int]:
    return (r.n, r.d)


def _missed(r: Rate) -> tuple[int, int]:
    """A 'good' rate turned into the bad count it implies (planted problems not raised, fields read wrong)."""
    return (r.d - r.n, r.d)


# -- one runner per engine -------------------------------------------------------------------------------------------

def statements() -> list[SetResult]:
    from spreader.evaluation.score import score, summarize
    from spreader.evaluation.truth import AnswerKey
    from spreader.ingest import read_document
    from spreader.pipeline import spread_document
    from spreader.profile import load_profile

    profile = load_profile()
    res = SetResult("statements-synthetic", get("statements-synthetic").version)
    scores = []
    for case in sorted(p for p in (EVAL / "synthetic").iterdir() if p.is_dir()):
        key = AnswerKey.load(case / "key.json")
        for fmt in ("html", "xlsx", "pdf"):
            f = case / f"statement.{fmt}"
            if not f.exists():
                continue
            doc = f"{case.name}.{fmt}"
            try:
                spread, _ = spread_document(read_document(f.name, f.read_bytes()), profile)
                s = score(spread, key)
            except Exception as exc:  # a crash is a result: recorded, compared, never hidden
                res.crashes.append(f"{doc}: {type(exc).__name__}")
                continue
            scores.append(s)
            for v in s.values:
                if SEVERITY.get(v.bucket, 0):
                    res.failures[f"{doc} {v.line} {v.period}"] = SEVERITY[v.bucket]
            for k in s.expected_review_missing:
                res.failures[f"{doc} expected review item missing: {k}"] = 1
            for k in s.forbidden_present:
                res.failures[f"{doc} value that must not appear: {k}"] = 1
    b = summarize(scores).buckets
    present = b["correct_auto"] + b["correct_review"] + b["wrong_auto"] + b["wrong_review"]
    total = present + b["missing_flagged"] + b["missing_silent"]
    res.metrics = {"silent_errors": (b["wrong_auto"], b["correct_auto"] + b["wrong_auto"]),
                   "silent_omissions": (b["missing_silent"], total),
                   "wrong_values_not_caught": (b["wrong_auto"], b["wrong_auto"] + b["wrong_review"]),
                   "values_wrong_or_missing": (total - b["correct_auto"] - b["correct_review"], total)}
    return [res]


def recon() -> list[SetResult]:
    from finops.core.config import load_config
    from finops.evalsets import RECON_ROUND_SHARE
    from finops.recon.config import ReconProfile
    from finops.recon.evaluate import evaluate
    from finops.recon.synthetic import generate

    profile, version = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    out = []
    for split, seed in RECON_SEEDS.items():
        bank, ledger, truth = generate(seed, RECON_SCALE, round_share=RECON_ROUND_SHARE.get(split, 0.0))
        r = evaluate(profile, version, bank, ledger, truth)  # the default strategy (component)
        res = SetResult(f"recon-{split}", get(f"recon-{split}").version)
        rt = r["rates"]
        res.metrics = {"false_automatic_matches": _bad(rt["false_match_rate"]),
                       "need_a_person_but_auto_accepted": _bad(rt["review_cases_auto_accepted"]),
                       "pairings_not_found": _missed(rt["any_recall"]),
                       "planted_problems_not_raised": _missed(rt["exception_recall"]),
                       "no_counterpart_records_matched": _missed(rt["left_alone_accuracy"])}
        for f in r["false_matches"]:
            res.failures[f"false automatic match {f['rule']}: {sorted(f['left'])} + {sorted(f['right'])}"] = 2
        for m in r["missed_exceptions"]:
            res.failures[f"problem not raised: {m['kind']} {m['code']} on {sorted(m['any_of'])}"] = 1
        if not (r["order_stable"] and r["exceptions_stable"]):
            res.failures["result changes when the rows are shuffled"] = 2
        res.failures.update({f"completeness check failed: {c.get('name', c)}": 2 for c in r["checks_failed"]})
        out.append(res)
    return out


def invoices() -> list[SetResult]:
    from finops.core.config import load_config
    from finops.invoice.config import APPolicy
    from finops.invoice.evaluate import evaluate_set

    cfg = ROOT / "config" / "finops" / "invoice"
    default, _ = load_config(APPolicy, cfg / "default-ap.yaml")
    runs = [("dev", "dev", "default-ap.yaml"), ("holdout", "holdout", "default-ap.yaml"), ("unseen", "unseen", "default-ap.yaml"),
            ("unseen+wording", "unseen", "example-supplier-layout-d.yaml"), ("unseen-e", "unseen-e", "default-ap.yaml"),
            ("unseen-e+reviewed-draft", "unseen-e", "example-supplier-layout-e.yaml"),
            ("messy-31", "messy-31", "default-ap.yaml"), ("messy-32", "messy-32", "default-ap.yaml"),
            ("messy-33", "messy-33", "default-ap.yaml")]
    out = []
    for name, folder, policy_file in runs:
        if not (EVAL / "invoice" / folder / "truth.json").exists():
            continue
        policy = default if policy_file == "default-ap.yaml" else load_config(APPolicy, cfg / policy_file)[0]
        r = evaluate_set(EVAL / "invoice" / folder, policy)
        res = SetResult(f"invoice-{name}", get(f"invoice-{folder}").version)
        rt = r["rates"]
        res.metrics = {"false_touchless": _bad(rt["false_touchless"]), "false_exceptions": _bad(rt["false_exceptions"]),
                       "header_fields_wrong": _missed(rt["header_fields"]), "line_items_wrong": _missed(rt["line_items"]),
                       "planted_problems_not_raised": _missed(rt["reason_codes"]),
                       "duplicates_missed": _missed(rt["duplicate_recall"])}
        for f in r["failures"]:
            res.failures[f"{f['doc']}: {f['what']}"] = 2 if "TOUCHLESS" in f["what"] else 1
        for f in r["false_exceptions"]:
            res.failures[f"false exception: {f}"] = 1
        out.append(res)
    return out


def data_quality() -> list[SetResult]:
    from finops.core.config import load_config
    from finops.dq.config import DatasetSpec
    from finops.dq.engine import SourceInput, accepted_rows, gate
    from finops.dq.evaluate import _rows_csv, score, score_independent
    from finops.dq.synthetic import generate

    vspec, vver = load_config(DatasetSpec, ROOT / "config" / "finops" / "dq" / "vendors.yaml")
    pspec, pver = load_config(DatasetSpec, ROOT / "config" / "finops" / "dq" / "purchase_orders.yaml")
    scored: list[tuple[str, dict[str, Any]]] = []
    for split, seed in DQ_SEEDS.items():
        s = generate(seed)
        v = gate(vspec, [SourceInput("portal", "portal.csv", s.portal_csv), SourceInput("erp", "erp.xlsx", s.erp_xlsx)],
                 previous=("previous.csv", s.previous_csv), config_version=vver)
        p = gate(pspec, [SourceInput("erp", "po.csv", s.po_csv)],
                 references={"vendors": ("vendors.csv", _rows_csv(accepted_rows(v), v.columns))}, config_version=pver)
        scored.append((f"dq-{split}", {"vendors": score(v, s.vendor_truth, {}), "purchase_orders": score(p, s.po_truth, {})}))
    for folder in sorted((EVAL / "dq").glob("independent-*")):
        scored.append((f"dq-{folder.name}", score_independent(folder, vspec, pspec)))
    out = []
    for name, parts in scored:
        res = SetResult(name, get(name).version)
        for part in ("vendors", "purchase_orders"):
            rt = parts[part]["rates"]
            res.metrics[f"{part}_faults_missed"] = _bad(rt["faults_missed"])
            res.metrics[f"{part}_false_quarantine"] = _bad(rt["false_quarantine"])
            for m in parts[part]["misses"]:
                ident = f"{m.get('source')} row {m.get('row')}"
                note = m.get("note") or ("held although valid" if m.get("expect") == "accepted" else "missed")
                res.failures[f"{part} {ident}: {note} (got {m.get('got')})"] = 2 if note == "missed" else 1  # a missed fault would load; a held valid row costs time
        out.append(res)
    return out


def sheets() -> list[SetResult]:
    from finops.sheets.config import ScanSpec
    from finops.sheets.evaluate import folder_set, score_set, synthetic_set

    sets = [(f"sheets-synthetic-{seed}", lambda s=seed: synthetic_set(s)) for seed in SHEETS_SEEDS]
    sets += [(f"sheets-{f.name}", lambda f=f: folder_set(f)) for f in sorted((EVAL / "sheets").glob("independent-*"))]
    out = []
    for name, build in sets:
        books, pairs = build()
        r = score_set(books, pairs, ScanSpec())
        c = r["counts"]
        res = SetResult(name, get(name).version)
        res.metrics = {"wrong_claims": (c["claims"] - c["right"], c["claims"]), "planted_problems_missed": (c["faults"] - c["found"], c["faults"]),
                       "changes_missed": (c["pair_changes"] - c["pair_found"], c["pair_changes"]),
                       "false_changes": (c["pair_reported"] - c["pair_right"], c["pair_reported"])}
        for bn, bs in r["books"].items():
            for m in bs["missed"]:
                res.failures[f"{bn}: missed {m['kind']} at {m['sheet']}!{m['cell']}"] = 2
            for fa in bs["false_alarms"]:
                res.failures[f"{bn}: false alarm at {fa['cell']}"] = 1
        for pn, ps in r["pairs"].items():
            for m in ps["missed"]:
                res.failures[f"{pn}: change missed {m['kind']} at {m.get('sheet')}!{m.get('cell')}"] = 2
            for fa in ps["false_alarms"]:
                res.failures[f"{pn}: false change {fa['kind']} at {fa['sheet']}!{fa.get('cell')}"] = 1
        out.append(res)
    return out


RUNNERS: dict[str, Callable[[], list[SetResult]]] = {"statements": statements, "recon": recon, "invoice": invoices,
                                                     "dq": data_quality, "sheets": sheets}


def snapshot(engines: list[str] | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for engine in engines or list(RUNNERS):
        for r in RUNNERS[engine]():
            results[r.name] = {"engine": engine, **r.as_dict()}
    return {"sets": results, "provenance": provenance([], {})}


# -- the comparison -------------------------------------------------------------------------------------------------

def compare(baseline: dict[str, Any], run: dict[str, Any]) -> list[str]:
    """Every reason the run fails the gate (empty: it passes)."""
    problems: list[str] = []
    for name, base in baseline["sets"].items():
        now = run["sets"].get(name)
        if now is None:
            if base.get("engine") in {s.get("engine") for s in run["sets"].values()}:
                problems.append(f"{name}: in the baseline but not run")
            continue
        if base["dataset"] != now["dataset"]:
            problems.append(f"{name}: dataset version {now['dataset']} is not the baseline's {base['dataset']}; a changed set "
                            "needs a new baseline, made on purpose (--write-baseline) and explained in the commit")
            continue
        for c in sorted(set(now["crashes"]) - set(base["crashes"])):
            problems.append(f"{name}: new crash: {c}")
        for metric, (n, d) in now["metrics"].items():
            if metric not in base["metrics"]:
                continue
            bn, bd = base["metrics"][metric]
            hi = wilson(bn, bd)[1] if bd else 0.0
            if d and n / d > hi + 1e-12:
                problems.append(f"{name}: {metric} rose to {n} of {d} ({n / d:.2%}), above the baseline's 95% upper bound "
                                f"({bn} of {bd}, up to {hi:.2%})")
            elif n > bn and d == bd:
                problems.append(f"{name}: {metric} rose from {bn} to {n} (of {d}): at least one item that was right is now wrong")
        worse = [(k, sev) for k, sev in now["failures"].items() if sev > base["failures"].get(k, 0)]
        for k, sev in sorted(worse)[:25]:
            was = base["failures"].get(k, 0)
            problems.append(f"{name}: {k}: {'right' if was == 0 else 'caught'} in the baseline, now {'silent' if sev == 2 else 'caught by review'}"
                            if name.startswith("statements") else f"{name}: new failure: {k}")
        if len(worse) > 25:
            problems.append(f"{name}: ... and {len(worse) - 25} more items worse than the baseline")
    return problems


def improvements(baseline: dict[str, Any], run: dict[str, Any]) -> list[str]:
    out = []
    for name, base in baseline["sets"].items():
        now = run["sets"].get(name)
        if now is None or now["dataset"] != base["dataset"]:
            continue
        better = [k for k, sev in base["failures"].items() if now["failures"].get(k, 0) < sev]
        if better:
            out.append(f"{name}: {len(better)} item(s) better than the baseline (refresh the baseline to lock them in)")
    return out


def report_lines(baseline: dict[str, Any], run: dict[str, Any], problems: list[str]) -> list[str]:
    lines = ["# Release gate", "", f"Baseline: commit {(baseline['provenance'].get('commit') or '?')[:12]}, "
             f"{baseline['provenance']['created']}. This run: commit {(run['provenance'].get('commit') or '?')[:12]}"
             + (" with uncommitted changes" if run["provenance"].get("dirty") else "") + ".", "",
             "| Set | Measure | Baseline | This run |", "|---|---|---|---|"]
    for name, now in run["sets"].items():
        base = baseline["sets"].get(name, {"metrics": {}})
        for metric, (n, d) in now["metrics"].items():
            b = base["metrics"].get(metric)
            lines.append(f"| {name} | {metric} | {f'{b[0]} of {b[1]}' if b else '-'} | {n} of {d} |")
    lines += ["", f"**{'FAILED' if problems else 'PASSED'}**" + (f": {len(problems)} problem(s)" if problems else ""), ""]
    lines += [f"- {p}" for p in problems]
    better = improvements(baseline, run)
    if better:
        lines += ["", "Better than the baseline:", ""] + [f"- {b}" for b in better]
    return lines


def default_baseline_path() -> Path:
    return BASELINE
