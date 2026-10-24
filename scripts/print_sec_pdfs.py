"""SEC filings printed to PDF: the hard test set for the PDF reader.

    .venv/Scripts/python scripts/print_sec_pdfs.py                 # print every dev filing (skips existing)
    .venv/Scripts/python scripts/print_sec_pdfs.py --eval          # grade the printed SEC PDFs and the synthetic PDFs
    .venv/Scripts/python scripts/print_sec_pdfs.py --eval --set sec --save baseline --only AAPL,KO
    .venv/Scripts/python scripts/print_sec_pdfs.py --eval --reader saved/pdf_tables.py   # A/B: grade an older reader

Printing uses headless Edge, the way a person would "Print to PDF" a filing from a browser: the
statements come out as positioned words on pages (no table structure, no XBRL tags). The answer
keys are the same ones the HTML evaluation uses (eval/sec/keys/<TICKER>.json); cell-level scoring
needs HTML source paths and does not apply here, so only the spread-level buckets are graded.
The synthetic corpus (eval/synthetic/<case>/statement.pdf with key.json) is graded alongside it
and summarised separately: it is the clean set, the SEC printouts the hard one.

A document that crashes or is refused counts all its answer-key values as "crashed" (missing,
but loudly), so a fix that stops a crash cannot make the accuracy look worse.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
PDF_DIR = SEC / "pdf"
SYN = ROOT / "eval" / "synthetic"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def dev_filings() -> list[tuple[str, Path]]:
    manifest = json.loads((SEC / "manifest.json").read_text())
    return [(t, SEC / "raw" / m["file"]) for t, m in sorted(manifest.items()) if m["split"] == "dev"]


def print_pdf(html: Path, out: Path, timeout: int = 300) -> tuple[bool, str]:
    """Print one HTML file to PDF with headless Edge. Returns (ok, message)."""
    with tempfile.TemporaryDirectory(prefix="edge-print-") as profile_dir:
        cmd = [str(EDGE), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile_dir}",
               f"--print-to-pdf={out.resolve()}", html.resolve().as_uri()]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout} s"
    if not out.exists() or out.stat().st_size < 1000:
        return False, f"no PDF written (exit {proc.returncode})"
    return True, f"{out.stat().st_size / 1e6:.1f} MB"


def print_all() -> None:
    if not EDGE.exists():
        sys.exit(f"Edge not found at {EDGE}")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    t_all = time.perf_counter()
    for ticker, html in dev_filings():
        out = PDF_DIR / f"{ticker}.pdf"
        if out.exists():
            print(f"{ticker:6s} exists, skipped", flush=True)
            continue
        if not html.exists():
            print(f"{ticker:6s} no HTML at {html.name}", flush=True)
            continue
        t0 = time.perf_counter()
        ok, msg = print_pdf(html, out)
        print(f"{ticker:6s} {'ok' if ok else 'FAILED'} {msg} in {time.perf_counter() - t0:.0f} s", flush=True)
    print(f"done in {time.perf_counter() - t_all:.0f} s")


def _use_reader(path: str | None) -> None:
    """Swap in another copy of pdf_tables.py (worker initializer for A/B runs).

    The rest of the repository and the answer keys change while the reader is tuned; running the
    saved and the current reader side by side, on the same code and keys, isolates the reader.
    """
    if not path:
        return
    import importlib.util

    import spreader.ingest  # noqa: F401  (the parent package must be loaded for relative imports)

    spec = importlib.util.spec_from_file_location("spreader.ingest.pdf_tables", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["spreader.ingest.pdf_tables"] = module
    spec.loader.exec_module(module)


def _grade(args: tuple[str, str, str]) -> dict:
    """Run the pipeline on one PDF and score it (in a worker process)."""
    doc, pdf_path, key_path = args
    from spreader.evaluation.score import DocScore, score
    from spreader.evaluation.truth import AnswerKey
    from spreader.ingest import read_document
    from spreader.pipeline import spread_document
    from spreader.profile import load_profile

    t0 = time.perf_counter()
    spread = None
    key = AnswerKey.load(key_path)
    try:
        ir = read_document(Path(pdf_path).name, Path(pdf_path).read_bytes())
        spread, _ = spread_document(ir, load_profile())
        s = score(spread, key)
    except Exception as exc:  # a crash (or a refusal) is a result too
        s = DocScore(document=doc, source="pdf", error=f"{type(exc).__name__}: {exc}")
    stmts = spread.statements.items() if spread else []
    checks = [c for c in (spread.checks if spread else []) if c.status.value != "skipped"]
    return {
        "doc": doc, "ms": round((time.perf_counter() - t0) * 1000), "error": s.error,
        "statements": s.statements_found, "buckets": dict(s.counts()),
        "checks_failed": sum(1 for c in checks if c.status.value == "fail"), "checks_run": len(checks),
        "expected_review_missing": s.expected_review_missing, "forbidden_present": s.forbidden_present,
        "values": [{"line": v.line, "period": v.period, "truth": str(v.truth),
                    "predicted": None if v.predicted is None else str(v.predicted), "bucket": v.bucket, "kind": v.kind}
                   for v in s.values],
        "scales": {k: r.table.scale.multiplier for k, r in stmts},
        "periods": {k: [p.key for p in r.table.periods] for k, r in stmts},
        "pages": {k: sorted({v.ref.page for row in r.table.rows for v in row.values.values() if v.ref and v.ref.page})
                  for k, r in stmts},
        "key_values": len(key.spread),
        "expect_review": key.expect_review,
    }


def documents(which: str, only: list[str] | None) -> list[tuple[str, str, str]]:
    """(document id, PDF path, answer-key path) for the printed SEC filings and/or the synthetic PDFs."""
    out: list[tuple[str, str, str]] = []
    if which in {"sec", "all"}:
        for p in sorted(PDF_DIR.glob("*.pdf")):
            key = SEC / "keys" / f"{p.stem}.json"
            if key.exists():
                out.append((f"sec:{p.stem}", str(p), str(key)))
    if which in {"synthetic", "all"} and SYN.exists():
        for case in sorted(d for d in SYN.iterdir() if d.is_dir()):
            if (case / "statement.pdf").exists() and (case / "key.json").exists():
                out.append((f"syn:{case.name}", str(case / "statement.pdf"), str(case / "key.json")))
    if only:
        out = [d for d in out if d[0] in only or d[0].split(":", 1)[1] in only]
    return out


def summarize(results: list[dict]) -> tuple[dict[str, int], dict]:
    from spreader.evaluation.stats import Rate

    buckets: dict[str, int] = {}
    for r in results:
        for k, n in r["buckets"].items():
            buckets[k] = buckets.get(k, 0) + n

    def g(k: str) -> int:
        return buckets.get(k, 0)

    present = g("correct_auto") + g("correct_review") + g("wrong_auto") + g("wrong_review")
    total = present + g("missing_flagged") + g("missing_silent") + g("crashed")
    rates = {
        "accuracy": Rate(g("correct_auto") + g("correct_review"), total),
        "silent_error_rate": Rate(g("wrong_auto"), g("correct_auto") + g("wrong_auto")),
        "silent_omission_rate": Rate(g("missing_silent"), total),
        "coverage": Rate(present, total),
    }
    return buckets, rates


def evaluate(which: str, only: list[str] | None, jobs: int, save: str | None, reader: str | None = None) -> None:
    todo = documents(which, only)
    if not todo:
        sys.exit("no PDFs with answer keys")
    if reader:
        print(f"reader: {reader}")
    t_all = time.perf_counter()
    with ProcessPoolExecutor(max_workers=max(1, jobs), initializer=_use_reader, initargs=(reader,)) as ex:
        results = list(ex.map(_grade, todo))
    seconds = time.perf_counter() - t_all

    for r in results:
        if r["error"]:
            # A crash or a refusal is loud, not silent: the key's values are missing, and visibly so.
            r["buckets"] = {"crashed": r["key_values"]} if r["key_values"] else {}
        b = r["buckets"]
        right = b.get("correct_auto", 0) + b.get("correct_review", 0)
        notes = []
        if r["error"]:
            notes.append(f"ERROR {r['error'][:80]}")
        if r["expected_review_missing"]:
            notes.append(f"expected review missing {r['expected_review_missing']}")
        if r["forbidden_present"]:
            notes.append(f"forbidden present {r['forbidden_present']}")
        print(f"{r['doc']:24s} {r['ms'] / 1000:5.1f}s  right {right:3d}/{sum(b.values()):3d}  "
              f"wrong_auto {b.get('wrong_auto', 0):3d}  wrong_rev {b.get('wrong_review', 0):3d}  "
              f"miss_silent {b.get('missing_silent', 0):3d}  miss_flag {b.get('missing_flagged', 0):3d}  "
              f"stmts {len(r['statements'])}  checks {r['checks_run'] - r['checks_failed']}/{r['checks_run']}  "
              + "  ".join(notes))

    summary = {}
    for name in ("sec", "syn"):
        part = [r for r in results if r["doc"].startswith(name + ":")]
        if not part:
            continue
        buckets, rates = summarize(part)
        kinds: dict[str, int] = {}
        for r in part:
            for v in r["values"]:
                if v["kind"]:
                    kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
        print(f"\n[{name}] {len(part)} PDFs ({sum(1 for r in part if r['error'])} crashed or refused)")
        print(f"buckets: {dict(sorted(buckets.items()))}")
        print(f"wrong by kind: {kinds}")
        for k, rate in rates.items():
            print(f"{k:22s} {rate.text()}")
        summary[name] = {"buckets": buckets, "kinds": kinds, "rates": {k: v.as_dict() for k, v in rates.items()}}
    print(f"\n{len(results)} PDFs in {seconds:.0f} s with {jobs} workers")
    if save:
        out = PDF_DIR / f"eval-{save}.json"
        out.write_text(json.dumps({"name": save, "reader": reader, "seconds": round(seconds, 1), "summary": summary,
                                   "documents": results}, indent=1, default=str), encoding="utf-8")
        print(f"saved {out.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true", help="grade the PDFs instead of printing")
    ap.add_argument("--set", default="all", choices=["sec", "synthetic", "all"],
                    help="sec: eval/sec/pdf/*.pdf; synthetic: eval/synthetic/*/statement.pdf")
    ap.add_argument("--only", default=None, help="comma-separated document ids (AAPL, s7-005-clean, ...)")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--save", default=None, help="write eval/sec/pdf/eval-<name>.json")
    ap.add_argument("--reader", default=None, help="grade with this copy of pdf_tables.py instead (A/B runs)")
    args = ap.parse_args()
    if args.eval:
        evaluate(args.set, args.only.split(",") if args.only else None, args.jobs, args.save, args.reader)
    else:
        print_all()


if __name__ == "__main__":
    main()
