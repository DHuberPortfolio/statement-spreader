# Overnight report: 2026-10-25

Branch `overnight-2026-10-25`, cut from `main` at 8e644a7. Written as the night goes, so it is useful wherever it
stops.

## Summary

All eight tasks were reached; seven are done and one (task 7, coverage) is done as a smoke test with partial
coverage, which is what a few hand-checked filings can honestly support. The flaky test was fixed, and so was CI's
actual failure: the ROI page picked its source reports by file time. Every evaluation set is now versioned, every
report records what produced it, and a release gate runs in CI. One uncertainty policy now governs automatic
acceptance in every engine. Auto-acceptance needs measured accuracy: it lowered silent errors on the never-tuned
holdout from 55 to 49, at about three more review items per filing. Company memory cuts silent errors on the SEC
holdout from 2.3% to 0.4% (47 of 2,053 to 10 of 2,334, measured once). The XBRL second reader is opt-in, measured
without the circular keys, and its gain is small. Flag narrowing gave a small, safe gain; no safe rule was found
for the balance-sheet sums. Bank, insurer and IFRS overlays were added with an honest smoke test. The README was
rewritten with a use-case summary and an architecture diagram.

Reverted or rejected along the way, each logged:
- a reconciliation calibration that mixed proposals in;
- a cover-page restatement signal that flagged every filing;
- remembering the rows behind corrected lines (three values went silent);
- same-statement confirmation for failed checks (three wrong values would have lost their flag).

Two general engine flaws were found and fixed: undated columns crashed a filing, and a parent-company-only
statement was spread as if consolidated. All work is on branch `overnight-2026-10-25`; nothing touched `main`.

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

## Task 5: XBRL tags as a second reader (opt-in)

### Plan (written before starting)

- **What it compares.** For every printed number the spread uses, the inline XBRL fact tagged on the same table cell
  (same cell path as the reader's provenance): the magnitude after scaling, and the period. The tag's sign is not
  compared: it follows the concept's convention, not what is printed. Three kinds of disagreement: *scale* (a power of
  ten apart), *value* (any other difference beyond rounding), *period* (same number, different period).
- **What it does.** Off by default (`SPREADER_XBRL_CHECK=1`, `spread_document(..., tags=...)`, `run_eval.py
  --xbrl-check`). A disagreement is a warning on the value's line and period, so that value is not accepted without a
  person. Agreement adds nothing to automation: making agreement a basis for auto-acceptance would need calibration
  against outcomes, and the only outcomes here come from the same tags.
- **How it is measured.** Not against the answer keys for any headline: they are built from the same tags, so the
  mode would look better than it is. Reported instead: how often the readers disagree on dev and the holdout, by kind,
  and, for a fixed random sample of disagreements, which reader was right, checked by me against the printed filing,
  each verdict recorded in `eval/xbrl-check/verdicts.json`. Labelled as not independent of the key source.

### Result: done (off by default)

**Not independent of the SEC answer keys** (same tags). Report `xbrl-check`.

| | Dev (33 filings) | Holdout (30) |
|---|---|---|
| Printed numbers with a tag on their cell | 6,233 | 5,381 |
| Readers agree | 96.8% (96.4-97.2%) | 91.7% (90.9-92.4%) |
| Disagree: scale / period / other value | 27 / 171 / 0 | 240 / 208 / 0 |
| Disagreements on values the tag-blind engine had not already sent to review | 5 | 19 |

- **Hand check.** 30 disagreements drawn at random (seed 20261025) and checked against each filing's text: the tag
  was right 29 times. The causes were unit statements printed once for the whole document (Deere), year-only and
  "Fiscal 2023" columns dated a year off (Snap-on, Target, Home Depot, Disney), and a fair-value table read as a
  statement (Merck). The printed reader was right once: McDonald's tags its share count as "713.4" with no scale.
  The sample is clustered (8 filings; Deere 11 of 30), so read it as "the tags are usually right when they disagree",
  not as a rate.
- **The honest bottom line.** Every sampled disagreement was on a value already sent to review by the default
  engine, and only 24 of 646 disagreements were new information. The mode is cheap insurance for public filers, not a
  big safety gain. Its most useful find: Home Depot's "Fiscal 2023" columns are dated a year early *without a flag*
  (19 values). That is a reader bug worth fixing, but it was found on the holdout, so it is in the next steps with
  the rule to reproduce it on a dev filing first.
- **One comparison bug fixed on the way:** opening and closing cash disagreed on "period" in every filing, because
  they are tagged as balances at a date (found on dev, Walmart).

## Task 6: narrow what a failed check flags (done; small gain)

- **What the data says (dev).** Values flagged *only* by failed checks: 716 right, 53 wrong. By check:
  `bs_assets_parts` 268 right / 10 wrong, `bs_liabilities_parts` 119 / 6, `bs_current_liabilities` 88 / 12,
  `is_pretax` 81 / 12.
- **Rule tried and rejected.** "An input confirmed by a passing check that shares no other input is not flagged"
  would unflag 219 right values and 3 wrong ones (Domino's closing cash and Oracle's net income to the company, each
  confirmed only by a check inside its own statement). Silent errors would rise, so no.
- **Rule kept** (IMPROVEMENT_LOG #22, `review._confirmed_elsewhere`): only confirmation against a *different
  statement* counts, and only if the confirming check's other inputs are not themselves in doubt. Dev: right values
  sent to review 1,180 -> 1,151, silent errors 59 (unchanged), caught 163 of 222 (unchanged). Holdout, once: 896 ->
  889, silent 49, caught 372 of 421 (both unchanged). Reports `stmt-dev-confirmed`, `stmt-holdout-confirmed`.
- **The honest result.** The gain is small (about 1 value per filing). The big source of over-flagging, the
  balance-sheet sum checks, is untouched: those lines have no check against another statement, and every rule I could
  justify for them would unflag a value that could be the cause. The work order allows "no such rule exists", and for
  the balance sheet that is my finding.
- **The 59 remaining dev silent errors**: 47 wrong values, 7 signs, 5 scales; mostly other non-operating income (9),
  common stock and APIC (8), commercial paper (5); mostly AMD and Walmart (7 each), Amazon and Oracle (6 each). The
  company-memory mode (task 4) brings them to 20.

## Task 7: banks, insurers, IFRS

### Plan (written before starting)

- **One small engine change:** an overlay may add lines (`add_lines`), never remove them, so every spread stays
  comparable with the base template. Banks and insurers need lines the commercial template lacks (net interest
  income, provision for credit losses, loans, deposits; premiums earned, losses and loss adjustment expenses, loss
  reserves). Commercial lines a bank never prints (cost of revenue, inventory) simply stay empty: a missing line raises
  nothing, and checks whose inputs are missing are skipped.
- **Three overlays** in `config/profiles/`: `us-bank.yaml`, `us-insurer.yaml`, `ifrs-commercial.yaml` (IFRS wording
  for the commercial template: "profit for the year", "finance costs", "trade and other receivables", "share
  premium"...), each with checks of its own where the industry has an identity (net interest income; loans net of the
  allowance).
- **Tests** on hand-built statements, and **a hand check on real filings**: two banks, two insurers, two IFRS
  filers (20-F), downloaded outside the evaluation sets (`eval/coverage/`, filings git-ignored), spread with the
  overlay, and key values compared by me with the printed statements, recorded in `eval/coverage/checks.json`.
  A few documents per overlay is a smoke test, not a measurement, and is reported as such.

### Result: done as a smoke test; partial coverage

| Overlay | Written from | Hand-checked (unseen) | What the check found |
|---|---|---|---|
| `us-bank.yaml` | Fifth Third: every check passes | Huntington, KeyCorp | 19 of 19 checked values right; Huntington's net income missing ("Income after income taxes"); KeyCorp's cash-flow checks fail |
| `us-insurer.yaml` | Travelers: key lines placed, insurer check passes | Allstate, Progressive | Allstate: the 5 values found are right, but 5 key lines are missing (its own wording); Progressive: no consolidated statements in the 10-K (see below) |
| `ifrs-commercial.yaml` | Unilever: the income statement is now found (it was not) | BP, Novartis | BP: 7 of 7 checked values right, revenue missing; Novartis: right tables, almost nothing placed |

- **Engine changes:** overlays can add lines (never redefine or delete one); a parent-company-only statement is a
  blocker (IMPROVEMENT_LOG #23). Progressive's 10-K holds its consolidated statements in an exhibit, so the only
  balance sheet in the document was the parent company's, spread as if consolidated, unflagged: a general flaw, now a
  blocker. Dev and the synthetic corpus are unchanged by both.
- **What this shows and does not show:** wording written from one company covers that company and some of its peers.
  Banks generalised well; insurers did not (each insurer words its main lines its own way). This is the case for
  measuring these overlays like the commercial template: the SEC tags exist for banks and insurers too, so answer keys
  can be built for a few dozen of each.
- **Not done:** OCR (out of scope); currencies. Euro and "$ million" unit statements are not recognised, so
  Unilever's and BP's values carry an assumed unit and a blocker. That is safe, but it is review work on every IFRS
  filer. It is the next ingestion step after OCR.

## Task 8: README (done)

- New top: who uses it, which manual work it replaces, and what stays human, per engine. Then a Mermaid architecture
  diagram: the engines, the shared controls, the data flow, and the human decision points (it parses with Mermaid
  11.4; a deliberately broken copy is rejected, so the check works).
- The statement results table is replaced with tonight's measurements, each row naming its report: dev and holdout
  (`stmt-*-confirmed`, holdout on all 30 filings), printed PDFs (`eval/sec/pdf/eval-overnight.json`) and the synthetic
  corpus (`syn-overnight`). Added the company-memory table, the second-reader figures labelled as not independent,
  and a pointer to the overlay smoke test. The honest limits are kept.
- The step-by-step description of the statement engine moved to ARCHITECTURE.md, which also gained a section on
  tonight's shared controls. The other engines' tables, the harder-tests section, "Run it", "Adapting" and "Limits"
  are kept verbatim.
- One overclaim caught in my own draft: "nothing becomes eligible without a person" is false. Touchless invoices
  reach "eligible for approval" alone, and calibrated rules settle matches alone. Corrected.

## Assumptions made without anyone to ask

1. The work order's "flaky test" diagnosis was right, but it was not what failed CI; I fixed both and treated the
   ROI one as the CI failure to explain.
2. **The calibration bar is the lower bound of a 95% range, not the point estimate.** The work order says
   "calibrated against measured outcomes"; I took the cautious reading. It costs about three review items per filing.
3. **The reconciliation bar is 0.98 precision.** I chose it after seeing that every current rule clears it (DECISIONS
   D35 says so). Its job is to stop a newly configured rule from auto-accepting before it is measured.
4. **Reconciliation was calibrated on 30 new generated sets** (seeds 2001-2010), not on dev or holdout, so the
   evaluation sets stay untouched.
5. **The stand-in approval for company memory** takes the key's value wherever the key has one and keeps the
   engine's value elsewhere, as an analyst correcting before approval would. A line whose value was corrected confirms
   no mapping behind it.
6. **Fixing a crash found on a holdout filing is not tuning.** I fixed it with a hand-built test and did not re-run
   the holdout. The Home Depot silent misdating found by the second reader is a holdout finding and is *not* fixed:
   it needs reproducing on a dev filing first.
7. **"A few hand-checked documents" means 2 unseen filings per overlay**, plus the one the wording came from. That
   is reported as a smoke test, not a rate.
8. **Pushing the branch counts as authorised by the work order.** Nothing was merged, deployed or published; `main`
   is unchanged.
9. **Sharing names with SEC filings.** Company names and tickers of public SEC filers appear in reports and logs, as
   they already did. No client names are involved (checked against the list in the site's `build_site.py`).

## Surprises and things I think are wrong

1. The ROI page has been quoting intermediate regression reports on this machine (same figures as the final ones,
   by luck, not by design). Fixed (task 1).
2. **The hand-set mapping confidences were mostly optimistic.** A catch-all set to 0.82 was right 0 of 3 times and
   was settling values alone. A section rule set to 0.97 measures 94.2%.
3. **Last year's approved spread is worth more than any rule tonight.** It took silent errors on the holdout from
   47 to 10, and much of that gain comes from mappings that carry forward.
4. **The XBRL tags were right in 29 of 30 sampled disagreements**, but the default engine had already flagged every
   one of them. The tags rarely tell the reviewer something new.
5. **Real engine weaknesses the night exposed, not fixed:**
   - columns dated a year off in 52/53-week and "Fiscal 2023" years (Home Depot unflagged; Snap-on, Target and Disney
     flagged);
   - unit statements printed once for the whole document (Deere), or in other currencies;
   - a fair-value table read as a statement (Merck);
   - wording that differs between insurers.
6. **The ROI page's statement figure** now comes from the newest `latest-*` report by the time it records. After
   tonight that is the policy-era holdout run (49 of 2,108).

## Decisions left for a person

1. **Whether to merge** `overnight-2026-10-25` into `main` (13 commits; CI green on the head of every push, see the end).
2. **The automation bars**: 0.80 / 0.90 on the lower bound for statements, 0.98 for reconciliation. A credit or audit
   function may want its own, and they trade review time for safety.
3. **Whether company memory should be on by default** for companies with an approved prior year. It is the biggest
   safety gain of the night, but it changes what an approval means: approving now also teaches the next year's run.
4. **Whether to build answer keys for banks and insurers** (the SEC tags exist) to turn the overlay smoke test into a
   measurement.

## Next steps (ranked by expected value per hour)

1. **Turn company memory on by default for returning companies**, and add a company-id field to the upload screen
   (today it is API-only). Then measure it on reviewer-approved spreads, not key-approved ones.
2. **Fix period dating for 52/53-week and "Fiscal YYYY" years** (Home Depot, Target, Snap-on, Disney), after
   reproducing it on a dev filing or a synthetic case. Re-measure dev and the synthetic corpus, then the holdout once.
3. **Unit statements**: document-level units ("All amounts are presented in millions of U.S. dollars") and other
   currencies ("EUR million", "$ million"). Today they are assumed and flagged.
4. **Answer keys for 20-30 banks and insurers** from their tags, so the overlays can be measured like the
   commercial template, and their wording grown from many companies rather than one.
5. **Feed reviewer decisions into calibration** (`scripts/calibrate.py --outcomes`) once there are a few hundred.
6. **OCR for scanned statements**: the next ingestion step (out of scope tonight).
7. Groundwork noticed for the next phase:
   - The finding shape (`policy.Finding`) is what a job queue or a case-management connector would carry.
   - The append-only approval tables are what sign-in and roles would attach identities to.
   - `finops.gate` is the release check a deployment pipeline would run.

## CI on the branch

Every push ran the four jobs (Python 3.11, Python 3.13, Python 3.11 with the oldest allowed lxml 5.2, and web). Each
Python job also runs the manifest check and the release gate, so the synthetic statement corpus and every in-repo set
were re-measured on Linux at each push. Some commits went up together, so 8 runs cover the first 12 commits; the head of
every push passed all four jobs:

| Head commit | Result |
|---|---|
| 414f41f (flaky test, after the ROI fix) | success |
| 63b9bb0 (versioned evaluation and release gate) | success |
| 342cddd (uncertainty policy) | success |
| 2a4d973 (company memory, after the crash fix) | success |
| a42ce9d (XBRL second reader) | success |
| a4d0019 (narrower failed-check flags) | success |
| 7c1009e (bank, insurer, IFRS overlays) | success |
| cd69c53 (README) | success |

The commit that adds this section is checked the same way; its result is in the commit's CI run on GitHub.
