# Spreadsheet risk scanner: sheets-first-score-independent-1

Claims are anchor cells reported as error or risk; anomalies are listed but not counted. Every workbook was hashed before and after scanning and none changed.

## independent-1

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 91.3% (42 of 46; likely 79.7-96.6%) |
| Recall (planted problems found) | 97.7% (42 of 43; likely 87.9-99.6%) |
| Kind agreement (found problems named right) | 95.2% (40 of 42; likely 84.2-98.7%) |
| Version changes: precision | 100.0% (8 of 8; likely 67.6-100.0%) |
| Version changes: recall | 100.0% (8 of 8; likely 67.6-100.0%) |

Workbooks 15, planted problems 43, claims 46, anomalies 5, legitimate exceptions listed 114 (flagged: 3). Naive checker on the same files: 685 claims. Scan time 0.22 s.

- missed in three_statement_model.xlsx: INCONSISTENT_FORMULA at P&L!F10 (FY2026 opex uses the FY2025 assumption (column E) instead of column F)
- false alarm in headcount_payroll.xlsx: payroll plan!C16 SUM_OMITS_ROW
- false alarm in headcount_payroll.xlsx: payroll plan!N16 SUM_OMITS_ROW
- false alarm in pricing_model_v1.xlsx: price build!H6 HARDCODED_PLUG
- false alarm in pricing_model_v2.xlsx: price build!H6 HARDCODED_PLUG

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
