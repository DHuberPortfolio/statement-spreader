# Spreadsheet risk scanner: sheets-final

Claims are anchor cells reported as error or risk; anomalies are listed but not counted. Every workbook was hashed before and after scanning and none changed.

## synthetic-31

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 100.0% (22 of 22; likely 85.1-100.0%) |
| Recall (planted problems found) | 100.0% (22 of 22; likely 85.1-100.0%) |
| Kind agreement (found problems named right) | 100.0% (22 of 22; likely 85.1-100.0%) |
| Version changes: precision | 100.0% (8 of 8; likely 67.6-100.0%) |
| Version changes: recall | 100.0% (8 of 8; likely 67.6-100.0%) |

Workbooks 6, planted problems 22, claims 22, anomalies 5, legitimate exceptions listed 39 (flagged: 0). Naive checker on the same files: 464 claims. Scan time 0.12 s.


## synthetic-32

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 100.0% (23 of 23; likely 85.7-100.0%) |
| Recall (planted problems found) | 100.0% (23 of 23; likely 85.7-100.0%) |
| Kind agreement (found problems named right) | 100.0% (23 of 23; likely 85.7-100.0%) |
| Version changes: precision | 100.0% (8 of 8; likely 67.6-100.0%) |
| Version changes: recall | 100.0% (8 of 8; likely 67.6-100.0%) |

Workbooks 6, planted problems 23, claims 23, anomalies 5, legitimate exceptions listed 38 (flagged: 0). Naive checker on the same files: 387 claims. Scan time 0.1 s.


## independent-1

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 100.0% (43 of 43; likely 91.8-100.0%) |
| Recall (planted problems found) | 100.0% (43 of 43; likely 91.8-100.0%) |
| Kind agreement (found problems named right) | 100.0% (43 of 43; likely 91.8-100.0%) |
| Version changes: precision | 100.0% (8 of 8; likely 67.6-100.0%) |
| Version changes: recall | 100.0% (8 of 8; likely 67.6-100.0%) |

Workbooks 15, planted problems 43, claims 43, anomalies 6, legitimate exceptions listed 114 (flagged: 0). Naive checker on the same files: 685 claims. Scan time 0.21 s.


## independent-2

| Measure | Result |
|---|---|
| Precision (claims that are planted problems) | 100.0% (42 of 42; likely 91.6-100.0%) |
| Recall (planted problems found) | 100.0% (39 of 39; likely 91.0-100.0%) |
| Kind agreement (found problems named right) | 100.0% (39 of 39; likely 91.0-100.0%) |
| Version changes: precision | 100.0% (7 of 7; likely 64.6-100.0%) |
| Version changes: recall | 100.0% (7 of 7; likely 64.6-100.0%) |

Workbooks 17, planted problems 39, claims 42, anomalies 34, legitimate exceptions listed 206 (flagged: 0). Naive checker on the same files: 818 claims. Scan time 0.29 s.


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
