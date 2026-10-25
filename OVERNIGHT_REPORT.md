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
