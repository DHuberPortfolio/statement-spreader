"""Print the README's reconciliation and invoice result tables from saved reports.

    .venv/Scripts/python scripts/platform_table.py recon-final invoice-final

Every number comes from eval/reports/<name>.json; nothing is typed by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "eval" / "reports"


def t(r: dict) -> str:
    if not r or not r.get("d"):
        return "-"
    return f"{100 * r['n'] / r['d']:.1f}% ({r['n']:,} of {r['d']:,}; {100 * r['low']:.1f}-{100 * r['high']:.1f}%)"


def recon(name: str) -> None:
    rep = json.loads((REPORTS / f"{name}.json").read_text(encoding="utf-8"))
    print("| Set | Strategy | Records | **False automatic matches** | Pairings that need a person, auto-accepted | "
          "True automatic pairings settled | Pairings that need a person, proposed | Planted problems raised | Same result, rows shuffled |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key, run in rep["runs"].items():
        split, strategy = key.split(":")
        r = run["rates"]
        print(f"| {split} | {strategy} | {run['counts']['records']} | {t(r['false_match_rate'])} | {t(r['review_cases_auto_accepted'])} | "
              f"{t(r['auto_recall'])} | {t(r['review_cases_reaching_review'])} | {t(r['exception_recall'])} | "
              f"{'yes' if run['order_stable'] and run['exceptions_stable'] else 'NO'} |")
    s = rep.get("scale_run")
    if s:
        print(f"\nScale: {s['records']:,} records in {s['seconds']} s, completeness checks failed: {s['checks_failed']}. Source: `eval/reports/{name}.json`.")


def invoice(name: str) -> None:
    rep = json.loads((REPORTS / f"{name}.json").read_text(encoding="utf-8"))
    print("| Set | Invoices | **False touchless** | Touchless | Header fields right | Line items read exactly | "
          "Right PO matched | Planted problems raised | Duplicates caught |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key, s in rep["sets"].items():
        r = s["rates"]
        print(f"| {key} | {s['invoices']} | {t(r['false_touchless'])} | {t(r['touchless_rate'])} | {t(r['header_fields'])} | "
              f"{t(r['line_items'])} | {t(r['po_recall'])} | {t(r['reason_codes'])} | {t(r['duplicate_recall'])} |")
    print(f"\nSource: `eval/reports/{name}.json`.")


if __name__ == "__main__":
    recon(sys.argv[1] if len(sys.argv) > 1 else "recon-final")
    print()
    invoice(sys.argv[2] if len(sys.argv) > 2 else "invoice-final")
