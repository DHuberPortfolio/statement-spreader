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

## Task 3: one uncertainty policy (done)

### Plan (written before starting)

Find where each engine decides "accept without a person". Statements: hand-set confidences per mapping path and a
review threshold. Reconciliation: a configured list of rules that auto-accept. Invoices, data quality, spreadsheets:
no confidences at all; deterministic checks decide. So only two engines have something to calibrate; all five need
the common finding shape. Measure statements on dev and the synthetic corpus before and after, holdout once;
reconciliation through its reports and the gate. Revert if silent errors rise anywhere.

### Result

- **The policy** (`src/finops/core/policy.py`, DECISIONS D35): a `Finding` shape for everything an engine asks a person
  to look at; automatic acceptance only on a *calibrated* method (95% lower bound of its measured accuracy clears the
  engine's bar), a *person*'s earlier decision (mapping memory) or a *derived* result (a total of rows that each
  passed). A never-measured method is reviewed; a model is always reviewed and its stated confidence is ignored.
- **Calibration** (`scripts/calibrate.py statements|recon`, files in `config/calibration/`): records the datasets and
  versions, commit, profile and outcome counts. Reviewer decisions can be added later as JSONL outcomes.
- **Statements** (IMPROVEMENT_LOG #19): one outcome per mapped row on the dev keys. What it found: the hand-set
  confidences were mostly optimistic. `catchall:cf_other_noncash` (0.82 by hand) was right 0 of 3 times and had been
  settling values alone; `alias.section` (0.97 by hand) measures 94.2%, at least 89.4%, below the 0.90 bar for critical
  lines. Dev: silent errors 60 of 2,536 (2.4%, 1.8-3.0%) -> 59 of 2,487 (2.4%, 1.8-3.0%); wrong values caught 162 ->
  163 of 222; accuracy and omissions unchanged; cost: right values sent to review 1,132 -> 1,180, median review items
  per filing 21 -> 24. Holdout, once: silent errors 55 of 2,139 (2.6%, 2.0-3.3%) -> 49 of 2,101 (2.3%, 1.8-3.1%);
  caught 366 -> 372 of 421 (86.9% -> 88.4%). Synthetic corpus: 6 silent errors before and after. Reports:
  `stmt-dev-before-policy`, `stmt-dev-policy`, `stmt-holdout-policy`.
- **Reconciliation** (O5): calibrated on 30 generated sets no evaluation uses (registered as `recon-calibration`).
  Every configured rule clears 0.98, so every report is reproduced exactly; the change is that a newly configured rule
  proposes until measured. One mistake caught on the way: the first fit counted proposals too and rated
  `one_to_many` at 60.9% (sums without a reference are proposed by design); the unit is now "what the rule settles
  alone".
- **Invoices, data quality, spreadsheets**: nothing confidence-driven to migrate (their decisions are deterministic
  checks); they and the other two now give findings in the shared shape (O6).
- **Tests** (`tests/test_policy.py`, 9): the policy's rules; the committed calibrations record their data; mapping
  confidence is the measured bound; with no calibration every rule-placed row is reviewed; an over-confident model
  is reviewed; an uncalibrated reconciliation rule proposes; every engine's findings have all five parts. Reverting
  each of the three decision points (review, mapping, matcher) makes at least one test fail.

### Choices worth a second look

- The bar is compared with the **lower bound**, not the point estimate D5 used. That is the cautious reading of
  "calibrated against measured outcomes"; it costs about three review items per filing.
- The reconciliation bar of 0.98 was picked after seeing that every current rule clears it. DECISIONS D35 says so.
- The profile's `confidence:` on catch-all rules is now ignored (kept so overlays load).

## Task 4: remember each company across years

### Plan (written before starting)

- **Identity.** A document gets a `company_id`: given by the uploader (any identifier an organisation uses), or, for an
  SEC filing, the CIK read from the filing's cover-page tag (`dei:EntityCentralIndexKey`). That is identification
  metadata, not a value, so D1 (values only from what a person can see) still holds; recorded in DECISIONS.
- **What is remembered, per company.** (a) Approved values: when a spread is approved, every value is written to an
  append-only table (company, period, line, value, run, approver); a later approval adds rows, nothing is ever updated
  or deleted (database triggers refuse it). (b) Confirmed mappings: the label-to-line mapping of every placed row in
  an approved spread, scoped to that company.
- **Reuse.** The mapping cascade tries the company's confirmed mappings first (rule `memory.company`), before the
  global reviewer memory and the rules. It is a calibrated method like any other (D35), measured on the evaluation
  below; until measured it is reviewed.
- **Comparison.** When a new document has a column for a period the company already has approved values for, every
  line that differs beyond the rounding tolerance raises a review item. It says which it most likely is, with the
  evidence: *likely a misread* when the ratio is a power of ten or the sign is flipped; *likely a restatement* when the
  document mentions a restatement, recast or reclassification; otherwise *restatement or misread: check the document*.
  The approved spread is never changed.
- **Evaluation.** Fetch the prior-year 10-K for each company (`scripts/fetch_sec.py --prior`, the SEC's fair-access
  rules), build its key, spread it and "approve" it against its own key (the key's values replace the engine's, and the
  key's line replaces a wrong mapping, as an analyst would before approving). Then spread the current year without and
  with memory and compare silent errors, wrong values caught, review workload, and the comparison items, which the keys
  can label: a restatement is where the prior key and the current key disagree on the comparative period; a misread is
  where the spread disagrees with the current key. Dev first; the holdout once.
- **Revert if** silent errors rise on dev or the comparison items are mostly noise.

### Result: done

| SEC 10-Ks, current year | Without memory | With memory |
|---|---|---|
| Dev (33 companies): silent errors | 59 of 2,487 (2.4%, 1.8-3.0%) | 20 of 2,913 (0.7%, 0.4-1.1%) |
| Dev: wrong values caught | 163 of 222 (73.4%) | 90 of 110 (81.8%) |
| Dev: values right / silent omissions | 81.5% / 2.2% | 92.3% / 1.2% |
| Dev: median review items per filing | 24 | 24 |
| Holdout (29 companies, once): silent errors | 47 of 2,053 (2.3%, 1.7-3.0%) | 10 of 2,334 (0.4%, 0.2-0.8%) |
| Holdout: wrong values caught | 366 of 413 (88.6%) | 350 of 360 (97.2%) |
| Holdout: values right / silent omissions | 73.9% / 3.9% | 81.7% / 2.4% |
| Holdout: median (mean) review items | 24 (23.2) | 26 (31.0) |

Reports: `company-memory-dev`, `company-memory-holdout` (and the two earlier dev runs, kept under names that say what
they were). No value went from caught to silent on either split.

- **Built**: `spreader/company.py`; store schema 3 (`approved_values`, `company_mappings`, `approval_withdrawals`,
  append-only by trigger; `documents.company_id`); `Service.upload(..., company_id)` (API form field; SEC filings
  default to their CIK); approval remembers, reopening withdraws; the run's idempotency key includes what was
  remembered. DECISIONS D36, THREAT_MODEL T38-T39, IMPROVEMENT_LOG #20, #21, O7.
- **Root causes found on the way.** (1) The cover page's standard sentence about "new or revised financial accounting
  standards" made every filing look restated (140 of 164 misreads were labelled restatements); the restatement words
  are now read only from the statements. (2) Remembering the rows behind a line the analyst corrected let three wrong
  values go silent the next year; a corrected line now confirms nothing behind it. (3) Deckers' prior-year 10-K
  crashed the engine (undated columns, #21); fixed with a hand-built test, after the holdout run, and the holdout was
  not re-run.
- **How good is the "which is it" label?** Measured with the keys. When it says *misread* it is usually right (19 of
  20 dev, 120 of 129 holdout). When it says *restatement* it is not reliable (3 of 5, 6 of 16). Most items say it
  cannot tell. On dev, 177 of 198 items the keys could judge were real misreads and none was a false alarm, so the
  items are worth a reviewer's time even when they cannot say which.
- **Limits.** The stand-in approval is perfect (the key), so remembered mappings are as good as an analyst's best day.
  The headline gain comes mostly from mappings: last year's corrections carry forward. No UI field for the company id
  yet (API only).

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
