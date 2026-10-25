# Data-quality gate evaluation: dq-dev-second

Synthetic vendor-master and purchase-order exports with injected faults and legitimate oddities, each row labelled with the decision it should get (finops.dq.synthetic). Two source systems with different schemas feed one canonical vendor record; purchase orders are checked against the accepted vendors.

## dev (seed 21)

Vendors: 149 rows ({'accepted': 92, 'review': 25, 'rejected': 30, 'duplicate': 2}); purchase-order lines: 138 ({'accepted': 108, 'review': 8, 'rejected': 20, 'duplicate': 2}). Shuffled rerun: 0 record(s) changed decision.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (57 of 57; likely 93.7-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 57; likely 0.0-6.3%) |
| Right reason, of faults caught | 100.0% (57 of 57; likely 93.7-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (57 of 57; likely 93.7-100.0%) |
| **False quarantines** (valid records held) | 0.0% (0 of 92; likely 0.0-4.0%) |
| Legitimate oddities held | 0.0% (0 of 22; likely 0.0-14.9%) |
| Quarantine precision (held records that needed it) | 100.0% (55 of 55; likely 93.5-100.0%) |

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 96.7% (29 of 30; likely 83.3-99.4%) |
| **Faults missed** (bad records that would have loaded) | 3.3% (1 of 30; likely 0.6-16.7%) |
| Right reason, of faults caught | 100.0% (29 of 29; likely 88.3-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 96.7% (29 of 30; likely 83.3-99.4%) |
| **False quarantines** (valid records held) | 0.9% (1 of 108; likely 0.2-5.1%) |
| Legitimate oddities held | 16.7% (1 of 6; likely 3.0-56.4%) |
| Quarantine precision (held records that needed it) | 96.4% (27 of 28; likely 82.3-99.4%) |

Cases not decided as expected: exact_duplicate_first (1 of 2), exact_duplicate_repeat (1 of 2)

## holdout (seed 22)

Vendors: 149 rows ({'accepted': 92, 'review': 25, 'rejected': 30, 'duplicate': 2}); purchase-order lines: 139 ({'accepted': 109, 'review': 8, 'rejected': 20, 'duplicate': 2}). Shuffled rerun: 0 record(s) changed decision.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (57 of 57; likely 93.7-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 57; likely 0.0-6.3%) |
| Right reason, of faults caught | 100.0% (57 of 57; likely 93.7-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (57 of 57; likely 93.7-100.0%) |
| **False quarantines** (valid records held) | 0.0% (0 of 92; likely 0.0-4.0%) |
| Legitimate oddities held | 0.0% (0 of 22; likely 0.0-14.9%) |
| Quarantine precision (held records that needed it) | 100.0% (55 of 55; likely 93.5-100.0%) |

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 96.7% (29 of 30; likely 83.3-99.4%) |
| **Faults missed** (bad records that would have loaded) | 3.3% (1 of 30; likely 0.6-16.7%) |
| Right reason, of faults caught | 100.0% (29 of 29; likely 88.3-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 96.7% (29 of 30; likely 83.3-99.4%) |
| **False quarantines** (valid records held) | 0.9% (1 of 109; likely 0.2-5.0%) |
| Legitimate oddities held | 16.7% (1 of 6; likely 3.0-56.4%) |
| Quarantine precision (held records that needed it) | 96.4% (27 of 28; likely 82.3-99.4%) |

Cases not decided as expected: exact_duplicate_first (1 of 2), exact_duplicate_repeat (1 of 2)

## Hostile files

0 crash(es) in 12 files.

- empty file: refused: a.csv is empty
- header only: gated
- missing a mapped column: refused: a.csv (Procurement portal export) has no column 'Supplier Name'; its columns are 'Supplier
- duplicate header: refused: a.csv: column 'EIN' appears twice in the header
- binary garbage: refused: a.csv is not a text file (it contains binary data)
- not a workbook: refused: a.xlsx is not a readable Excel workbook (BadZipFile)
- windows-1252 text: gated
- byte-order mark: gated
- ragged rows: gated
- huge cell: refused: a.csv is not a readable CSV (field larger than field limit (131072))
- unsupported type: refused: a.pdf: only .csv and .xlsx files are read
- quotes and newlines: gated

