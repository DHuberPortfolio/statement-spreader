# Plan and status

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

## Running services (local only)
- llama-server: `C:\Users\devin\tools\llama.cpp\b11853\bin\llama-server.exe` on 127.0.0.1:8088 with
  `C:\Users\devin\tools\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (log `C:\Users\devin\tools\llama-server.log`)
- Demo app: `SPREADER_DATA=var/demo` uvicorn on 127.0.0.1:8766 (`scripts/load_demo.py var/demo` loads it)
- (The frontend agent's servers on 8765 and 5173 were stopped at 11:40.)

## How to resume

1. `cd C:\Users\devin\Github\statement-spreader`; `git log --oneline`; read IMPROVEMENT_LOG.md.
2. `.venv\Scripts\python -m pytest -o addopts=""` and `.venv\Scripts\python scripts\run_eval.py --split dev`.
3. Compare with the latest saved report in `eval/reports/` before and after any change.
