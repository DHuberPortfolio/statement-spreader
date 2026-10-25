"""Grade a reconciliation run against the generator's answer key.

Measures (each with its Wilson range):
  auto-match precision      of matches made without a person, how many are exactly right
  false-match rate          1 - precision: the number that matters most; a wrong automatic
                            match hides a real discrepancy
  auto recall               of the true pairings that rules may settle alone, how many were
  found for review          of the true pairings that need a person, how many reached one as a
                            proposal (none should be auto-accepted)
  left-alone accuracy       records with no true counterpart that no automatic match swallowed
  exception recall          injected problems raised with the right reason code on the right record
  amount reconciled         share of money (bank side) settled by correct automatic matches
  rerun / order stability   the same files, rows shuffled, give the same matches

A pairing counts as right only when its record set is exactly the true one (or the key's
accepted alternative, e.g. which of two identical duplicate postings is the extra one).
"""

from __future__ import annotations

import csv
import io
import random
import time
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from finops.core.evaluation import Rate

from .config import ReconProfile
from .engine import reconcile
from .model import MatchStatus, ReconResult


def _members(left: list[str], right: list[str]) -> frozenset[str]:
    return frozenset(left + right)


def score(result: ReconResult, truth: dict[str, Any]) -> dict[str, Any]:
    index: dict[frozenset[str], dict[str, Any]] = {}
    for t in truth["groups"]:
        index[_members(t["left"], t["right"])] = t
        for alt in t["alternatives"]:
            index[_members(t["left"], alt)] = t
    auto = [g for g in result.groups if g.status in (MatchStatus.AUTO, MatchStatus.ACCEPTED)]
    proposed = [g for g in result.groups if g.status is MatchStatus.PROPOSED]
    auto_ok = [g for g in auto if _members(g.left, g.right) in index]
    false_auto = [g for g in auto if _members(g.left, g.right) not in index]
    found_auto = {id(index[_members(g.left, g.right)]) for g in auto_ok}
    found_prop = {id(index[_members(g.left, g.right)]) for g in proposed if _members(g.left, g.right) in index}
    review_violations = [g for g in auto_ok if index[_members(g.left, g.right)]["expect"] == "review"]

    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for t in truth["groups"]:
        k = by_kind[t["kind"]]
        k["cases"] += 1
        if id(t) in found_auto:
            k["auto_right"] += 1
        elif id(t) in found_prop:
            k["proposed_right"] += 1
        else:
            k["missed"] += 1
    in_auto = {m for g in auto for m in g.left + g.right}
    in_prop = {m for g in proposed for m in g.left + g.right}
    for g in false_auto:
        kinds = {t["kind"] for t in truth["groups"] if set(g.left + g.right) & set(t["left"] + t["right"])}
        kinds |= {n["kind"] for n in truth["no_counterpart"] if n["id"] in g.left + g.right}
        for kd in kinds or {"(unknown)"}:
            by_kind[kd]["false_auto"] += 1

    alone_ok = sum(1 for n in truth["no_counterpart"] if n["id"] not in in_auto)
    for n in truth["no_counterpart"]:
        k = by_kind[n["kind"]]
        k["alone_records"] += 1
        k["alone_left_alone"] += int(n["id"] not in in_auto)
        k["alone_proposed"] += int(n["id"] in in_prop)

    raised: dict[str, set[str]] = defaultdict(set)
    for e in result.exceptions:
        raised[e.code].update(e.subjects)
    exc_hits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    misses = []
    for x in truth["exceptions"]:
        hit = any(raised.get(c, set()) & set(x["any_of"]) for c in x.get("codes") or [x["code"]])
        exc_hits[x["code"]][0] += int(hit)
        exc_hits[x["code"]][1] += 1
        by_kind[x["kind"]]["exc_expected"] += 1
        by_kind[x["kind"]]["exc_raised"] += int(hit)
        if not hit:
            misses.append(x)
    clean = {m for t in truth["groups"] if t["expect"] == "auto" for m in t["left"] + t["right"]}
    noisy = [e for e in result.exceptions if e.subjects and set(e.subjects) <= clean]

    left_name = result.left_name
    total_amt = sum((abs(t.amount) for t in result.records.values() if t.source == left_name), Decimal(0))
    ok_amt = sum((abs(result.records[m].amount) for g in auto_ok for m in g.left), Decimal(0))
    n_auto_truth = sum(1 for t in truth["groups"] if t["expect"] == "auto")
    n_review_truth = sum(1 for t in truth["groups"] if t["expect"] == "review")
    rates = {
        "auto_precision": Rate(len(auto_ok), len(auto)),
        "false_match_rate": Rate(len(false_auto), len(auto)),
        "auto_recall": Rate(sum(1 for t in truth["groups"] if t["expect"] == "auto" and id(t) in found_auto), n_auto_truth),
        "review_cases_reaching_review": Rate(sum(1 for t in truth["groups"] if t["expect"] == "review" and id(t) in found_prop), n_review_truth),
        "review_cases_auto_accepted": Rate(len(review_violations), n_review_truth),
        "any_recall": Rate(len(found_auto | found_prop), len(truth["groups"])),
        "proposal_precision": Rate(sum(1 for g in proposed if _members(g.left, g.right) in index), len(proposed)),
        "left_alone_accuracy": Rate(alone_ok, len(truth["no_counterpart"])),
        "exception_recall": Rate(sum(v[0] for v in exc_hits.values()), sum(v[1] for v in exc_hits.values())),
        "unnecessary_exceptions": Rate(len(noisy), len(result.exceptions)),
        "records_auto_settled": Rate(sum(len(g.left) + len(g.right) for g in auto_ok), len(result.records)),
    }
    return {
        "rates": rates, "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "exceptions_by_code": {k: Rate(*v) for k, v in sorted(exc_hits.items())},
        "amount_reconciled_share": float(ok_amt / total_amt) if total_amt else None,
        "false_matches": [{"id": g.id, "rule": g.rule, "left": g.left, "right": g.right} for g in false_auto],
        "missed_exceptions": misses,
        "noisy_exceptions": [{"code": e.code, "subjects": e.subjects} for e in noisy],
        "counts": {"auto": len(auto), "proposed": len(proposed), "exceptions": len(result.exceptions),
                   "records": len(result.records)},
    }


def shuffled(data: bytes, seed: int) -> bytes:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    head, body = rows[0], rows[1:]
    random.Random(seed).shuffle(body)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([head] + body)
    return buf.getvalue().encode("utf-8")


def fingerprint(result: ReconResult) -> list[tuple[str, str, tuple[str, ...]]]:
    return sorted((g.status.value, g.rule, tuple(sorted(g.left + g.right))) for g in result.groups)


def evaluate(profile: ReconProfile, version: str, bank: bytes, ledger: bytes, truth: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    result = reconcile("bank.csv", bank, "ledger.csv", ledger, profile, version)
    seconds = time.perf_counter() - t0
    out = score(result, truth)
    again = reconcile("bank.csv", shuffled(bank, 1), "ledger.csv", shuffled(ledger, 2), profile, version)
    out["order_stable"] = fingerprint(again) == fingerprint(result)
    out["exceptions_stable"] = sorted(e.id for e in again.exceptions) == sorted(e.id for e in result.exceptions)
    out["seconds"] = round(seconds, 3)
    out["checks_failed"] = [c for c in result.checks if c["status"] != "pass"]
    return out


LABELS = {
    "false_match_rate": "**False-match rate** (wrong, of matches made without a person)",
    "auto_precision": "Automatic matches exactly right",
    "auto_recall": "True pairings the rules may settle alone, settled",
    "review_cases_reaching_review": "Pairings that need a person, proposed to one",
    "review_cases_auto_accepted": "Pairings that need a person, auto-accepted anyway",
    "any_recall": "All true pairings found (automatic or proposed)",
    "proposal_precision": "Proposals that are right",
    "left_alone_accuracy": "Records with no counterpart left unmatched",
    "exception_recall": "Injected problems raised with the right reason",
    "unnecessary_exceptions": "Exceptions on records that needed none",
    "records_auto_settled": "Records settled by correct automatic matches",
}


def run_report(name: str, profile_path: str, seeds: dict[str, int], scale: int, strategies: list[str],
               round_share: dict[str, float] | None = None) -> list[str]:
    from finops.core.config import load_config
    from finops.core.evaluation import write_report

    from .config import ReconProfile
    from .synthetic import generate

    base, version = load_config(ReconProfile, profile_path)
    report: dict[str, Any] = {"name": name, "profile": f"{base.id} {version}", "scale": scale, "runs": {}}
    lines = [f"# Reconciliation evaluation: {name}", "",
             f"Synthetic bank-vs-ledger sets (generator seeds {seeds}, scale {scale}), profile {base.id} {version}. "
             "The answer key is written by the generator, not computed by the matcher.", ""]
    for split, seed in seeds.items():
        bank, ledger, truth = generate(seed, scale, round_share=(round_share or {}).get(split, 0.0))
        for strategy in strategies:
            p = base.model_copy(update={"matching": base.matching.model_copy(update={"strategy": strategy})})
            r = evaluate(p, version, bank, ledger, truth)
            report["runs"][f"{split}:{strategy}"] = r
            rs = (round_share or {}).get(split, 0.0)
            lines += [f"## {split} (seed {seed}{f', {rs:.0%} round amounts' if rs else ''}), strategy `{strategy}`", "",
                      f"{r['counts']['records']} records, {r['counts']['auto']} automatic matches, {r['counts']['proposed']} "
                      f"proposals, {r['counts']['exceptions']} exceptions, {r['seconds']} s. Same result with rows "
                      f"shuffled: {'yes' if r['order_stable'] and r['exceptions_stable'] else 'NO'}. Completeness checks "
                      f"failed: {len(r['checks_failed'])}.", "", "| Measure | Result |", "|---|---|"]
            lines += [f"| {LABELS[k]} | {r['rates'][k].text()} |" for k in LABELS]
            lines += [f"| Bank-side money settled by correct automatic matches | {100 * (r['amount_reconciled_share'] or 0):.1f}% |", "",
                      "| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |",
                      "|---|---|---|---|---|---|---|---|"]
            for kind, c in r["by_kind"].items():
                alone = f"{c.get('alone_left_alone', 0)} of {c['alone_records']}" if c.get("alone_records") else ""
                exc = f"{c.get('exc_raised', 0)} of {c['exc_expected']}" if c.get("exc_expected") else ""
                lines.append(f"| {kind} | {c.get('cases', '')} | {c.get('auto_right', '')} | {c.get('proposed_right', '')} | "
                             f"{c.get('missed', '')} | {c.get('false_auto', '')} | {alone} | {exc} |")
            if r["false_matches"]:
                lines += ["", "False automatic matches:"] + [f"- {f['rule']}: {f['left']} + {f['right']}" for f in r["false_matches"][:10]]
            if r["missed_exceptions"]:
                lines += ["", "Problems not raised as expected:"] + [f"- {m['kind']}: {m['code']} on {m['any_of']}" for m in r["missed_exceptions"][:10]]
            lines.append("")
    big_bank, big_ledger, big_truth = generate(seeds.get("holdout", 11) + 100, scale * 10)
    t0 = time.perf_counter()
    big = reconcile("bank.csv", big_bank, "ledger.csv", big_ledger, base, version)
    report["scale_run"] = {"records": len(big.records), "seconds": round(time.perf_counter() - t0, 2),
                           "checks_failed": sum(1 for c in big.checks if c["status"] != "pass")}
    lines += ["## Scale", "", f"{len(big.records)} records reconciled in {report['scale_run']['seconds']} s "
              f"(one run, this machine); completeness checks failed: {report['scale_run']['checks_failed']}.", ""]
    from finops.evalsets import RECON_ROUND_SHARE, RECON_SCALE, RECON_SEEDS

    registered = scale == RECON_SCALE and all(RECON_SEEDS.get(sp) == sd and (round_share or {}).get(sp, 0.0) == RECON_ROUND_SHARE.get(sp, 0.0)
                                              for sp, sd in seeds.items())
    datasets: list[str | dict[str, Any]] = ([f"recon-{sp}" for sp in seeds] if registered else
                                            [{"name": f"recon-seed-{sd}", "version": None, "note": f"generated: seed {sd}, scale {scale}"}
                                             for sd in seeds.values()])
    write_report(name, report, lines, datasets=datasets, config={"profile": f"{base.id} {version}"})
    return lines
