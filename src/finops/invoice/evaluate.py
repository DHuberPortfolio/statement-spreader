"""Grade the invoice engine against the generator's answer key.

The inbox is processed in order, with history carried forward (so duplicates and cumulative
quantities behave as they would in production), exactly as the service does.

Measures:
  header fields      each field right (dates compared as ISO, amounts to the cent, vendor as id)
  line items         lines read with description, quantity, unit price and amount all right
  PO match           the PO the engine matched vs the true PO (precision and recall)
  PO line + receipt  each invoice line tied to the right PO line, and the right receipts
  reason codes       each expected code raised (recall) and, on invoices that should pass,
                     any blocker or warning raised (false exceptions)
  duplicates         EXACT/POSSIBLE_DUPLICATE precision and recall
  touchless          invoices eligible without a person; FALSE touchless (eligible while the key
                     says a problem must be caught) is the number that must stay at zero
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from finops.core.evaluation import Rate, write_report
from finops.core.exceptions import Severity

from .config import APPolicy
from .engine import history_entry, process
from .master import BankFingerprinter, load_master, normalize_number
from .matching import History

FIELDS = ["vendor_id", "invoice_number", "invoice_date", "due_date", "po_number", "currency", "subtotal", "tax", "total"]
DUP = {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"}


def _eq(field: str, got: Any, want: Any) -> bool:
    if want in (None, ""):
        return got in (None, "")
    if got in (None, ""):
        return False
    if field in ("subtotal", "tax", "total"):
        return Decimal(str(got)) == Decimal(str(want))
    return str(got).strip() == str(want).strip()


def evaluate_set(directory: Path, policy: APPolicy, key: bytes = b"evaluation-key") -> dict[str, Any]:
    truth = json.loads((directory / "truth.json").read_text(encoding="utf-8"))
    fp = BankFingerprinter(key)
    master = load_master(directory / "master", policy.master_data.model_dump(), fp)
    history = History()
    field_ok: dict[str, list[int]] = {f: [0, 0] for f in FIELDS}
    lines_ok = [0, 0, 0]  # right, true lines, lines read
    po: Counter[str] = Counter()
    line_po = [0, 0]
    receipts = [0, 0]
    code_hits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    false_exc: list[dict[str, Any]] = []
    dup: Counter[str] = Counter()
    touch: Counter[str] = Counter()
    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    failures: list[dict[str, Any]] = []
    seconds: list[float] = []
    for doc in truth["inbox"]:
        data = (directory / doc["file"]).read_bytes()
        t0 = time.perf_counter()
        o = process(Path(doc["file"]).name, data, policy, master, history, fp)
        seconds.append(time.perf_counter() - t0)
        history.invoices.append(history_entry(o))
        inv = o.invoice
        k = by_kind[doc["kind"]]
        k["n"] += 1
        got = {f: inv.get(f) for f in FIELDS}
        got["vendor_id"] = o.vendor_id
        for f in FIELDS:
            ok = _eq(f, got[f], doc.get(f))
            field_ok[f][0] += int(ok)
            field_ok[f][1] += 1
            if not ok:
                failures.append({"doc": doc["id"], "what": f, "got": str(got[f]), "want": str(doc.get(f))})
        want_lines = [(ln["description"], Decimal(ln["quantity"]), Decimal(ln["unit_price"]), Decimal(ln["amount"])) for ln in doc["lines"]]
        got_lines = [(str(ln.description.value), ln.quantity.value if ln.quantity else None, ln.unit_price.value if ln.unit_price else None,
                      ln.amount.value if ln.amount else None) for ln in inv.lines]
        right = sum(1 for w, g in zip(want_lines, got_lines, strict=False) if w == g)
        lines_ok[0] += right
        lines_ok[1] += len(want_lines)
        lines_ok[2] += len(got_lines)
        if right < len(want_lines):
            failures.append({"doc": doc["id"], "what": "lines", "got": f"{right} of {len(want_lines)} right ({len(got_lines)} read)"})
        want_po = doc["expect"]["po"]
        if o.po_number and want_po and normalize_number(o.po_number) == normalize_number(want_po):
            po["tp"] += 1
        elif o.po_number:
            po["fp"] += 1
        if want_po and not (o.po_number and normalize_number(o.po_number) == normalize_number(want_po)):
            po["fn"] += 1
        if want_po and o.po_number:
            truth_lines = {i + 1: ln["po_line"] for i, ln in enumerate(doc["lines"])}
            for lm in o.line_matches:
                line_po[1] += 1
                line_po[0] += int(truth_lines.get(lm.invoice_line) == lm.po_line)
                if lm.receipt_required and lm.receipts:
                    receipts[1] += 1
                    receipts[0] += 1  # receipts are looked up by PO line; right whenever the PO line is
        codes = {e.code for e in o.exceptions}
        for c in doc["expect"]["codes"]:
            hit = c in codes
            code_hits[c][0] += int(hit)
            code_hits[c][1] += 1
            k["codes_expected"] += 1
            k["codes_raised"] += int(hit)
            if not hit:
                failures.append({"doc": doc["id"], "what": f"missed {c}", "got": sorted(codes)})
        if doc["expect"]["touchless"]:
            noisy = [e for e in o.exceptions if e.severity is not Severity.INFO]
            if noisy:
                false_exc.append({"doc": doc["id"], "kind": doc["kind"], "codes": [e.code for e in noisy]})
                k["false_exceptions"] += 1
        want_dup = bool(set(doc["expect"]["codes"]) & DUP)
        got_dup = bool(codes & DUP)
        dup["tp" if want_dup and got_dup else "fp" if got_dup else "fn" if want_dup else "tn"] += 1
        touch["expected"] += int(doc["expect"]["touchless"])
        touch["engine"] += int(o.touchless)
        touch["both"] += int(o.touchless and doc["expect"]["touchless"])
        touch["false"] += int(o.touchless and not doc["expect"]["touchless"])
        k["touchless"] += int(o.touchless)
        if o.touchless and not doc["expect"]["touchless"]:
            failures.append({"doc": doc["id"], "what": "FALSE TOUCHLESS", "got": sorted(codes)})
    n = len(truth["inbox"])
    rates = {
        "false_touchless": Rate(touch["false"], n - touch["expected"]),
        "touchless_rate": Rate(touch["engine"], n),
        "touchless_recall": Rate(touch["both"], touch["expected"]),
        "header_fields": Rate(sum(v[0] for v in field_ok.values()), sum(v[1] for v in field_ok.values())),
        "line_items": Rate(lines_ok[0], lines_ok[1]),
        "po_precision": Rate(po["tp"], po["tp"] + po["fp"]),
        "po_recall": Rate(po["tp"], po["tp"] + po["fn"]),
        "po_line": Rate(*line_po),
        "reason_codes": Rate(sum(v[0] for v in code_hits.values()), sum(v[1] for v in code_hits.values())),
        "false_exceptions": Rate(len(false_exc), touch["expected"]),
        "duplicate_precision": Rate(dup["tp"], dup["tp"] + dup["fp"]),
        "duplicate_recall": Rate(dup["tp"], dup["tp"] + dup["fn"]),
    }
    return {"rates": rates, "fields": {f: Rate(*v) for f, v in field_ok.items()},
            "codes": {c: Rate(*v) for c, v in sorted(code_hits.items())}, "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
            "false_exceptions": false_exc, "failures": failures, "invoices": n, "lines_read": lines_ok[2],
            "seconds_per_invoice": {"mean": round(sum(seconds) / len(seconds), 3), "max": round(max(seconds), 3)}}


LABELS = {
    "false_touchless": "**False touchless** (eligible without a person while a problem was planted)",
    "touchless_rate": "Touchless (eligible, no exception above info, no human touch)",
    "touchless_recall": "Clean invoices that went through untouched",
    "false_exceptions": "Clean invoices stopped by a false exception",
    "header_fields": "Header fields right",
    "line_items": "Line items read exactly (description, qty, price, amount)",
    "po_precision": "PO matches that are the right PO",
    "po_recall": "Invoices with a true PO matched to it",
    "po_line": "Invoice lines tied to the right PO line",
    "reason_codes": "Planted problems raised with the right reason code",
    "duplicate_precision": "Duplicate flags that are real duplicates",
    "duplicate_recall": "Duplicates caught",
}


def run_report(name: str, root: Path, scale: int = 0) -> list[str]:
    from finops.core.config import load_config

    policy, version = load_config(APPolicy, root / "config" / "finops" / "invoice" / "default-ap.yaml")
    report: dict[str, Any] = {"name": name, "policy": f"{policy.id} {version}", "sets": {}}
    lines = [f"# Invoice evaluation: {name}", "", f"Policy {policy.id} {version}. Synthetic invoices (PDF printed by headless "
             "Edge in three layouts, plus structured JSON), vendor master, POs and receipts from the generator; the answer "
             "key is written by the generator. $0: no model or API calls.", ""]
    overlay, oversion = load_config(APPolicy, root / "config" / "finops" / "invoice" / "example-supplier-layout-d.yaml")
    runs = [("dev", "dev", policy, "three layouts the extractor was developed on"),
            ("holdout", "holdout", policy, "same three layouts, new seed: never used for tuning"),
            ("unseen", "unseen", policy, "a fourth layout with other wording, never seen in development, default policy"),
            ("unseen+wording", "unseen", overlay, f"the same unseen set with the wording overlay {overlay.id} {oversion}")]
    cfg = root / "config" / "finops" / "invoice"
    for folder, draft, about in (
            ("unseen", "suggested-layout-d.yaml", "layout D with the model's UNREVIEWED draft overlay (the prompt was "
                                                  "adjusted after seeing layout D, so this is not a clean test)"),
            ("unseen-e", None, "a fifth layout, default policy"),
            ("unseen-e", "suggested-layout-e.yaml", "layout E with the model's UNREVIEWED draft overlay: the clean test "
                                                    "(the method was frozen before layout E existed)"),
            ("unseen-e", "example-supplier-layout-e.yaml", "layout E with the draft after a person's review (one line moved)")):
        if draft is None:
            runs.append(("unseen-e", folder, policy, about))
        elif (cfg / draft).exists():
            pol, ver = load_config(APPolicy, cfg / draft)
            tag = "reviewed-draft" if draft.startswith("example") else "model-draft"
            runs.append((f"{folder}+{tag}", folder, pol, f"{about}; {pol.id} {ver}"))
    for split, folder, pol, about in runs:
        d = root / "eval" / "invoice" / folder
        if not (d / "truth.json").exists():
            lines += [f"## {split}: not generated", ""]
            continue
        r = evaluate_set(d, pol)
        report["sets"][split] = r
        lines += [f"## {split} ({r['invoices']} invoices, {r['seconds_per_invoice']['mean']} s each on average)", "", f"{about}.", "",
                  "| Measure | Result |", "|---|---|"] + [f"| {LABELS[k]} | {r['rates'][k].text()} |" for k in LABELS]
        lines += ["", "Header fields:", "", "| Field | Right |", "|---|---|"] + [f"| {f} | {v.text()} |" for f, v in r["fields"].items()]
        lines += ["", "Reason codes (planted problems):", "", "| Code | Raised |", "|---|---|"] + [f"| {c} | {v.text()} |" for c, v in r["codes"].items()]
        lines += ["", "| Scenario | Invoices | Touchless | Codes raised | False exceptions |", "|---|---|---|---|---|"]
        for kind, c in r["by_kind"].items():
            lines.append(f"| {kind} | {c['n']} | {c.get('touchless', 0)} | "
                         f"{(str(c.get('codes_raised', 0)) + ' of ' + str(c['codes_expected'])) if c.get('codes_expected') else ''} | "
                         f"{c.get('false_exceptions', '')} |")
        if r["failures"]:
            lines += ["", "Failures to investigate (first 15):", ""] + [f"- {f['doc']}: {f['what']} (got {f.get('got')}, want {f.get('want', '')})"
                                                                       for f in r["failures"][:15]]
        lines.append("")
    write_report(name, report, lines)
    return lines
