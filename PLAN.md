# Plan and status

Statement Spreader: financial statements (HTML, PDF, Excel) in; a standard spread out, where every
value is traced to its printed source, checked by accounting identities, and either auto-accepted
or sent to review. Measured against answer keys (SEC inline XBRL and synthetic statements), with an
ROI layer that separates what was measured from what is assumed.

## Architecture (src/spreader)

| Stage | Module | What it does |
|---|---|---|
| Read | `ingest/html_tables.py`, `ingest/pdf_tables.py`, `ingest/xlsx_tables.py` | File -> `DocumentIR`: tables of positioned tokens, each with a `SourceRef` (xpath / page+bbox / sheet!cell) |
| Lay out | `layout.py` | Value columns ("slots") from number positions; header rows; label + values per row |
| Detect | `detect.py` | Which table is which statement; periods from headers/titles; unit ("in millions") |
| Structure | `structure.py` | Sections, units (money/shares/per share), totals found by footing; period harmonisation across statements |
| Map | `mapping.py` | Row -> template line: memory, alias, section rules, fuzzy, structure, optional model; confidence + reason |
| Assemble | `spread.py` | One value per line and period, provenance steps, cost-sign rules, scale |
| Check | `checks.py`, `formulas.py` | Derived lines, accounting checks with rounding tolerance, ratios (safe formula language, no eval) |
| Review | `review.py` | Review items (blocker/warning/info) and the flags that decide auto-accepted vs sent to review |
| Service/API | `service.py`, `store.py`, `api.py`, `export.py` | SQLite, idempotent runs, append-only audit log, corrections, approval gate, Excel/CSV/JSON |
| ROI | `roi.py`, `roi_api.py` | Timed sessions (active time), assumptions, observed/estimated/hypothetical labels |
| Evaluation | `evaluation/*`, `scripts/run_eval.py` | iXBRL answer keys, synthetic keys, scoring buckets, Wilson ranges |
| Config | `config/profiles/us-commercial.yaml` | Template lines, aliases, section rules, checks, derived lines, ratios |
| Web | `web/` | React + TypeScript review workspace (built by a parallel agent) |

## Status (update as work lands)

- [x] HTML pipeline end to end; Apple 10-K: all runnable checks pass
- [x] SEC answer keys from inline XBRL; dev/holdout split by ticker hash (`scripts/fetch_sec.py`)
- [x] Service, store, API, exports, ROI model and routes
- [ ] PDF reader quality (printed SEC filings are the hard set; synthetic PDFs the clean set)
- [ ] Excel reader
- [ ] Synthetic corpus with adversarial cases (parallel agent)
- [ ] Frontend (parallel agent)
- [ ] Local LLM mapping tier + ablation
- [ ] Red team; docs (DECISIONS, TESTING, THREAT_MODEL, IMPROVEMENT_LOG)

## How to resume

1. `cd C:\Users\devin\Github\statement-spreader`; `git log --oneline`; read IMPROVEMENT_LOG.md.
2. `.venv\Scripts\python -m pytest -q` and `.venv\Scripts\python scripts\run_eval.py --split dev`.
3. Compare with the latest saved report in `eval/reports/` before and after any change.
