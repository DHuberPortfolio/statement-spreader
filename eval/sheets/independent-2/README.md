# Independent blind test set 2 (spreadsheet risk scanner)

Built without looking at the scanner, its tests, its config, set `independent-1` or any reports.
`build_set.py` writes every workbook with openpyxl and writes `truth.json`. It uses fixed seeds,
fixed document timestamps and fixed zip timestamps, so reruns are byte-identical (checked by hashing
two runs).

```
..\..\..\.venv\Scripts\python.exe build_set.py
```

After building, the script reopens every workbook and checks each label against the file: the anchor
holds what the label says, each loop really is a strongly connected cycle, and no legit range overlaps
a fault cell. Then it runs a simple self-scan (#REF!, missing sheets, unknown or broken names,
external links, text numbers inside SUM ranges, loops, row and column run breaks, SUMs that stop
short, SUMs that contain a subtotal, trailing typed constants). Every hit is either a labelled fault
or inside a labelled legit range (`SHOW_LEGIT_HITS=1` lists the second group). openpyxl writes no
cached values, so no workbook contains error results.

Totals: 17 workbooks (11 single workbooks and 3 version pairs), 39 faults, 206 legit entries,
3 diff pairs with 7 material changes.

| Kind | Count |
|---|---|
| REF_ERROR | 2 |
| MISSING_SHEET | 2 |
| UNKNOWN_NAME | 2 |
| BROKEN_NAME | 2 |
| CIRCULAR_REFERENCE | 2 |
| TEXT_NUMBER_IN_SUM | 3 |
| INCONSISTENT_FORMULA | 6 |
| HARDCODED_OVERRIDE | 6 |
| SUM_OMITS_ROW | 3 |
| DOUBLE_COUNT | 4 |
| EXTERNAL_LINK | 3 |
| HARDCODED_PLUG | 4 |

## Workbooks

| File | What it is | Faults | Legit |
|---|---|---|---|
| cash_13wk.xlsx | 13-week cash forecast, weeks across C:O, total column P, hidden `Lists` sheet, sheet `Cash 13wk` | 4 | 18 |
| revenue_bridge.xlsx | Price/volume product data, a vertical revenue bridge using defined names, `P&L Summary` | 4 | 9 |
| lease_ifrs16.xlsx | IFRS 16 / ASC 842 schedule, 36 months down the rows, named IBR and term, SUMIFS disclosure | 4 | 15 |
| bank_rec_sep.xlsx | Bank reconciliation workpaper, cheque lookups against `GL & Bank Data` | 4 | 11 |
| vat_return_q3.xlsx | VAT working: sales/purchase ledgers, hidden rate table, nine-box return, SUMIFS by rate | 4 | 11 |
| inventory_rollforward.xlsx | Monthly RM and FG roll-forward plus a total block, FY column, stock-count valuation | 4 | 21 |
| board_pack_q.xlsx | Board P&L with Q1, Q2, H1, Q3, Q4, H2, FY interleaved, budget, Var, Var %; KPI sheet | 3 | 17 |
| scenario_model.xlsx | Base / Upside / Downside blocks side by side, CHOOSE selector, `Funding & Fees` | 3 | 17 |
| unit_economics.xlsx | Cohort triangle, retention %, `LTV & CAC` | 3 | 10 |
| bva_variance.xlsx | Budget vs actual (month and YTD side by side), SUMIFS from the TB, INDEX/MATCH budget, department SUMIFS | 3 | 14 |
| annual_forecast_3yr.xlsx | 2 actual years and 3 forecast years (few columns), per-year named growth inputs. **Clean** | 0 | 14 |
| rolling_fcst_v1 / v2 | Pair A: monthly opex forecast | 0 / 1 | 5 / 6 |
| debt_schedule_v1 / v2 | Pair B: term-loan schedule | 0 / 1 | 10 / 10 |
| capex_plan_v1 / v2 | Pair C: capex and depreciation | 0 / 1 | 8 / 10 |

### Faults by workbook
- **cash_13wk**: F8 text "1,250.00" in a summed input row; J12 payroll points at the rent input; K14 typed supplier figure; C26 link to `[Treasury Positions.xlsx]`.
- **revenue_bridge**: Product Data D13 totals stop at row 11 and miss the new product (group G13:I13); Bridge B9 link to `[FX Rates 2026.xlsx]`; B12 `+3200` plug; B16 unknown name `CY_Revenue_Mgmt`.
- **lease_ifrs16**: Schedule D24 interest on the *closing* balance, a loop D24 to F24; H29 typed depreciation; Disclosure B13 `+0.42` plug; B15 refers to sheet `Lease Schedule`, which does not exist.
- **bank_rec_sep**: D15 sums both batch subtotals and their items; C25 text "845.20"; D38 `-37.50` plug; B22 lookup without the IFERROR used on the other rows.
- **vat_return_q3**: Return C6 `SUMIFS('Purchase Ledger'!#REF!,...)`; names `Rates_2024` (#REF!) and `PY_Box1` (missing sheet); Sales Ledger F21 hardcodes 20% on a reduced-rate line.
- **inventory_rollforward**: FG closing C18 omits the returns row (group D18:O18); J15 typed cost of sales; Valuation E23 sums subtotals and items; E25 unknown name `Obsolescence_Rate`.
- **board_pack_q**: total opex C18 includes the People costs subtotal (group D18, F18, G18); I14 FY = H1 + Q4; KPIs I10 `/#REF!`.
- **scenario_model**: Downside Q5 uses the Upside growth driver; Upside K7 typed opex; `Funding & Fees` B9 to B10 fee loop.
- **unit_economics**: Cohorts E9 text count; N17 grand total adds the row-total column to its cells; `LTV & CAC` B12 refers to sheet `CAC Detail`, which does not exist.
- **bva_variance**: C20 cost total omits Training (group D20); F16 var % divides by actual; H22 `+1200` plug.
- **pairs**: rolling v2 Opex F8 pasted value; debt v2 Refinancing B6 link to `[Lender Term Sheet.xlsx]`; capex v2 Depreciation E7 pasted value.

### Legitimate structures (the main point of this set)
Interleaved Q/H/FY columns; quarter formulas that each read a different month block; subtotal rows
between item rows (column neighbours look like a run); ratio rows recomputed in H1/FY columns;
point-in-time half-year KPIs (H1 headcount = Q2); a roll-forward that skips the half-year column;
scenario blocks side by side on different driver columns with blank separator columns; a CHOOSE
selector block; per-year named inputs (every forecast cell differs); actual columns then forecast;
roll-forwards (opening, flows, closing, closing becomes next opening) with FY opening = January
opening; grand totals of subtotals; a total above its items; SUMs across blank and text memo rows;
cohort triangles with blanks; IFERROR lookups; SUMIFS summaries; variance and variance % columns;
a variance sign that flips between revenue and cost sections; memo % rows below a total; unit
constants (/52, /12, *30 vs *365, *4 vs *2, /1000, *10000, /6); ROUND and ROUNDDOWN; year and box
number header rows; documented overrides (blue and comment, comment only, blue only); a last-period
ROUND to clear a residual; residual "balancing" formulas with no typed number; hidden helper sheets;
quoted sheet names with spaces and `&`.

## Version pairs (`diffs` in truth.json)
- **rolling_fcst**: FORMULA_TO_VALUE Opex!F8; FORMULA_CHANGED Summary!B5 (efficiency factor added). Not material: row inserted at 9, column I (Jul-26) added, total SUMs grow, a label reworded, an input updated, new input rows.
- **debt_schedule**: VALUE_TO_FORMULA Debt!G10; SHEET_REMOVED Covenants; SHEET_ADDED Refinancing. Not material: an amortisation input updated, a label reworded, the 2030 rate filled in.
- **capex_plan**: FORMULA_TO_VALUE Depreciation!E7; FORMULA_CHANGED Depreciation!B13 (before B12, disposals deduction added). Not material: row inserted at 8 in three sheets, column G (2030) added, total SUMs grow, a capex input updated, a new input.

## Labelling judgement calls
1. **Lease D24** (interest on the closing balance) is labelled CIRCULAR_REFERENCE with `also_ok: INCONSISTENT_FORMULA`: it is both a loop and a run break.
2. **Funding & Fees B9/B10**: a deliberate-looking fee-on-total loop is still labelled a CIRCULAR_REFERENCE (iteration is not switched on, and nothing documents it).
3. **Copied faults**: whole-row omissions are labelled once with a `group` (Product Data D13 + G13:I13, Roll-forward C18 + D18:O18, BvA C20 + D20, P&L C18 + D18/F18/G18). The H1/H2/FY cells of P&L row 18 are correct formulas (C+D etc.) that only inherit the error, so they are not in the group and stay inside the legit H1/H2/FY column ranges.
4. **Product Data**: B13 and E13 (units) are correct and the revenue/effect totals are not. Only the wrong ones are labelled.
5. **Sales Ledger F21** hardcodes the rate inside the formula. That pattern is unscored on its own, but the cell also breaks the lookup run and gives the wrong VAT on an R line, so it is labelled INCONSISTENT_FORMULA.
6. **Bank rec B22** (VLOOKUP without IFERROR) is labelled INCONSISTENT_FORMULA even though it returns the same payee today. The logic differs from both neighbours.
7. **Bank rec D15** is DOUBLE_COUNT, not SUM_OMITS_ROW: the range includes two batch subtotals and their items.
8. **Cohorts N17** is DOUBLE_COUNT (row totals plus the cells they total). It is anchored at the grand-total cell.
9. **Plugs vs ROUND**: `+3200`, `+0.42`, `-37.50` and `+1200` are plugs. ROUND/ROUNDDOWN checks, `-1` in growth or CAGR formulas, and the residual mix formula (no typed number) are legit.
10. **Documented overrides**: Cash L12 (blue + comment), Sales Forecast H6 (blue + comment), Scenarios P7 (comment only, black font), Forecast E11 (blue only, no comment) and Debt v1 G10 (blue + comment, end of run) are legit. Undocumented black typed numbers inside runs (K14, H29, J15, K7, rolling v2 F8, capex v2 E7) are faults.
11. **Pasted values in the v2 files** are labelled twice, on purpose: as a FORMULA_TO_VALUE diff change, and as a HARDCODED_OVERRIDE fault in the v2 workbook.
12. **FORMULA_CHANGED** is anchored only where logic changed (a factor or deduction added). The row and column shifts that rewrite references (Opex!C12 to C13, C10 to C11) are listed as not material.
13. **Annual forecast rows 15 and 17** (interest, tax) sit between two subtotal rows whose formulas match in relative terms (EBIT/PBT, PBT/net income). A column-wise run check would call them overrides (actual years) or inconsistent (forecast years). They are labelled legit.
14. **Board pack quarter totals** (rows 7 and 15 in quarter columns) are subtotal rows between item rows. They are labelled legit for the same reason.
15. **Broken names** are anchored as `name:<Name>` with `sheet: null`. Neither broken name is used by a formula, so there is no second, formula-level fault.
16. **Hidden sheets** (`Lists`, `RateCodes`) hold labels or lookup tables only and are listed as legit. They are not faults.
17. **Legit entries are broad on purpose** (inputs, totals, roll-forwards), so the count (206) is much higher than the 40 required. The entries that matter most are the run-break traps listed in items 13 and 14, the interleaved columns, the scenario blocks, the named-input row and the documented overrides.
