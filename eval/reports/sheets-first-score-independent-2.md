# Spreadsheet risk scanner: sheets-first-score-independent-2

Claims are anchor cells reported as error or risk; anomalies are listed but not counted. Every workbook was hashed before and after scanning and none changed.

## independent-2

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 84.0% (42 of 50; likely 71.5-91.7%) |
| Recall (planted problems found) | 100.0% (39 of 39; likely 91.0-100.0%) |
| Kind agreement (found problems named right) | 100.0% (39 of 39; likely 91.0-100.0%) |
| Version changes: precision | 100.0% (7 of 7; likely 64.6-100.0%) |
| Version changes: recall | 100.0% (7 of 7; likely 64.6-100.0%) |

Workbooks 17, planted problems 39, claims 50, anomalies 31, legitimate exceptions listed 206 (flagged: 8). Naive checker on the same files: 818 claims. Scan time 0.28 s.

- false alarm in board_pack_q.xlsx: kpis!E6 INCONSISTENT_FORMULA
- false alarm in board_pack_q.xlsx: kpis!E9 INCONSISTENT_FORMULA
- false alarm in board_pack_q.xlsx: kpis!F9 INCONSISTENT_FORMULA
- false alarm in unit_economics.xlsx: cohorts!B17 SUM_OMITS_ROW
- false alarm in annual_forecast_3yr.xlsx: forecast!B15 HARDCODED_OVERRIDE
- false alarm in annual_forecast_3yr.xlsx: forecast!B17 HARDCODED_OVERRIDE
- false alarm in annual_forecast_3yr.xlsx: forecast!C15 HARDCODED_OVERRIDE
- false alarm in annual_forecast_3yr.xlsx: forecast!C17 HARDCODED_OVERRIDE

## Hostile files

| File | Expected | Result | Message |
|---|---|---|---|
| empty.xlsx | refused | refused | empty.xlsx is not an Excel workbook (.xlsx or .xlsm) |
| old-format.xls | refused | refused | old-format.xls is an old-format (.xls) or password-protected workbook. Save it as .xlsx without a password and scan that copy. |
| not-a-workbook.xlsx | refused | refused | not-a-workbook.xlsx is damaged: it is not a readable .xlsx package |
| a-text-file.xlsx | refused | refused | a-text-file.xlsx is not an Excel workbook (.xlsx or .xlsm) |
| zip-not-excel.xlsx | refused | refused | zip-not-excel.xlsx is a zip file but not an Excel workbook |
| binary.xlsb | refused | refused | binary.xlsb is a binary workbook (.xlsb). Save it as .xlsx and scan that copy. |
| entities.xlsx | refused | refused | entities.xlsx contains XML with a DOCTYPE or entity declaration (xl/worksheets/sheet1.xml); Excel never writes these, so the file was refused |
| expands-to-450MB.xlsx | refused | refused | expands-to-450MB.xlsx expands to 450 MB, over the 400 MB limit |
| truncated.xlsx | refused | refused | truncated.xlsx is damaged: it is not a readable .xlsx package |
| formula-only.xlsx | scanned | scanned | 0 finding(s) |
| odd-formulas.xlsx | scanned | scanned | 4 finding(s) |
| empty-workbook.xlsx | scanned | scanned | 0 finding(s) |

Same findings on a second scan of the same bytes: True.
