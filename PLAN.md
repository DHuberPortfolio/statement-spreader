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

## Status (2026-10-24, 11:35 ET)

- [x] HTML pipeline; SEC dev split 79.4% right, silent error rate 2.9% (dev-v3); holdout measured once (holdout-v2: 73.3%, 3.4%)
- [x] Excel reader; synthetic corpus (40 cases x 3 formats): 94.7% right, 0.1% silent (syn-v3)
- [x] Service, store, API, exports, ROI; 762 tests pass (59 product tests + 703 generator tests)
- [x] Frontend built and checked in a browser by its agent; I checked documents + workspace pages myself
- [x] Local model tier + ablation on dev (83.2% right, 2.2% silent with the model)
- [ ] PDF reader rework: parallel agent owns `ingest/pdf_tables.py`, `tests/test_pdf_reader.py`, `scripts/print_sec_pdfs.py` (uncommitted until its report)
- [ ] Red-team review: parallel agent, report pending; fix confirmed findings with regression tests
- [ ] Final evaluations running in background -> `eval/reports/dev-v3-model`, `holdout-v3`, `holdout-v3-model` (log: `var/final-evals.log`)
- [ ] README with verified results; PORTFOLIO.md row; memory note; handoff

## Running services (local only)
- llama-server: `C:\Users\devin\tools\llama.cpp\b11853\bin\llama-server.exe` on 127.0.0.1:8088 with
  `C:\Users\devin\tools\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (log `C:\Users\devin\tools\llama-server.log`)
- Demo app: `SPREADER_DATA=var/demo` uvicorn on 127.0.0.1:8766 (`scripts/load_demo.py var/demo` loads it)
- The frontend agent left a backend on 8765 (`var/dev-ui`) and Vite on 5173; stop them at the end.

## How to resume

1. `cd C:\Users\devin\Github\statement-spreader`; `git log --oneline`; read IMPROVEMENT_LOG.md.
2. `.venv\Scripts\python -m pytest -o addopts=""` and `.venv\Scripts\python scripts\run_eval.py --split dev`.
3. Compare with the latest saved report in `eval/reports/` before and after any change.
