# Plan and status

Since 2026-10-24 afternoon this repository is a small finance operations platform: the statement spreader below
(engine one, unchanged), plus reconciliation (engine two) and invoice intake with three-way matching (engine
three) on a shared core. Platform architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Platform status is at the end
of this file.

Statement Spreader: financial statements (HTML, PDF, Excel) in; a standard spread out, where every
value is traced to its printed source, checked by accounting identities, and either auto-accepted
or sent to review. Measured against answer keys (SEC inline XBRL and synthetic statements), with an
ROI layer that separates what was measured from what is assumed.

## Architecture (src/spreader)

| Stage | Module | What it does |
|---|---|---|
| Read | `ingest/html_tables.py`, `ingest/pdf_tables.py`, `ingest/xlsx_tables.py` | File -> `DocumentIR`: tables of positioned tokens, each with a `SourceRef` (element path / page+bbox / sheet!cell); `preface` = cover-page text |
| Lay out | `layout.py` | Value columns ("slots") from number positions; header rows; label + values per row |
| Detect | `detect.py` | Which table is which statement; periods from headers/titles; unit ("in millions") |
| Structure | `structure.py` | Sections, units, totals by footing, period harmonisation (other statements, cover page), refusal of ambiguous numbers |
| Map | `mapping.py`, `llm/local.py` | Row -> template line: memory, total aliases, section rules, alias, fuzzy, structure, optional local model; confidence + reason |
| Assemble | `spread.py` | One value per line and period, provenance steps, cost-sign rules, scale |
| Check | `checks.py`, `formulas.py` | Derived lines, accounting checks with rounding tolerance, ratios (safe formula language) |
| Review | `review.py` | Review items and the flags that decide auto-accepted vs sent to review |
| Service/API | `service.py`, `store.py`, `api.py`, `export.py` | SQLite, idempotent runs, append-only audit log, corrections, approval gate, Excel/CSV/JSON |
| ROI | `roi.py`, `roi_api.py` | Timed sessions (active time), assumptions, observed/estimated/hypothetical labels |
| Evaluation | `evaluation/*`, `scripts/run_eval.py` | iXBRL keys, synthetic keys, buckets, Wilson ranges, mapping accuracy by method |
| Config | `config/profiles/us-commercial.yaml` | Template lines, aliases, section rules, checks, derived lines, ratios |
| Web | `web/` | React + TypeScript review workspace; `npm run build` -> `web/dist`, served by the API |

## Status (2026-10-24, 12:20 ET)

- [x] HTML, PDF and Excel readers; SEC answer keys from inline XBRL (dev/holdout by ticker hash); synthetic corpus
- [x] Service, store, API, exports, ROI, overlays with covenants; React review workspace (browser-checked)
- [x] Local model tier (Qwen3-4B, llama.cpp) with ablation; red team: 15 findings fixed with regression tests
- [x] PDF reader rewrite (printed SEC 10-Ks 43% -> 77% of values right)
- [x] Final evaluations: `eval/reports/*-final*.json`, SEC PDFs `eval/sec/pdf/eval-sec-pdf-final.json`; table via
      `scripts/results_table.py dev-final dev-final-model holdout-final holdout-final-model syn-final`
- [ ] Waits on Devin: repo visibility (nothing pushed); timed sessions so ROI can be measured (3 by hand + 3 assisted)
- Next ideas (ranked) in IMPROVEMENT_LOG.md "Next" section

## Services (none left running; start them when needed)
- Model server (optional): `C:\Users\devin\tools\llama.cpp\b11853\bin\llama-server.exe -m
  C:\Users\devin\tools\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 99 -c 8192 --host 127.0.0.1 --port 8088`,
  then set `SPREADER_MODEL_URL=http://127.0.0.1:8088` for the app or pass `--model` to `scripts/run_eval.py`.
- App: `.venv\Scripts\python scripts\load_demo.py var\demo`, then
  `SPREADER_DATA=var/demo .venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765`
  (build the web first: `cd web && npm install && npm run build`).

## How to resume

1. `cd C:\Users\devin\Github\statement-spreader`; `git log --oneline`; read IMPROVEMENT_LOG.md.
2. `.venv\Scripts\python -m pytest -o addopts=""` and `.venv\Scripts\python scripts\run_eval.py --split dev`.
3. Compare with the latest saved report in `eval/reports/` before and after any change.

## Platform status (2026-10-24, afternoon)

| Piece | Where | State |
|---|---|---|
| Shared core | `src/finops/core/` | money and tolerances, tables, validated overlays, fingerprints, exceptions, hash-chained audit log, rates and reports |
| Reconciliation | `src/finops/recon/`, `config/finops/recon/` | layered matcher, exception reasons, decisions, idempotent runs, completeness checks; 39 tests; dev, holdout and stress evaluations |
| Invoices | `src/finops/invoice/`, `config/finops/invoice/` | PDF/JSON extraction with evidence, arithmetic, PO/receipt matching, duplicates, vendor and bank controls, inbox with corrections; 30 + 7 red-team tests; dev, holdout, unseen-layout evaluations |
| API and UI | `src/finops/api.py` (mounted in `spreader/api.py`), `web/src/pages/ReconPage.tsx`, `InvoicesPage.tsx`, `FinopsRoi.tsx` | browser-checked on synthetic data (create, run, accept, refusal without a note, invoice detail with masked bank change) |
| ROI | `src/finops/roi.py`, ROI page section | observed-on-synthetic rates, placeholder minutes, estimated hours; editable assumptions |
| Evaluation | `scripts/run_eval.py --engine recon|invoice` | reports in `eval/reports/recon-*.md`, `invoice-*.md` |

Waits on Devin: review and commit (nothing of the platform is committed); a sample of real, anonymised records to
measure on; timed exception handling for ROI. Next steps ranked at the end of IMPROVEMENT_LOG.md.

Run the platform locally: build the web (`cd web && npm run build`), then
`SPREADER_DATA=var/demo .venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765` and open
/recon or /invoices ("Try sample data" / "Load the sample inbox" use the synthetic sets in `eval/`).
