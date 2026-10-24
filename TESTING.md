# Testing and evaluation

All commands run from the repository root in Git Bash or PowerShell. Python is `.venv/Scripts/python`.

## Setup (once)

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cd web && npm install && cd ..
```

## Automated tests

```bash
.venv/Scripts/python -m pytest -o addopts=""        # Python: pipeline, readers, service, ROI, generator
cd web && npm run typecheck && npm test && npm run build
```

What the Python tests cover:
- `test_numbers.py`, `test_formulas.py`: number parsing (property-based round trip), refusal of European
  grouping, the safe formula language (unsafe syntax rejected, missing inputs reported, Decimal exactness).
- `test_pipeline.py`: hand-worked statements: components not double-counted, totals by footing, cost signs,
  par-value equity lines, hidden rows, no unit statement as a blocker, a document that does not add up is
  flagged not fixed, year-only headers dated from the title, determinism.
- `test_xlsx_reader.py`: cell provenance, hidden rows, formulas without saved values, damaged workbooks.
- `test_service.py`: idempotent uploads, failed runs not half-written, the approval gate, audited corrections
  and remaps, no live formulas in exports.
- `test_roi.py`: hand-worked ROI, "not measured" below three sessions, no cash without an entered share, review
  time counted against the tool.
- `test_synthetic.py`: the synthetic generator's own accounting (every model balances and foots).
- `test_pdf_reader.py` (when present): PDF footers, wrapped labels, page segmentation.

## Evaluation against answer keys

```bash
.venv/Scripts/python scripts/fetch_sec.py                       # download the SEC 10-Ks (fair-access rate)
.venv/Scripts/python scripts/run_eval.py --split dev            # tune on this
.venv/Scripts/python scripts/run_eval.py --split holdout        # measure on this; never tune on it
.venv/Scripts/python scripts/run_eval.py --split none --synthetic   # 40 cases x HTML, Excel, PDF
.venv/Scripts/python scripts/make_synthetic.py --out eval/synthetic --seed 7 --count 40   # regenerate
```

Reports land in `eval/reports/<name>.md|.json`. Each value in an answer key ends in one bucket: right and
auto-accepted, right but sent to review, wrong but caught by review, **wrong and auto-accepted (silent
error)**, missing but flagged, missing and silent, or unjudged (the key cannot place a row the value
includes). Rates carry 95% Wilson ranges.

Before keeping a change: run the dev split and the synthetic corpus before and after, compare the saved
reports, and record the result in IMPROVEMENT_LOG.md.

## The local model tier (optional)

```bash
llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 99 -c 8192 --host 127.0.0.1 --port 8088
.venv/Scripts/python scripts/run_eval.py --split dev --model http://127.0.0.1:8088 --save dev-model
```

Responses are cached in `var/llm-cache.sqlite3`, so a rerun is repeatable and needs no GPU.

## Manual checks of the interface

```bash
.venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765   # serves web/dist too
```

Upload an SEC filing from `eval/sec/raw/`, a synthetic PDF and an Excel file; open a value, follow its
provenance to the source, correct it with a reason, resolve the review items, approve, export to Excel.
