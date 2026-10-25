# Data-quality gate evaluation: dq-dev-third

Synthetic vendor-master and purchase-order exports with injected faults and legitimate oddities, each row labelled with the decision it should get (finops.dq.synthetic). Two source systems with different schemas feed one canonical vendor record; purchase orders are checked against the accepted vendors.

## dev (seed 21)

Vendors: 149 rows ({'accepted': 92, 'review': 25, 'rejected': 30, 'duplicate': 2}); purchase-order lines: 138 ({'accepted': 108, 'review': 8, 'rejected': 20, 'duplicate': 2}). Shuffled rerun: 0 record(s) changed decision.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (56 of 56; likely 93.6-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 56; likely 0.0-6.4%) |
| Right reason, of faults caught | 100.0% (56 of 56; likely 93.6-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (56 of 56; likely 93.6-100.0%) |
| **False quarantines** (valid records held) | 1.1% (1 of 93; likely 0.2-5.8%) |
| Legitimate oddities held | 4.3% (1 of 23; likely 0.8-21.0%) |
| Quarantine precision (held records that needed it) | 98.2% (54 of 55; likely 90.4-99.7%) |

Cases not decided as expected: legit_name_starts_with_at (1 of 1)

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (30 of 30; likely 88.6-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 30; likely 0.0-11.4%) |
| Right reason, of faults caught | 100.0% (30 of 30; likely 88.6-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (30 of 30; likely 88.6-100.0%) |
| **False quarantines** (valid records held) | 0.0% (0 of 108; likely 0.0-3.4%) |
| Legitimate oddities held | 0.0% (0 of 6; likely 0.0-39.0%) |
| Quarantine precision (held records that needed it) | 100.0% (28 of 28; likely 87.9-100.0%) |

## holdout (seed 22)

Vendors: 149 rows ({'accepted': 92, 'review': 25, 'rejected': 30, 'duplicate': 2}); purchase-order lines: 139 ({'accepted': 109, 'review': 8, 'rejected': 20, 'duplicate': 2}). Shuffled rerun: 0 record(s) changed decision.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (56 of 56; likely 93.6-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 56; likely 0.0-6.4%) |
| Right reason, of faults caught | 100.0% (56 of 56; likely 93.6-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (56 of 56; likely 93.6-100.0%) |
| **False quarantines** (valid records held) | 1.1% (1 of 93; likely 0.2-5.8%) |
| Legitimate oddities held | 4.3% (1 of 23; likely 0.8-21.0%) |
| Quarantine precision (held records that needed it) | 98.2% (54 of 55; likely 90.4-99.7%) |

Cases not decided as expected: legit_name_starts_with_at (1 of 1)

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (30 of 30; likely 88.6-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 30; likely 0.0-11.4%) |
| Right reason, of faults caught | 100.0% (30 of 30; likely 88.6-100.0%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (30 of 30; likely 88.6-100.0%) |
| **False quarantines** (valid records held) | 0.0% (0 of 109; likely 0.0-3.4%) |
| Legitimate oddities held | 0.0% (0 of 6; likely 0.0-39.0%) |
| Quarantine precision (held records that needed it) | 100.0% (28 of 28; likely 87.9-100.0%) |

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

