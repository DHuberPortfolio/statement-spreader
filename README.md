# Finance Operations Platform (statement-spreader)

A local, $0 portfolio build of three finance engines on one shared core:

1. **Financial statement spreading**: statements (HTML, PDF, Excel) in, a standard spread out, every number traced
   to the printed cell, checked by accounting identities. (The original engine; details below.)
2. **Reconciliation and exception management**: two sources (a bank statement and the cash ledger) matched by
   layered, deterministic rules; everything uncertain proposed to a person; every leftover given a reason; every
   decision recorded and replayed safely on reruns.
3. **Invoice intake and three-way matching**: invoices (PDF with a text layer, or JSON) read with field-level
   evidence, checked arithmetically, matched to purchase orders and goods receipts, screened for duplicates,
   vendor impersonation and changed bank details. The best status an invoice can reach is *eligible for
   approval*; nothing here approves or pays.

And in front of them, a **data-quality gate** (2026-10-24, night): records moving from one system into another
(vendor master, purchase orders) are mapped from each source's own columns into one record, checked, and either
accepted, held for a person, or rejected with a reason, before anything loads them. Its accepted export is the
invoice engine's master data. See [Data-quality gate](#data-quality-gate-2026-10-24-night) below.

And beside them, a **spreadsheet risk scanner** (2026-10-24, night): a workbook (and optionally its earlier
version) in, definite errors, likely risks and low-confidence anomalies out, each with the sheet, cell, formula,
what its neighbours imply and what depends on it. It never changes or calculates the workbook. See
[Spreadsheet risk scanner](#spreadsheet-risk-scanner-2026-10-24-night) below.

They share money handling, configuration overlays, the exception queue, an append-only audit log, the evaluation
format and the ROI conventions ([ARCHITECTURE.md](ARCHITECTURE.md)). Deterministic code does arithmetic, matching
and policy; a local language model is used only where language is the problem (placing unusual statement rows,
drafting wording for an unknown invoice layout), always behind a closed list and a person's review.

It measures itself: every rate below comes from a command in [TESTING.md](TESTING.md), against answer keys the
code under test never writes, with a 95% range. **This is a tested portfolio prototype, not a production system**:
it has no sign-in, runs on one machine, and has only been measured on public filings and synthetic data.

## Reconciliation results (synthetic, 2026-10-24)

Generated bank-vs-ledger sets (about 690 records each) with planted problems: missing entries, duplicates, fees
deducted, keying errors, partial payments, reversals, timing differences, batch deposits, split settlements,
ambiguous twins, coincidental sums and currency mismatches. The **stress** set draws 40% of amounts from a short list
of round numbers, the way rent, retainers and subscriptions repeat in real books. `greedy` is the naive baseline
(best pair first), kept for comparison; `component` is the default.

| Set | Strategy | Records | **False automatic matches** | Pairings that need a person, auto-accepted | True automatic pairings settled | Pairings that need a person, proposed | Planted problems raised | Same result, rows shuffled |
|---|---|---|---|---|---|---|---|---|
| dev | greedy | 690 | 0.0% (0 of 231; 0.0-1.6%) | 31.6% (18 of 57; 21.0-44.5%) | 100.0% (213 of 213; 98.2-100.0%) | 68.4% (39 of 57; 55.5-79.0%) | 91.2% (93 of 102; 84.1-95.3%) | yes |
| dev | component | 690 | 0.0% (0 of 213; 0.0-1.8%) | 0.0% (0 of 57; 0.0-6.3%) | 100.0% (213 of 213; 98.2-100.0%) | 100.0% (57 of 57; 93.7-100.0%) | 100.0% (102 of 102; 96.4-100.0%) | yes |
| holdout | greedy | 688 | 0.0% (0 of 231; 0.0-1.6%) | 31.6% (18 of 57; 21.0-44.5%) | 100.0% (213 of 213; 98.2-100.0%) | 68.4% (39 of 57; 55.5-79.0%) | 91.2% (93 of 102; 84.1-95.3%) | yes |
| holdout | component | 688 | 0.0% (0 of 213; 0.0-1.8%) | 0.0% (0 of 57; 0.0-6.3%) | 100.0% (213 of 213; 98.2-100.0%) | 100.0% (57 of 57; 93.7-100.0%) | 100.0% (102 of 102; 96.4-100.0%) | yes |
| stress | greedy | 685 | 1.3% (3 of 233; 0.4-3.7%) | 31.6% (18 of 57; 21.0-44.5%) | 99.5% (212 of 213; 97.4-99.9%) | 57.9% (33 of 57; 45.0-69.8%) | 85.3% (87 of 102; 77.1-90.9%) | yes |
| stress | component | 685 | 0.0% (0 of 212; 0.0-1.8%) | 0.0% (0 of 57; 0.0-6.3%) | 99.5% (212 of 213; 97.4-99.9%) | 89.5% (51 of 57; 78.9-95.1%) | 93.1% (95 of 102; 86.5-96.6%) | yes |

Scale: 6,898 records in 2.81 s, completeness checks failed: 0. Source: `eval/reports/recon-final.json`.

The headline is the false-match rate: a wrong automatic match hides a real discrepancy. On the stress set the
greedy baseline makes them; the default does not, at the cost of sending more pairings to a person.

## Invoice results (synthetic, 2026-10-24)

81 invoices per set, about half with a planted problem (arithmetic, price over PO, quantity over receipt, missing
receipt, closed or unknown PO, wrong vendor, tax, exact and re-typed duplicates, changed or unverifiable bank
details). **dev** and **holdout** use the three layouts the extractor was built on. **unseen** (layout D) and
**unseen-e** (layout E) use wording the extractor never saw: with the default policy they fail closed (nothing
problematic goes through untouched); a wording overlay, configuration only, restores them. `model-draft` rows use
an overlay drafted by a local model and not reviewed; `reviewed-draft` is that draft after a person moved one line.
Layout E was created after the drafting method was frozen, so it is the clean test of the model step.

| Set | Invoices | **False touchless** | Touchless | Header fields right | Line items read exactly | Right PO matched | Planted problems raised | Duplicates caught |
|---|---|---|---|---|---|---|---|---|
| dev | 81 | 0.0% (0 of 37; 0.0-9.4%) | 54.3% (44 of 81; 43.5-64.7%) | 100.0% (729 of 729; 99.5-100.0%) | 100.0% (242 of 242; 98.4-100.0%) | 100.0% (77 of 77; 95.2-100.0%) | 100.0% (37 of 37; 90.6-100.0%) | 100.0% (6 of 6; 61.0-100.0%) |
| holdout | 81 | 0.0% (0 of 37; 0.0-9.4%) | 53.1% (43 of 81; 42.3-63.6%) | 100.0% (729 of 729; 99.5-100.0%) | 100.0% (263 of 263; 98.6-100.0%) | 100.0% (77 of 77; 95.2-100.0%) | 100.0% (37 of 37; 90.6-100.0%) | 100.0% (6 of 6; 61.0-100.0%) |
| unseen | 81 | 0.0% (0 of 37; 0.0-9.4%) | 3.7% (3 of 81; 1.3-10.3%) | 36.1% (263 of 729; 32.7-39.6%) | 1.6% (4 of 253; 0.6-4.0%) | 3.9% (3 of 77; 1.3-10.8%) | 27.0% (10 of 37; 15.4-43.0%) | 16.7% (1 of 6; 3.0-56.4%) |
| unseen+wording | 81 | 0.0% (0 of 37; 0.0-9.4%) | 54.3% (44 of 81; 43.5-64.7%) | 100.0% (729 of 729; 99.5-100.0%) | 100.0% (253 of 253; 98.5-100.0%) | 100.0% (77 of 77; 95.2-100.0%) | 100.0% (37 of 37; 90.6-100.0%) | 100.0% (6 of 6; 61.0-100.0%) |
| unseen+model-draft | 81 | 0.0% (0 of 37; 0.0-9.4%) | 54.3% (44 of 81; 43.5-64.7%) | 100.0% (729 of 729; 99.5-100.0%) | 100.0% (253 of 253; 98.5-100.0%) | 100.0% (77 of 77; 95.2-100.0%) | 100.0% (37 of 37; 90.6-100.0%) | 100.0% (6 of 6; 61.0-100.0%) |
| unseen-e | 81 | 0.0% (0 of 37; 0.0-9.4%) | 3.7% (3 of 81; 1.3-10.3%) | 32.6% (238 of 729; 29.3-36.1%) | 2.1% (5 of 240; 0.9-4.8%) | 3.9% (3 of 77; 1.3-10.8%) | 27.0% (10 of 37; 15.4-43.0%) | 16.7% (1 of 6; 3.0-56.4%) |
| unseen-e+model-draft | 81 | 0.0% (0 of 37; 0.0-9.4%) | 3.7% (3 of 81; 1.3-10.3%) | 78.6% (573 of 729; 75.5-81.4%) | 100.0% (240 of 240; 98.4-100.0%) | 3.9% (3 of 77; 1.3-10.8%) | 51.4% (19 of 37; 35.9-66.6%) | 100.0% (6 of 6; 61.0-100.0%) |
| unseen-e+reviewed-draft | 81 | 0.0% (0 of 37; 0.0-9.4%) | 53.1% (43 of 81; 42.3-63.6%) | 100.0% (729 of 729; 99.5-100.0%) | 100.0% (240 of 240; 98.4-100.0%) | 100.0% (77 of 77; 95.2-100.0%) | 100.0% (37 of 37; 90.6-100.0%) | 100.0% (6 of 6; 61.0-100.0%) |

Source: `eval/reports/invoice-final.json`.

The headline is **false touchless**: a problem invoice that would reach "eligible for approval" with no person
involved. It is 0 on every set. Touchless rates are on sets where about half the invoices carry a planted problem,
so they say nothing about a real inbox.

## Data-quality gate (2026-10-24, night)

The engines above trusted their inputs: the invoice engine loaded its vendor master and purchase orders with no
checks, so a duplicate vendor id silently replaced another and one unreadable cell stopped the whole load. The gate
sits between source systems and the engines (`src/finops/dq`, `config/finops/dq/*.yaml`). It never edits a source,
never merges, never loads anything itself: it writes the accepted records for the next system and a quarantine
report for people. Bank details changed since the last accepted load are held for a second person while the
previous, verified details stay in force.

Measured with `scripts/run_eval.py --engine dq` (report `eval/reports/dq-final.md`). A *fault* is a row that needed
attention (an error to reject, a suspicion to hold, a duplicate to load once); a *false quarantine* is a valid row
held anyway.

| Test set | Faults caught | Faults missed (would have loaded) | Valid rows held |
|---|---|---|---|
| Synthetic vendors, holdout seed (two source schemas, faults and legitimate oddities) | 56 of 56 | 0 | 1 of 93 |
| Synthetic purchase-order lines, holdout seed | 30 of 30 | 0 | 0 of 109 |
| Independent set 2, vendors, **first scoring, nothing changed beforehand** | 60 of 63 | 3 | 0 of 44 |
| Independent set 2, purchase-order lines, first scoring | 34 of 35 | 1 | 1 of 42 |

The independent sets were written by separate agents from the configuration files and a description of the policy,
without the gate's code. Each found a real defect (Excel's scientific notation turned into a different account
number; "NET 45 EOM" read as 45 days), fixed afterwards, so their later scores (set 1: 58 of 58 and 32 of 34; set 2:
61 of 63 and 35 of 35) are no longer held-out figures. The remaining disagreements are labelling choices, listed in
IMPROVEMENT_LOG. The one synthetic valid row held is by design: a company named "@Home Supply" looks like a
spreadsheet formula.

Without the gate, the same synthetic exports loaded the way the invoice engine reads them today: the load fails on
the first unreadable cell, and if it had not, 4 vendor rows would have silently replaced others, 2 PO lines would
name unknown vendors and 11 to 12 bank-detail changes would have loaded unreviewed. End to end (a test): a bank
account changed in a source system lets a matching fraudulent invoice pass the invoice engine's bank check; through
the gate, the invoice is blocked.

Run it on files: `spreader gate --dataset config/finops/dq/vendors.yaml --source portal=portal.csv --source erp=erp.xlsx
--previous last-accepted.csv --out out` (`--strict` exits 1 when anything is held), or open **Data quality** in the
app and press "Try sample data". Synthetic data only: no real company's records have been through it.

## Spreadsheet risk scanner (2026-10-24, night)

Finance runs on workbooks nothing checks. The scanner (`src/finops/sheets`, settings in
`config/finops/sheets/default.yaml`) reads one and reports:
- **Errors** (broken whatever the author meant): `#REF!`, a sheet or name that does not exist, a defined name that
  points nowhere, cells that depend on themselves, a number stored as text inside a sum (the total silently skips
  it), and error values Excel saved (reported at the cell they start from, not every cell they spread to).
- **Risks** (probably wrong, a person should look): a formula unlike the same formula on both sides of it, a typed
  number in the middle of a formula run, a total that stops short of its block, a sum that counts something twice,
  a link to another workbook, a typed amount added to force a result.
- **Anomalies** (listed, not counted as findings): overrides the model documents (input colour or a comment),
  row-specific patterns, typed rates inside formulas, INDIRECT/OFFSET, hidden sheets that visible formulas read.

It does not flag every typed number: a cell is only compared inside a run of formulas that agree on both sides of
it, so input blocks, actual months before forecast months, opening balances and full-year columns are left alone.
Given an earlier version, it lists only the formulas whose meaning changed: rows and columns are aligned first, so
an inserted row is not a change to every formula below it.

Measured with `scripts/run_eval.py --engine sheets` (report `eval/reports/sheets-final.md`). A *claim* is a cell
reported as an error or risk; it is right when a planted problem is there.

| Test set | Claims that were real problems (precision) | Planted problems found (recall) | Version changes found, false |
|---|---|---|---|
| Synthetic, seeds 31 and 32 (same author as the scanner) | 22 of 22; 23 of 23 | 22 of 22; 23 of 23 | 8 of 8, 0; 8 of 8, 0 |
| Independent set 1, **first scoring, nothing changed beforehand** (9 workbooks + 3 version pairs) | 42 of 46 (91.3%) | 42 of 43 (97.7%) | 8 of 8, 0 |
| Independent set 2, **first scoring** (11 workbooks + 3 version pairs, weighted toward legitimate structure) | 42 of 50 (84.0%) | 39 of 39 | 7 of 7, 0 |

The independent sets were written by separate agents from the list of finding kinds and their anchor cells, without
the scanner's code. Their first scorings are the figures to quote. Each then showed a real gap that was fixed with a
regression test: a three-year forecast row was never compared; totals starting at a subtotal were blamed for rows
the subtotal holds; `=ROUND(x,0)-0.01` (a .99 price) was called a plug; half-year columns between quarters, typed
actuals between subtotal rows and a 0-1-2-3 heading were flagged. Both now score 100% (`sheets-final`), which is no
longer a held-out figure.

On the same independent workbooks a naive checker (every typed number next to a formula, every formula unlike its
left neighbour) makes 685 and 818 claims (set 1, set 2), against the scanner's 46 and 50 on first scoring. A 48,121-formula workbook loads and scans in about 4.5 seconds on this
machine. Twelve hostile files (old .xls, encrypted, binary .xlsb, damaged, an XML entity bomb, a zip that expands
to 450 MB) are refused with a message or scanned; none crashes. Every workbook is hashed before and after scanning
and none changed.

What it cannot see: a formula that is consistent everywhere and still wrong; values in a file saved without
calculating (a program-written file; it says so); VBA. It reads .xlsx and .xlsm only. Synthetic and agent-written
workbooks only: no real company's model has been through it.

Run it: `spreader scan model-v2.xlsx --previous model-v1.xlsx` (`--strict` exits 1 on a definite error), or open
**Spreadsheets** in the app and press "Try a sample workbook". A person confirms or dismisses each finding with a
reason; a dismissal carries to the next version of the same model until the formula or its labels change, and a
definite error cannot be dismissed.

## Harder tests and an independent scorer (2026-10-24, late)

- **Reconciliation, 10 random seeds x 3 kinds of set** (`eval/reports/recon-multiseed-v4.md`; *messy* adds truncated and
  abbreviated bank descriptions, dropped and mistyped references and same-day payroll bursts): false automatic matches 0 of
  2,130 (clean), 1 of 2,114 (stress), 2 of 2,317 (messy). All three are the same pattern no rule can see: the same customer,
  the same round amount, days apart, where the truth is two different payments.
- **Invoices, 3 messy PDF sets mixing all five layouts** ("PO#4501", re-typed invoice numbers, 3-decimal prices): 100% of
  header fields and line items read, every planted problem raised, 0 false touchless.
- **workflow-eval-harness** (`wfeval`, written earlier for other workflows) scored exported outputs and keys independently:
  0 silent errors and 0 silent omissions on all five invoice sets it scored and on reconciliation dev, holdout and stress; on two messy
  reconciliation sets it counts exactly the same-customer cases above.
- **Statement engine**: anchoring column dates on the balance sheet and flagging every gap cut silent omissions on the dev
  split from 3.9% to 2.2% and on the never-tuned holdout from 5.3% to 3.9%, without adding silent errors (holdout 68 -> 66).
- **Statement answer keys** (a scorer fix, engine unchanged): the key builder now reads each filing's own calculation
  links, so a total and its part tagged on one line are no longer added together (Walmart's revenue key was about twice
  its revenue). Same engine output, old keys against new: silent errors 70 -> 60 on dev, 66 -> 55 on the holdout, 87 -> 77
  on the printed PDFs. The engine-one table below predates both statement changes; IMPROVEMENT_LOG #15 and #16 have
  the current figures.
- **An outside test run on a fresh Linux install** found that lxml's Linux wheels stop reading at the first `</html>`
  (a second statement in the same file vanished) and that the reader hid Deckers' entire 10-K behind a `font-size:0`
  page wrapper, so the holdout had scored 29 of 30 filings. Both are fixed and measured (IMPROVEMENT_LOG #17-#18:
  holdout with all 30 filings, 74.1% right, 55 silent errors of 2,139), and `.github/workflows/tests.yml` installs
  fresh on Linux and runs the tests on every push.

What these numbers do **not** show: the synthetic data and the engines were written by the same author; real
exports are messier; minutes saved are not measured (the ROI page labels them placeholders).

# Engine one: Statement Spreader

Financial statements in (an SEC 10-K, a PDF, an Excel workbook); a standard **spread** out: every
income-statement, balance-sheet and cash-flow line mapped to one template, per period, with each
number traced to the exact printed cell it came from, checked by accounting identities, and either
auto-accepted or sent to a reviewer with a reason. Built as a reusable foundation for an internal AI
pilot in credit, FP&A or audit: a new organisation adapts it with a configuration overlay, not code.

It measures itself. Every rate below comes from a command in [TESTING.md](TESTING.md), against
answer keys the pipeline never sees, and carries a 95% range.

### What it does

1. **Reads** HTML (including inline-XBRL filings, ignoring the tags and anything hidden), PDFs with
   a text layer (words rebuilt into rows, with page and box for every number) and Excel (cell
   references, hidden rows and sheets skipped, formulas without saved values refused).
2. **Finds the statements**, their periods (from headers, titles, other statements or the cover
   page) and their unit ("in millions, except per share").
3. **Finds totals by footing**: a row is a total when it equals the rows above it in every period.
4. **Maps each row** to the template with a confidence and a reason: reviewer memory, aliases,
   section rules, spelling, structure, and optionally a local language model that only ever picks
   a line id from a closed list and never sees a number.
5. **Assembles** one value per line and period with its provenance trail (read, scale, sum, sign,
   map, calculate, correct), and a status: extracted, normalized, calculated, AI-mapped, human,
   assumed or missing.
6. **Checks**: balance sheet balances, subtotals, cash-flow roll-forward, cross-statement and
   cross-period ties, EPS x shares vs net income, with rounding tolerance from the printed scale.
7. **Sends to review** whatever it doubts: failed checks, assumed units or periods, low-confidence
   mappings, unplaced rows, unreadable or ambiguous numbers, suspicious jumps, covenant breaches.
8. **Lets a reviewer** inspect any value back to its source, correct it with a reason, remap rows
   (remembered for next time), resolve items with notes, and approve: approval is refused while a
   blocking item is open. Everything is an audit event.
9. **Exports** Excel (spread, sources, checks, review, ratios; never live formulas), CSV and JSON.
10. **Measures ROI** from timed work sessions (by hand vs assisted, active time only), labelling
    every number observed, estimated, hypothetical or assumption, and keeping released capacity
    apart from cash saved.

### Measured results (2026-10-24)

SEC set: 63 recent 10-K filings of non-financial companies, split by ticker hash into a **dev** half
(tuned on) and a **holdout** half (measured, never tuned on). Answer keys come from each filing's
inline XBRL tags through an independent crosswalk. Synthetic set: 40 generated private-company
statement packages (30 clean, 10 adversarial) in HTML, Excel and PDF, with exact keys.

| Set | Documents | Values right | Silent error rate | Silent omissions | Wrong values caught | Review items per document (median) |
|---|---|---|---|---|---|---|
| SEC dev, HTML (tuned on) | 33 | 80.0% (3,542 of 4,425; 78.8-81.2%) | 2.8% (70 of 2,542; 2.2-3.5%) | 3.9% (171 of 4,425; 3.3-4.5%) | 68.2% (150 of 220; 61.8-74.0%) | 21 |
| SEC dev, HTML, + local model | 33 | 83.3% (3,608 of 4,333; 82.1-84.3%) | 2.1% (53 of 2,485; 1.6-2.8%) | 3.0% (128 of 4,333; 2.5-3.5%) | 79.5% (205 of 258; 74.1-83.9%) | 25 |
| **SEC holdout, HTML (never tuned on)** | 30 (29 scored) | 73.5% (2,858 of 3,890; 72.1-74.8%) | 3.2% (68 of 2,100; 2.6-4.1%) | 5.3% (208 of 3,890; 4.7-6.1%) | 81.7% (304 of 372; 77.5-85.3%) | 20 |
| SEC holdout, HTML, + local model | 30 (29 scored) | 75.0% (2,870 of 3,827; 73.6-76.3%) | 2.8% (59 of 2,086; 2.2-3.6%) | 3.8% (144 of 3,827; 3.2-4.4%) | 86.9% (392 of 451; 83.5-89.7%) | 24 |
| Synthetic, 40 cases x HTML/Excel/PDF | 120 | 97.0% (14,085 of 14,517; 96.7-97.3%) | 0.0% (6 of 13,452; 0.0-0.1%) | 1.7% (252 of 14,517; 1.5-2.0%) | 0.0% (0 of 6; 0.0-39.0%) | 1 |
| SEC dev printed to PDF | 33 | 80.5% (3,572 of 4,438; 79.3-81.6%) | 3.3% (87 of 2,650; 2.7-4.0%) | 2.6% (115 of 4,438; 2.2-3.1%) | - | - |

Sources: `eval/reports/{dev,holdout}-final[-model].json`, `eval/reports/syn-final.json`, `eval/sec/pdf/eval-sec-pdf-unjudged.json`; regenerate with `scripts/run_eval.py`, `scripts/print_sec_pdfs.py --eval` and `scripts/results_table.py`. For PDFs the scorer finds the answer key's unplaceable rows by label, period and value instead of HTML cell paths, so the PDF row is comparable with the HTML dev rows. "Review items per document" is the reviewer's workload: one failed check flags several values but is resolved once.

**One holdout filing was never scored.** Deckers (DECK) crashed in both holdout runs above ("no tables with numbers
found"), so those rows score 29 of the 30 filings. The reader took the `font-size:0` wrapper around each of its pages
as hidden text, although the text inside sets its own size. Fixed on 2026-10-24 (evening); the holdout measured with
Deckers included is in [IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md) #17.

The **silent error rate** is the share of auto-accepted values that are wrong: of what would go out
without a person looking, how much is wrong. Every improvement and every reverted idea is in
[IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md).

What these numbers do **not** show:
- SEC filings are cleaner than a borrower's scanned PDF; scanned PDFs (no text layer) are refused.
- The synthetic corpus was written by the same team that wrote the pipeline.
- ROI: no time savings have been measured yet. The ROI page reports "not measured" until at least
  three documents are spread by hand and three reviewed in assisted mode by a real analyst.

### Run it

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cd web && npm install && npm run build && cd ..
.venv/Scripts/python scripts/load_demo.py var/demo          # optional: a few documents to look at
SPREADER_DATA=var/demo .venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765
SPREADER_DATA=var/demo .venv/Scripts/spreader serve                  # the same, through the installed command
.venv/Scripts/spreader spread path/to/10-K.htm --out spread.xlsx      # one document, no app (export marked unapproved)
```

Open http://127.0.0.1:8765: **Statements**, **Reconciliation** (/recon: create one, then upload two files or
"Try sample data") and **Invoices** (/invoices: upload a PDF or JSON, or "Load the sample inbox"); the samples are
the synthetic sets in `eval/`. Invoice matching reads its vendor master, POs and receipts from
`FINOPS_MASTER_DIR` (default: the synthetic `eval/invoice/dev/master`) under the policy in `FINOPS_AP_POLICY`
(default `config/finops/invoice/default-ap.yaml`). To use an organisation's statement overlay:
`SPREADER_PROFILE=config/profiles/example-lender-overlay.yaml`. To turn on the local model tier, run
llama.cpp's `llama-server` on 127.0.0.1 and set `SPREADER_MODEL_URL=http://127.0.0.1:8088`.

Needs nothing paid: Python 3.11, Node 18+, and optionally an NVIDIA GPU for the model tier
(measured on an RTX 3060 Ti: about 0.35 s per row, 4.8 GB of GPU memory).

### Adapting it to an organisation

- **Template, aliases, checks, ratios, covenants**: `config/profiles/*.yaml`; an overlay
  (`extends:`) adds an organisation's labels, detection patterns, checks and covenant limits
  without copying the base ([example](config/profiles/example-lender-overlay.yaml)).
- **Sources**: a reader returns the same `DocumentIR` (tables of positioned tokens with source
  references); a new connector (SharePoint folder, email, a loan system's document API) only has to
  deliver bytes to `service.upload`.
- **Outputs**: `export.py` (Excel, CSV, JSON); a push to a downstream system belongs behind the
  approval gate.
- **Reconciliation and invoices**: `config/finops/recon/*.yaml` (column names, sign conventions, tolerances,
  which rules may auto-accept) and `config/finops/invoice/*.yaml` (tolerances, duplicate window, label and column
  wording). Examples: [a bank export with one signed column](config/finops/recon/example-company-signed.yaml),
  [an unseen supplier layout](config/finops/invoice/example-supplier-layout-d.yaml). Full guide in
  [ARCHITECTURE.md](ARCHITECTURE.md).
- **Model provider**: `llm/` is optional and isolated; replacing the local server with an
  organisation's approved model endpoint changes one class.

### Limits and what production would need

Sign-in and roles (the reviewer name is an unverified header), a retention and deletion policy,
encryption at rest, OCR for scanned statements, multi-user concurrency on a server database, and,
in banking, model-risk-management review. See [THREAT_MODEL.md](THREAT_MODEL.md) and
[DECISIONS.md](DECISIONS.md).
