"""ROI for the reconciliation and invoice engines, on the statement engine's ROI rules.

Reuses spreader.roi's Number and label vocabulary, and adds one label the mandate asks for:

    observed      measured here: rates from the known-answer evaluations (synthetic data!)
    imported      from a cited external source (none is used: no benchmark was verified)
    assumption    entered by a finance owner          default   a placeholder nobody entered
    estimated     arithmetic on the above

Each engine has its own task and its own minutes, so nothing is counted twice: a bank line
ticked off in reconciliation and an invoice keyed in AP are different work. The statement
engine's ROI stays where it is (spreader/roi.py, with timed sessions).

What this cannot claim: the automation rates are from synthetic sets, not production; the
minutes per item are placeholders until someone times real work; released hours are capacity,
not cash, unless a finance owner sets a cash-realisation share above 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spreader.roi import Number, wilson

DEFAULTS: dict[str, dict[str, tuple[float, str]]] = {
    "recon": {
        "records_per_month": (4000.0, "Bank and ledger lines reconciled per month (both sides). Placeholder."),
        "manual_seconds_per_record": (40.0, "Seconds to find and tick off one line by hand. Placeholder: time it."),
        "minutes_per_exception": (5.0, "Minutes to investigate and resolve one exception or proposal. Placeholder: time it."),
    },
    "invoice": {
        "invoices_per_month": (600.0, "Invoices received per month. Placeholder."),
        "manual_minutes_per_invoice": (7.0, "Minutes to key, match and code one invoice by hand. Placeholder: time it."),
        "minutes_per_exception_invoice": (9.0, "Minutes to work one invoice that stops in the exception queue. Placeholder."),
    },
    "dq": {
        "dq_records_per_month": (2000.0, "Records gated per month (vendor master, purchase-order lines). Placeholder."),
        "dq_error_share": (0.02, "Share of records with an error before the gate. Placeholder: the gate's first runs on real "
                                 "exports measure it."),
        "dq_minutes_per_held_record": (4.0, "Minutes for a person to resolve one held record. Placeholder: time it."),
        "dq_cost_per_bad_record_loaded": (0.0, "Cost of one bad record loaded into the next system (rework, a payment to the "
                                               "wrong account). Default 0: not claimed until a finance owner sets it."),
    },
    "sheets": {
        "sheets_workbooks_per_month": (30.0, "Workbooks reviewed per month (models, workpapers, close files). Placeholder."),
        "sheets_findings_per_workbook": (4.0, "Errors and risks the scanner reports per real workbook. Placeholder: the synthetic "
                                               "sets plant problems on purpose, so their count is not a guide."),
        "sheets_minutes_per_finding": (3.0, "Minutes to check one finding against the workbook. Placeholder: time it."),
        "sheets_cost_per_error_shipped": (0.0, "Cost of one spreadsheet error reaching a decision or a report. Default 0: not "
                                               "claimed until a finance owner sets it."),
    },
    "shared": {
        "analyst_hourly_cost": (75.0, "Fully loaded cost of one analyst hour. Placeholder."),
        "cash_realization_share": (0.0, "Share of released hours that becomes cash. Default 0: capacity, not savings."),
    },
}


# The report each engine's figures come from, named, never "the newest file": file times are arbitrary after a
# clone, and eval/reports also holds intermediate and multi-seed reports with other shapes. These are the reports the
# README quotes; change one here when a new run replaces it.
SOURCES = {"recon": "recon-final.json", "invoice": "invoice-final.json", "dq": "dq-first-score-independent-2.json"}


def _named(reports: Path, engine: str) -> dict[str, Any] | None:
    f = reports / SOURCES[engine]
    try:
        return {**json.loads(f.read_text(encoding="utf-8")), "_file": f.name}
    except (OSError, json.JSONDecodeError):
        return None


def _rate(d: dict[str, Any] | None) -> tuple[int, int] | None:
    return (int(d["n"]), int(d["d"])) if d and d.get("d") else None


def _obs(n_d: tuple[int, int] | None, unit: str, text: str) -> Number:
    if not n_d:
        return Number(None, "observed", unit, "Not measured: run scripts/run_eval.py for this engine.")
    n, d = n_d
    lo, hi = wilson(n, d)
    return Number(n / d, "observed", unit, text, lo, hi, d)


def compute(reports: Path, entered: dict[str, float] | None = None) -> dict[str, Any]:
    entered = entered or {}
    A: dict[str, float] = {}
    out: dict[str, Any] = {"engines": {}, "warnings": [
        "Automation rates are measured on synthetic known-answer sets, not on your data. Treat them as an upper "
        "bound until the engines run on a sample of real records.",
        "Minutes per item are placeholders until someone times real work; every money figure inherits that.",
        "No external benchmark is imported: none was verified, so none is quoted."]}
    assumptions: dict[str, Number] = {}
    for group in DEFAULTS.values():
        for k, (v, why) in group.items():
            A[k] = float(entered.get(k, v))
            assumptions[k] = Number(A[k], "assumption" if k in entered else "default", "", why)
    out["assumptions"] = {k: n.as_dict() for k, n in assumptions.items()}
    rate, cash = A["analyst_hourly_cost"], A["cash_realization_share"]

    rec = _named(reports, "recon")
    if rec:
        run = rec["runs"].get("holdout:component") or next(iter(rec["runs"].values()))
        counts = run["counts"]
        exc_per_record = counts["exceptions"] / counts["records"] if counts["records"] else None
        nums = {
            "false_match_rate": _obs(_rate(run["rates"]["false_match_rate"]), "share of automatic matches",
                                     f"Wrong automatic matches on the held-out synthetic set ({rec['_file']})."),
            "exceptions_per_record": Number(exc_per_record, "observed", "exceptions per record",
                                            "Exceptions raised per record on the held-out synthetic set (built with many "
                                            "planted problems, so higher than a typical month)."),
            "records_auto_settled": _obs(_rate(run["rates"].get("records_auto_settled")), "share of records",
                                         "Records settled by correct automatic matches (no person needed)."),
        }
        settled = nums["records_auto_settled"].value or 0.0
        R, tick, exc_min = A["records_per_month"], A["manual_seconds_per_record"], A["minutes_per_exception"]
        investigate = R * (exc_per_record or 0) * exc_min / 60  # the same problems must be worked either way
        manual_h = R * tick / 3600 + investigate
        assisted_h = R * (1 - settled) * tick / 3600 + investigate
        nums["hours_by_hand"] = Number(manual_h, "estimated", "hours per month",
                                       "Tick off every record (assumed seconds) + investigate the problems (assumed minutes x "
                                       "observed exception rate).")
        nums["hours_with_engine"] = Number(assisted_h, "estimated", "hours per month",
                                           "Tick off only records not settled automatically + the same investigation time. "
                                           "No claim that the engine makes investigation faster.")
        nums["hours_released"] = Number(manual_h - assisted_h, "estimated", "hours per month", "By hand minus with the engine.")
        nums["cash_value"] = Number((manual_h - assisted_h) * rate * cash, "estimated", "$ per month",
                                    "Released hours x hourly cost x cash-realisation share (default 0).")
        out["engines"]["recon"] = {k: v.as_dict() for k, v in nums.items()} | {"source": rec["_file"]}

    inv = _named(reports, "invoice")
    if inv:
        s = inv["sets"].get("holdout") or next(iter(inv["sets"].values()))
        touch = _rate(s["rates"]["touchless_rate"])
        nums = {
            "touchless_rate": _obs(touch, "share of invoices", f"Invoices eligible with no person on the held-out synthetic set "
                                   f"({inv['_file']}); the set plants a problem in nearly half of them."),
            "false_touchless": _obs(_rate(s["rates"]["false_touchless"]), "share of problem invoices",
                                    "Problem invoices that went through untouched (must stay at 0)."),
        }
        t = nums["touchless_rate"].value or 0.0
        N, key_min, exc_min = A["invoices_per_month"], A["manual_minutes_per_invoice"], A["minutes_per_exception_invoice"]
        investigate = N * (1 - t) * exc_min / 60  # problem invoices are worked either way
        manual_h = N * key_min / 60 + investigate
        assisted_h = N * (1 - t) * key_min / 60 + investigate  # conservative: exception invoices still cost full keying time
        nums["hours_by_hand"] = Number(manual_h, "estimated", "hours per month",
                                       "Key and match every invoice (assumed minutes) + work the problem invoices.")
        nums["hours_with_engine"] = Number(assisted_h, "estimated", "hours per month",
                                           "Only invoices that stop in the queue cost keying time (assumed in full, though they "
                                           "arrive pre-read) + the same problem time. Approval in the ERP is left out of both.")
        nums["hours_released"] = Number(manual_h - assisted_h, "estimated", "hours per month", "By hand minus with the engine.")
        nums["cash_value"] = Number((manual_h - assisted_h) * rate * cash, "estimated", "$ per month",
                                    "Released hours x hourly cost x cash-realisation share (default 0).")
        out["engines"]["invoice"] = {k: v.as_dict() for k, v in nums.items()} | {"source": inv["_file"]}

    dq = _named(reports, "dq")
    if dq and dq.get("sets"):
        # The worst of the measured sets, never a pooled or best figure (the sets repeat similar records).
        scored = [s[part] for s in dq["sets"].values() for part in ("vendors", "purchase_orders") if part in s]
        rates = [(_rate(s["rates"]["faults_caught"]), _rate(s["rates"]["false_quarantine"])) for s in scored]
        caught = min((c for c, _ in rates if c), key=lambda nd: nd[0] / nd[1], default=None)
        false_q = max((f for _, f in rates if f), key=lambda nd: nd[0] / nd[1], default=None)
        nums = {
            "faults_caught": _obs(caught, "share of bad records", f"Bad records held or rejected, worst of the measured sets "
                                  f"({dq['_file']}: synthetic and independently written test exports)."),
            "false_quarantine": _obs(false_q, "share of valid records", "Valid records held for review anyway, worst of the "
                                     "measured sets: the cost of the checks."),
        }
        c, fq = nums["faults_caught"].value or 0.0, nums["false_quarantine"].value or 0.0
        R, e = A["dq_records_per_month"], A["dq_error_share"]
        mins, cost = A["dq_minutes_per_held_record"], A["dq_cost_per_bad_record_loaded"]
        nums["review_hours_added"] = Number(R * (e * c + (1 - e) * fq) * mins / 60, "estimated", "hours per month",
                                            "Held records x assumed minutes: time the gate adds. Without the gate this time is "
                                            "not saved; it moves downstream, to fixing what loaded.")
        nums["bad_records_stopped"] = Number(R * e * c, "estimated", "records per month",
                                             "Records x assumed error share x observed catch rate.")
        nums["bad_records_still_loaded"] = Number(R * e * (1 - c), "estimated", "records per month",
                                                  "What the gate would miss at the observed rate.")
        nums["value_of_stopped_records"] = Number(R * e * c * cost, "hypothetical", "$ per month",
                                                  "Stopped records x the cost of one bad record loaded (default 0: not claimed).")
        out["engines"]["dq"] = {k: v.as_dict() for k, v in nums.items()} | {"source": dq["_file"]}

    # The scanner's held-out figures are the first scorings of the independently written sets (each was used to fix
    # the scanner afterwards, so later scores on them are not held out). Worst of them, as for the gate.
    firsts = []
    for f in sorted(reports.glob("sheets-first-score-*.json")):
        try:
            firsts.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    sh: dict[str, Any] | None = {"sets": {k: v for r in firsts for k, v in r.get("sets", {}).items()},
          "_file": ", ".join(f.name for f in sorted(reports.glob("sheets-first-score-*.json")))} if firsts else None
    if sh and sh.get("sets"):
        precisions = [_rate(s["rates"]["precision"]) for s in sh["sets"].values()]
        recalls = [_rate(s["rates"]["recall"]) for s in sh["sets"].values()]
        worst_p = min((x for x in precisions if x), key=lambda nd: nd[0] / nd[1], default=None)
        worst_r = min((x for x in recalls if x), key=lambda nd: nd[0] / nd[1], default=None)
        nums = {
            "precision": _obs(worst_p, "share of reported errors and risks", f"Findings that were planted problems, worst first "
                              f"scoring of the independently written workbooks ({sh['_file']}; synthetic, not real models)."),
            "recall": _obs(worst_r, "share of planted problems", "Planted problems the scanner reported, worst first scoring of the independent sets."),
        }
        W, F, M = A["sheets_workbooks_per_month"], A["sheets_findings_per_workbook"], A["sheets_minutes_per_finding"]
        p_ = nums["precision"].value or 0.0
        nums["triage_hours"] = Number(W * F * M / 60, "estimated", "hours per month",
                                      "Workbooks x assumed findings per workbook x assumed minutes: the time the scanner adds. "
                                      "It replaces no review; it points the review at cells.")
        nums["real_problems_reported"] = Number(W * F * p_, "estimated", "findings per month",
                                                "Assumed findings x observed precision.")
        nums["value_of_problems_caught"] = Number(W * F * p_ * A["sheets_cost_per_error_shipped"], "hypothetical", "$ per month",
                                                  "Real problems x the cost of one error shipped (default 0: not claimed).")
        out["engines"]["sheets"] = {k: v.as_dict() for k, v in nums.items()} | {"source": sh["_file"]}
    return out


def _settled_share(run: dict[str, Any]) -> float | None:
    by_kind = run.get("by_kind", {})
    cases = sum(c.get("cases", 0) for c in by_kind.values())
    return (sum(c.get("auto_right", 0) for c in by_kind.values()) / cases) if cases else None
