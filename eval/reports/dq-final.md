# Data-quality gate evaluation: dq-final

Synthetic vendor-master and purchase-order exports with injected faults and legitimate oddities, each row labelled with the decision it should get (finops.dq.synthetic). Two source systems with different schemas feed one canonical vendor record; purchase orders are checked against the accepted vendors.

## dev (seed 21)

Vendors: 149 rows ({'accepted': 92, 'review': 25, 'rejected': 30, 'duplicate': 2}); purchase-order lines: 138 ({'accepted': 108, 'review': 8, 'rejected': 20, 'duplicate': 2}). Shuffled rerun: 0 record(s) changed decision.

Without the gate (the same exports renamed into the invoice engine's master format and loaded as they are): the master load failed: ValueError: vendors row 19: tax_rate 'eight' is not a number; 4 vendor row(s) would silently replace another with the same id, 2 PO line(s) name an unknown vendor, 11 bank-detail change(s) would load unreviewed.

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

Without the gate (the same exports renamed into the invoice engine's master format and loaded as they are): the master load failed: ValueError: vendors row 13: tax_rate '8.25%' is not a number; 4 vendor row(s) would silently replace another with the same id, 2 PO line(s) name an unknown vendor, 12 bank-detail change(s) would load unreviewed.

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

## independent-1 (written by someone who did not see the gate's code)

Purchase orders checked against the vendors this gate run accepted. Reason codes are not scored here: the set's labels give decisions only.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (58 of 58; likely 93.8-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 58; likely 0.0-6.2%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (58 of 58; likely 93.8-100.0%) |
| **False quarantines** (valid records held) | 0.0% (0 of 47; likely 0.0-7.6%) |
| Legitimate oddities held | 0.0% (0 of 47; likely 0.0-7.6%) |
| Quarantine precision (held records that needed it) | 100.0% (56 of 56; likely 93.6-100.0%) |

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 94.1% (32 of 34; likely 80.9-98.4%) |
| **Faults missed** (bad records that would have loaded) | 5.9% (2 of 34; likely 1.6-19.1%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 94.1% (32 of 34; likely 80.9-98.4%) |
| **False quarantines** (valid records held) | 0.0% (0 of 51; likely 0.0-7.0%) |
| Legitimate oddities held | 0.0% (0 of 51; likely 0.0-7.0%) |
| Quarantine precision (held records that needed it) | 100.0% (31 of 31; likely 89.0-100.0%) |

Cases not decided as expected: qty_thousands_sep (1 of 1), vendor_held_review (1 of 1)

## independent-2 (written by someone who did not see the gate's code)

Purchase orders checked against the set's vendors_reference.csv. Reason codes are not scored here: the set's labels give decisions only.

**Vendors**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 96.8% (61 of 63; likely 89.1-99.1%) |
| **Faults missed** (bad records that would have loaded) | 3.2% (2 of 63; likely 0.9-10.9%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 96.8% (61 of 63; likely 89.1-99.1%) |
| **False quarantines** (valid records held) | 0.0% (0 of 44; likely 0.0-8.0%) |
| Legitimate oddities held | 0.0% (0 of 44; likely 0.0-8.0%) |
| Quarantine precision (held records that needed it) | 100.0% (59 of 59; likely 93.9-100.0%) |

Cases not decided as expected: ein_with_space (1 of 1), terms_mixed_case_net (1 of 1)

**Purchase-order lines**

| Measure | Result |
|---|---|
| Faults caught (needed attention, did not go through) | 100.0% (35 of 35; likely 90.1-100.0%) |
| **Faults missed** (bad records that would have loaded) | 0.0% (0 of 35; likely 0.0-9.9%) |
| Exact decision (errors rejected, suspicions reviewed), of faults | 100.0% (35 of 35; likely 90.1-100.0%) |
| **False quarantines** (valid records held) | 2.4% (1 of 42; likely 0.4-12.3%) |
| Legitimate oddities held | 2.4% (1 of 42; likely 0.4-12.3%) |
| Quarantine precision (held records that needed it) | 97.2% (35 of 36; likely 85.8-99.5%) |

Cases not decided as expected: price_high_but_below_factor (1 of 1)

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

