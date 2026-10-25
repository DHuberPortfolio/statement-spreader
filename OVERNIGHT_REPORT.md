# Overnight report: 2026-10-25

Branch `overnight-2026-10-25`, cut from `main` at 8e644a7. Written as the night goes, so it is useful wherever it
stops.

## Summary

(Filled in at the end of the night.)

## Task 1: flaky tests (done)

**What CI actually showed.** The only CI run on `main` (run 40148515260, commit 8e644a7) failed one job,
`python (3.11, lxml==5.2.*)`, on a different test from the one the work order names:
`tests/test_sheets.py::test_roi_quotes_the_first_scorings` with `KeyError: 'runs'` in `src/finops/roi.py:101`
(994 passed, 14 skipped, 1 failed). The other three jobs passed. So there were two problems, and I fixed both.

### 1a. The ROI page chose its source report by file time (a production bug, not only a test bug)

- **Root cause.** `finops.roi._latest(prefix)` returned the `recon-*`, `invoice-*` or `dq-*` report with the newest
  modification time. `eval/reports` also holds multi-seed reports (`recon-multiseed-v*`, a different shape with no
  `runs` key) and intermediate runs (`recon-v1`, `dq-check`, ...). After a `git clone` every file has roughly the
  checkout time, so the choice is arbitrary: on that CI runner it picked a multi-seed report and crashed.
  On this machine it quoted `recon-regress-dq` and `invoice-regress-dq`, intermediate regression runs, not the
  `recon-final` / `invoice-final` reports the README quotes (their rates and counts happen to be identical, checked).
- **Reproduced**: copying `eval/reports` to a temporary folder and touching `recon-multiseed-v1.json` gives the
  same `KeyError: 'runs'`.
- **Fix, where it starts**: each engine's ROI figures now come from a named report (`finops.roi.SOURCES`:
  `recon-final.json`, `invoice-final.json`, `dq-first-score-independent-2.json`); the scanner already read the
  `sheets-first-score-*` files by name, and its fallback to "the newest sheets-* file" (which would have quoted a
  tuned score) is removed: no first scoring means "not measured".
- **Test**: `test_roi_reads_named_reports_whatever_their_file_times` makes four unrelated reports the newest files
  and checks every engine still quotes its named report. It fails on the old code
  (`'recon-v1.json' == 'recon-final.json'`) and passes on the new.
- **Same pattern elsewhere**: `spreader.roi_api.silent_error_rate` also orders `latest-holdout` against `latest-all`
  by file time. Today only `latest-all` exists, so it is deterministic in practice; it is fixed properly in task 2,
  where every report gets a creation time and commit inside it.

### 1b. The scan test built its workbook twice

- **Root cause** (as the work order said): `_problem_book()` was called twice and openpyxl writes the save time,
  to the second, into `docProps/core.xml`; two builds in different seconds are different bytes, so "same bytes,
  same scan" failed whenever the clock ticked between them.
- **Fix**: build the bytes once, scan them twice.
- **Confirmed across a second boundary**: with `_problem_book` wrapped so every call starts in a new clock second,
  the old test passed 0 of 5 runs and the new one 5 of 5.
- **Searched the whole suite for the pattern** (a generated .xlsx built twice and compared by bytes or hash): no
  other case. The data-quality and reconciliation reuse tests send the same CSV text twice; the invoice test reuses
  one byte string; the statement corpus test compares two generated corpora, but that generator pins the timestamps
  (`evaluation/synthetic.py`, `_FIXED_TIME`). The spreadsheet and data-quality generators do *not* pin them; nothing
  compares their bytes today, but task 2's manifests will, so they are pinned there.

## Task 2: a versioned evaluation and a release gate

### Plan (written before starting)

- **What.** (1) A registry of every evaluation set (`finops.evalsets`): which files, or which generator and seed,
  make it up, and which files are its answer key. (2) `scripts/eval_manifest.py write|check` writes one committed
  manifest per set (`eval/manifests/<set>.json`: every file and its SHA-256, the key files and a key version, a
  dataset version = a hash of all of them) and checks the working tree against them. (3) Every report gets a
  `provenance` block: creation time, git commit and whether the tree was dirty, each dataset's version and whether
  it matches its committed manifest, and the configuration/profile version. (4) `scripts/release_gate.py` runs every
  set that lives in the repository (synthetic statements, reconciliation, invoices, data quality, spreadsheets),
  compares with a committed baseline (`eval/baseline/release-gate.json`) and exits 1 if a "bad" rate (silent errors,
  silent omissions, false matches, false touchless, missed faults, false quarantines, wrong claims) rises above the
  baseline's 95% upper bound, if any item that was right in the baseline is now wrong (per value for statements,
  per failure for the other engines), if a document crashes that did not before, or if a dataset's version is not
  the baseline's. (5) A CI step runs the manifest check and the gate. (6) TESTING.md documents it.
- **Why the per-item rule.** On the synthetic statement corpus the baseline has 6 silent errors in 13,452
  auto-accepted values; its 95% upper bound is about 0.1%, so the rate rule alone would let roughly a dozen new silent
  errors through. Every set is deterministic, so a new wrong value is a real change, not noise: it should stop a release
  until a person looks.
- **Generated sets need stable bytes.** The spreadsheet and data-quality generators write .xlsx files whose bytes
  carry the save time (task 1), so their dataset versions would change every second. They will write pinned
  timestamps, as the statement generator already does; the numbers they produce must stay identical (checked).
- **How measured.** The gate must pass on unchanged code against a baseline made from it, and must fail when a
  defect is planted on purpose (a test does that for each rule). Reports must stay byte-identical apart from the
  new `provenance` block.
- **What would make me revert.** Any engine figure moving because of this work.

### Result: done

- **Manifests.** 21 sets registered (`src/finops/evalsets.py`): SEC dev and holdout (filings recorded by the hashes in
  `eval/sec/manifest.json`, since they are not in the repository; keys and calculation links as the key), the
  synthetic statement corpus, reconciliation dev/holdout/stress, seven invoice folders, data-quality dev/holdout and
  two independent sets, spreadsheet seeds 31 and 32 and two independent sets. `eval_manifest.py check --files`:
  21 of 21 match, and every downloaded SEC filing on this machine matches its recorded hash.
- **Provenance on every report.** `finops.core.evaluation.write_report` (all four platform engines) and
  `scripts/run_eval.py` (statements) add a `provenance` block and a closing Markdown line. A subset run (`--only`)
  records itself as a subset rather than quoting the whole set's version. The statement ROI page now orders runs
  by the time a report records, not by file time (the same weakness as task 1a).
- **Generated workbooks.** The spreadsheet and data-quality generators wrote the save time into their .xlsx files,
  so a set's hash would change every second; they now use one shared `stable_xlsx`. Generated workbooks are hashed
  by their content (cells, types, formats, font colours, comments, names), because the zip bytes also depend on the
  openpyxl version and CI installs the newest allowed one. Scores before and after: identical
  (`var/overnight/gen-before.json` vs `gen-after.json`, not committed).
- **No figure moved.** Each engine's report re-run with the new code is identical to its committed final report
  apart from timings and provenance (recon-final, invoice-final, dq-final, sheets-final, syn-final).
- **The gate.** `scripts/release_gate.py` (logic in `src/finops/gate.py`) runs 21 in-repo sets in about 50 s and
  compares with `eval/baseline/release-gate.json`. On unchanged code: PASSED. Its figures agree with the final
  reports (statements: silent errors 6 of 13,452, silent omissions 252 of 14,517, as in `syn-final`).
  `tests/test_release_gate.py` (13 tests) plants a defect for every rule; end to end, the naive greedy matcher
  run against the committed baseline fails it on the stress set (new false automatic matches).
- **CI.** Each of the three Python jobs now runs `eval_manifest.py check` and the gate after the tests, and writes
  the gate's table to the job summary. Running it on all three jobs (lxml 6 on Python 3.11 and 3.13, lxml 5.2) also
  checks that the synthetic statement corpus spreads the same on Linux as on Windows, which was never measured.
- **Not covered by the gate:** the SEC filings (not in the repository). The dev split stays a manual step.
- **One test changed:** `test_dq.py::test_synthetic_sets_are_scored_and_stable` replaces `write_report` with a stub;
  the stub now accepts the new keyword arguments. No assertion changed.

## Assumptions made without anyone to ask

1. The work order's "flaky test" diagnosis was right, but it was not what failed CI; I fixed both and treated the
   ROI one as the CI failure to explain.

## Surprises and things I think are wrong

1. The ROI page has been quoting intermediate regression reports on this machine (same figures as the final ones,
   by luck, not by design).

## Decisions left for a person

(None yet.)

## Next steps (ranked)

(Filled in at the end of the night.)
