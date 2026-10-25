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

CI (`.github/workflows/tests.yml`) runs the Python tests on every push after a fresh install of the newest allowed
dependencies on Linux, with Python 3.11 and 3.13, and once more with the oldest lxml the pin allows (5.2), then the
web tests. Linux matters because lxml's Linux wheels use a newer libxml2 than the Windows wheel (see
`test_html_reader_fixes.py`). Tests that need the downloaded SEC filings skip themselves there. Each Python job then
checks the evaluation manifests and runs the release gate (next section).

## Versioned evaluation sets and the release gate

Every evaluation set has a name, a **dataset version** and a **key version** (`src/finops/evalsets.py`): a hash of
every input and answer-key file, or, for generated sets, of what the generator writes for its seed (generated
workbooks are hashed by content, not by their zip bytes, which depend on the openpyxl version). The committed
manifests in `eval/manifests/` list every file and its SHA-256.

```bash
.venv/Scripts/python scripts/eval_manifest.py check            # every set against its manifest (CI runs this)
.venv/Scripts/python scripts/eval_manifest.py check --files    # also hash the downloaded SEC filings
.venv/Scripts/python scripts/eval_manifest.py write --only <set>   # after a deliberate change to a set or key
```

A change to a set or its answer key is allowed, but only on purpose: rewrite its manifest in the same commit and say
why. Every report (`eval/reports/*.json`) written from now on carries a `provenance` block: when it was made, the git
commit and whether the tree had uncommitted changes, each dataset's version and whether it matched its manifest, and
the configuration or profile version; the Markdown report ends with the same line. Reports written before 2026-10-25
have no such block.

The **release gate** runs every set that lives in the repository (the synthetic statement corpus in all three formats;
reconciliation dev, holdout and stress; nine invoice runs; the data-quality synthetic and independent sets; the
spreadsheet synthetic and independent sets: about 50 s) and compares it with `eval/baseline/release-gate.json`:

```bash
.venv/Scripts/python scripts/release_gate.py                    # exit 1 if anything got worse
.venv/Scripts/python scripts/release_gate.py --write-baseline   # after a change that was measured and kept
```

It fails when, on any set: the dataset version is not the baseline's; a document crashes that did not; a bad rate
(silent errors, silent omissions, false automatic matches, false touchless, faults missed, false quarantines, wrong
claims, ...) rises above the baseline's 95% upper bound; or any item that was right is now wrong (per value for
statements, where a value that moves from caught to silent counts too; per listed failure for the other engines; a
rising count where an engine reports only a count). The last rule is exact, not statistical, because every set is
deterministic: on the synthetic corpus the rate rule alone would let about a dozen new silent errors through.
Improvements pass and are listed; refresh the baseline to lock them in. The SEC filings are not in the repository, so
the gate does not cover them: changes to the statement engine are still measured on the dev split by hand (below).
`tests/test_release_gate.py` plants a defect for each rule, including the naive greedy matcher run against the
committed baseline.

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
- `test_recon.py` (reconciliation, 41 tests): money formats and tolerance boundaries, overlay validation, column
  mapping errors naming the column, unreadable rows as blockers, every matching rule (reference with formatting
  and late clearing, ambiguity not guessed, the greedy control that does guess, mutual best, amount differences,
  far-apart amounts, currencies, batch with and without a reference, two possible subsets), leftover reasons,
  row-order independence, completeness checks, a known-answer bar on an unseen seed, and the service: reuse of an
  identical run, interrupted runs, decisions carried over, invalidated by a changed record, rejections remembered,
  latest-run-only, named reviewers and notes, append-only decisions and audit chain, profile path traversal;
  partial matches (and that a sum wins over a partial); a company overlay reading a differently shaped export.
- `test_invoice.py` (invoices, 30 tests): each layout's header, lines and evidence; multi-page tables; 13 planted
  problems each blocking or holding the invoice; amounts reported never corrected; bank numbers never stored in
  full; two-way service lines; cumulative quantities across invoices; exact, re-typed and look-alike duplicates;
  failing closed on unknown vendors, missing fields and damaged files; a known-answer bar; the service (same file
  twice is one invoice, corrections keep the original, bank-change segregation of duties); the HTTP routes end to
  end, including cross-site refusal.
- `test_invoice_redteam.py` (7 tests): hidden white bank account, tiny fake total, two bank accounts, borrowed tax
  id, credit note, instructions addressed to a model, CSV formula injection. Fixtures:
  `scripts/make_invoice_redteam.py`.
- `test_review_fixes.py` (20 tests): one per reproduced finding of the independent red-team review (THREAT_MODEL.md),
  plus two of its unreproduced hypotheses closed anyway (two decisions at once; a credit note freeing PO quantity).
- `test_accuracy_iteration.py` (11 tests): corroboration, mangled bank names, payroll bursts, late-clearing proposals, partial
  claims, label-looking values, and the messy mixed-layout invoice set read exactly.
- `test_period_anchoring.py` (3 tests, need the cached SEC filings): columns dated from the balance sheet (Disney), late-December years kept (Hasbro), calculated lines flagged in assumed columns.
- `test_html_reader_fixes.py` (6 tests; one needs the cached filings): a second HTML document in one file is read
  even by a parser that stops at the first `</html>` (simulated: the Windows lxml wheel does not stop there); text
  sized inside a `font-size:0` wrapper is read (Deckers); text at a zero font size, including `0.0pt` and a
  stylesheet class, stays hidden.
- `test_cli.py` (3 tests): the `spreader` command that pyproject.toml declares (spread to JSON and Excel, refusal).
- `test_calc_links.py` (8 tests; three need the cached filings): the answer key's use of calculation links (a total and
  its part keep the total, a subtotal across template lines keeps the part, unlinked concepts still add, net income to
  common only as a fallback, Walmart's and Oracle's real linkbases), and a key rebuilt under three hash seeds comes
  out byte for byte the same.
- `test_assumed_scale.py` (1 test): a statement with an assumed unit flags its calculated lines too.
- `test_dq.py` (35 tests): the data-quality gate. Two schemas into one record (an identical copy loads once);
  every field and rule check rejects with its reason; US rules stay off abroad; suspicious records held;
  ambiguous dates held; duplicates flagged and never merged (similar names with different tax ids pass); one key
  in two versions holds both; bank changes held, with the last accepted version carried forward unless the new
  version blocks the vendor; purchase-order references, group consistency and outliers; Excel scientific notation
  rejected; exports masked and spreadsheet-safe; hostile files refused, never a crash; the shared reader refusing
  binary files and flagging unsaved formulas. Service: idempotent reruns, release/reject/correct rules, two-person
  correction, releases lapse when a record changes, append-only decisions, no full account number in the audit log
  or the browser. End to end: the gate's export loads into the invoice engine, and a vendor-master bank change
  lets a fraudulent invoice through without the gate and blocks it with the gate.
- `test_sheets.py` (35 tests): the spreadsheet risk scanner. References and relative form; plugs versus rates; every
  definite error (#REF!, missing sheet, unknown and broken names, loops, a number stored as text in a sum, saved
  error values reported at their source only); every risk, with the formula its neighbours imply and what depends on
  it; one finding for a mistake copied across a row; legitimate structure left alone (actuals before forecasts,
  full-year columns, input blocks, documented overrides, row-specific rates, subtotals, grand totals of subtotals,
  ROUND(x,0)-0.01); severity set in configuration; version comparison that ignores inserted rows and grown ranges and
  pairs a renamed sheet; hostile files and limits; the file unchanged after a scan; the command's exit codes; reviews
  (a named person, a reason, errors not dismissable, carried to the next version, append-only); a spreadsheet-safe
  export; the HTTP routes. Ten are regressions from the independent sets, each shown to fail with its fix removed.
- `test_invoice_suggest.py` (5 tests): value shapes; label candidates (unknown labels with values, not item rows);
  closed-list answers with a misbehaving fake model; an empty draft when no model server answers; the reviewed
  layout-E overlay reading the held-out set.

## Evaluation against answer keys

```bash
.venv/Scripts/python scripts/fetch_sec.py                       # download the SEC 10-Ks (fair-access rate)
.venv/Scripts/python scripts/fetch_sec_calc.py                  # and each filing's calculation links (for the keys)
.venv/Scripts/python scripts/run_eval.py --split dev            # tune on this
.venv/Scripts/python scripts/run_eval.py --split holdout        # measure on this; never tune on it
.venv/Scripts/python scripts/run_eval.py --split none --synthetic   # 40 cases x HTML, Excel, PDF
.venv/Scripts/python scripts/make_synthetic.py --out eval/synthetic --seed 7 --count 40   # regenerate
```

Reconciliation and invoices (synthetic known-answer sets; the generator writes the key):

```bash
.venv/Scripts/python scripts/run_eval.py --engine recon --save recon-final       # dev, holdout, stress; greedy vs component
.venv/Scripts/python -c "from pathlib import Path; from finops.invoice.synthetic import write; write(Path('eval/invoice/dev'), 21)"
.venv/Scripts/python scripts/run_eval.py --engine invoice --save invoice-final   # dev, holdout, unseen, unseen + overlay
```

The data-quality gate (synthetic sets with injected faults and legitimate oddities, seeds 21 and 22, plus every
independently written set found in `eval/dq/independent-*`; each also shows what happens without the gate):

```bash
.venv/Scripts/python scripts/run_eval.py --engine dq --save dq-final
.venv/Scripts/spreader gate --dataset config/finops/dq/vendors.yaml --source portal=portal.csv --source erp=erp.xlsx --previous last-accepted.csv --out out
```

`eval/dq/independent-*` were written by separate agents that saw only the dataset configurations and a description
of the policy, never the gate's code; each has a `truth.json` with the decision for every row and a README listing
the rows its author was unsure about. Count a set as held out only until a change is made because of it (its
README and IMPROVEMENT_LOG say when that happened).

The spreadsheet risk scanner (synthetic workbooks with planted problems and legitimate structure, seeds 31 and 32, plus
every independently written set in `eval/sheets/independent-*`, the hostile files, and a naive checker on the same
workbooks for comparison):

```bash
.venv/Scripts/python scripts/run_eval.py --engine sheets --save sheets-final
.venv/Scripts/spreader scan model-v2.xlsx --previous model-v1.xlsx --out scan-out
```

A claim is an anchor cell reported as error or risk (anomalies are listed, not counted); it is right when its cell
(or a grouped copy, or a loop cell) is a planted problem. The scoring rules were fixed before any independent set was
scored and are written at the top of `src/finops/sheets/evaluate.py`.

Harder tests and an independent second scorer:

```bash
.venv/Scripts/python scripts/stress_eval.py --seeds 10 --save recon-multiseed     # 10 seeds x clean/stress/messy, pooled
.venv/Scripts/python -c "from pathlib import Path; from finops.invoice.synthetic import write; write(Path('eval/invoice/messy-31'), 31, layouts='ABCDE', messy=True)"
.venv/Scripts/python scripts/export_wfeval.py                                        # outputs + keys as JSONL
node ../workflow-eval-harness/bin/wfeval.js score --config eval/wfeval/recon.config.json --pred eval/wfeval/recon-messy-101/pred.jsonl --key eval/wfeval/recon-messy-101/key.jsonl
```

Drafting wording for an unknown invoice layout with the local model (optional; answers cached in `var/`):

```bash
.venv/Scripts/python scripts/suggest_invoice_labels.py "eval/invoice/unseen-e/invoices/inv-00*.pdf" --n 3 --out config/finops/invoice/suggested-layout-e.yaml
```

The invoice sets are regenerated with `finops.invoice.synthetic.write` (seeds: dev 21, holdout 22, unseen 23 with
`layouts="D"`, unseen-e 24 with `layouts="E"`); PDFs are printed by headless Edge (about 50 s per set of 81).

Reports land in `eval/reports/<name>.md|.json`. Each value in an answer key ends in one bucket: right and
auto-accepted, right but sent to review, wrong but caught by review, **wrong and auto-accepted (silent
error)**, missing but flagged, missing and silent, or unjudged (the key cannot place a row the value
includes). Rates carry 95% Wilson ranges.

Before keeping a change: run the dev split and the synthetic corpus before and after, compare the saved
reports, and record the result in IMPROVEMENT_LOG.md.

A change to the answer keys (a scorer change) is measured the other way round: same engine, old keys against new.
Copy `eval/sec/keys` aside, rebuild with `run_eval.py --split all --rebuild-keys --save <name>` (`--no-calc` rebuilds
the keys without calculation links), then list every changed key value, the rates per split and the bucket changes
per filing:

```bash
.venv/Scripts/python scripts/compare_keys.py <old keys dir> eval/sec/keys --reports <old report> <new report>
```

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
