# Independent spreadsheet test set 1

A blind test set for the spreadsheet risk scanner. It was built without looking at the scanner's code,
tests or config. `build_set.py` writes every workbook with openpyxl and writes `truth.json`, then reopens
each file and checks every label against what was saved.

Rebuild it from this folder with:

    ..\..\..\.venv\Scripts\python.exe build_set.py

The random seeds are fixed, and the script rewrites each zip with fixed timestamps, so two runs give
byte-identical files (checked with file hashes).

## Workbooks

| File | What it is | Faults | Legit |
|---|---|---|---|
| budget_fy25.xlsx | Marketing budget. Months run across B:M, the FY total is in N and the total row is below the items. Jan values are typed and Feb-Dec grow by `$B$2`. Hidden Lists sheet. | 4 | 6 |
| loan_amortisation.xlsx | Loan schedule with periods running down rows 7-66 from column B, defined names, and totals in row 4 above the table. | 4 | 7 |
| three_statement_model.xlsx | Assumptions, P&L, Balance Sheet and Cash Flow sheets that reference each other. FY23-24 actuals are typed and FY25-27 are formulas. Hidden Calc sheet. Two broken defined names. | 7 | 18 |
| sales_commission.xlsx | Rate card plus the 'Commission Q3' sheet: 15 reps, an IFERROR lookup and a circular bonus pool. | 6 | 8 |
| headcount_payroll.xlsx | Assumptions (defined names), a roster and a monthly payroll plan by department. Hidden Lookups sheet. | 5 | 9 |
| consolidation_fy25.xlsx | Three entity sheets (their names contain spaces), plus Eliminations, FX (defined name) and Consolidation sheets. Hidden Mapping sheet. | 5 | 13 |
| capex_depreciation.xlsx | Asset register with category subtotals and a grand total, a depreciation forecast by year, and Disposals and Summary sheets. | 5 | 7 |
| accruals_rec.xlsx | Month-end accruals workpaper (recurring accruals plus cut-off invoices) and a GL reconciliation. | 5 | 11 |
| regional_sales_summary.xlsx | **Clean (no faults).** The total row sits above the items, label rows and a text "n/a" row fall inside the SUM, and it has *100 mix and IFERROR growth columns. | 0 | 9 |
| opex_forecast_v1 / v2 | Version pair 1. The 'Op Ex' sheet has a space in its name. | 0 / 0 | 3 / 4 |
| pricing_model_v1 / v2 | Version pair 2 (one sheet removed, one added) | 1 / 0 | 5 / 6 |
| ar_aging_v1 / v2 | Version pair 3 | 0 / 1 | 4 / 4 |

Totals: **43 faults** and **114 legitimate exceptions** across 15 workbooks, plus **3 version pairs with
8 material changes**.

Faults by kind: INCONSISTENT_FORMULA 9, HARDCODED_OVERRIDE 7, SUM_OMITS_ROW 4, TEXT_NUMBER_IN_SUM 4,
HARDCODED_PLUG 4, EXTERNAL_LINK 3, REF_ERROR 2, MISSING_SHEET 2, UNKNOWN_NAME 2, BROKEN_NAME 2,
CIRCULAR_REFERENCE 2, DOUBLE_COUNT 2.

## truth.json additions

These fields go beyond the agreed format:

- `also_ok`: on a few faults, a second kind that is also a fair finding for the same anchor. For example,
  a total that stops a row short is SUM_OMITS_ROW, but it also breaks the run of totals beside it, so
  INCONSISTENT_FORMULA is fair too. Score the main `kind`, and decide in advance whether a finding of an
  `also_ok` kind counts as a hit.
- `before_cell`: on diff changes, the address in the BEFORE workbook (it differs after inserted rows).
- `cycle` entries are written as `Sheet name!A1` without quotes, even when the sheet name has spaces.
  Each cycle lists exactly the cells of one strongly connected component, in dependency order.

## Labelling judgement calls

- **Hidden sheets** (Lists, Calc, Lookups, Mapping) hold only clean helper data and are not labelled.
  Flagging that a sheet is hidden is not scored.
- **Documented overrides**: Budget!K12, 'Commission Q3'!G11, 'Asset Register'!J9 and opex_v2 'Op Ex'!H13
  are typed numbers inside formula runs, but each has a cell comment and the blue input font, so they are
  labelled legit. Undocumented typed numbers inside runs are HARDCODED_OVERRIDE faults.
- **Constant offsets that are not plugs**: `=B7+1` (period counter), `=ROUND(G6,0)-0.01` (prices ending
  in .99) and `=G8/FY2024!G8-1` (growth) are labelled legit. Only `=SUM(...)+2500`-style forcing numbers
  are plugs.
- **P&L E15:G15** (tax) is labelled legit. The rows above and below it (PBT `=x12+x13`, net income
  `=x14+x15`) happen to share the same relative pattern, so a column-run check could see the tax row as an
  odd one out. It is not.
- **Payroll Plan C16:L16** `=SUM(C11:C15)` is legit. The range holds the salaries subtotal, tax, benefits,
  a blank row and contractors, and it does *not* hold the department rows, so nothing is counted twice.
  M16 `=SUM(M7:M15)` is the DOUBLE_COUNT, because it also takes in M7:M10.
- **DOUBLE_COUNT 'Asset Register'!E24** `=SUM(E8:E22)` takes in both category subtotals (E14 and E22).
- **TEXT_NUMBER_IN_SUM cells** that a formula also uses for arithmetic (Commission E9, Asset Register
  E18) are still labelled only as TEXT_NUMBER_IN_SUM.
- **REF_ERROR P&L!F11** also breaks its row run (`also_ok` INCONSISTENT_FORMULA).
- **External links** are written as plain formula text (`'[Book.xlsx]Sheet'!A1`), in the format the brief
  gave. openpyxl does not create the externalLink parts that Excel itself would write, so Excel may offer
  to repair these files. A scanner reading formulas with openpyxl sees them as written.
- **Text "n/a"** inside a SUM range (regional summary row 18) is legit: it is not a number stored as text.
- **Diff pairs**: opex_v2 H13 is a FORMULA_TO_VALUE change, but in a single-file scan it is a documented
  override and so legit. ar_aging_v2 E19 is a FORMULA_TO_VALUE change and also an undocumented
  HARDCODED_OVERRIDE fault in v2. pricing_v1 G10 is a HARDCODED_OVERRIDE fault that v2 fixes
  (VALUE_TO_FORMULA).

## What the build script checks

After writing the files, `build_set.py` reopens each one and asserts the following:

- Each fault anchor holds what its kind says: a formula or a typed number, `#REF!`, a missing sheet, an
  unknown name, an external link, a typed +/- constant, a SUM, or numeric text inside a SUM range.
- Each INCONSISTENT_FORMULA or HARDCODED_OVERRIDE anchor sits between two neighbours with the same formula
  pattern, and it breaks that pattern.
- Each cycle is exactly one strongly connected component of the dependency graph.

It also scans every visible cell and fails if it finds anything unlabelled:

- a run break,
- numeric text,
- an error-type formula (`#REF!`, missing sheet, unknown name, external link),
- a broken defined name,
- a dependency cycle.

The first build run found 5 labelling mistakes this way, and all were fixed before the final build.
