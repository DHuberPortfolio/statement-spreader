# Reconciliation evaluation: recon-v3

Synthetic bank-vs-ledger sets (generator seeds {'dev': 7, 'holdout': 11, 'stress': 13}, scale 300), profile bank-vs-gl e71b551878cb0de4. The answer key is written by the generator, not computed by the matcher.

## dev (seed 7), strategy `greedy`

690 records, 231 automatic matches, 39 proposals, 123 exceptions, 0.069 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 231; likely 0.0-1.6%) |
| Automatic matches exactly right | 100.0% (231 of 231; likely 98.4-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 57.9% (33 of 57; likely 45.0-69.8%) |
| Pairings that need a person, auto-accepted anyway | 31.6% (18 of 57; likely 21.0-44.5%) |
| All true pairings found (automatic or proposed) | 97.8% (264 of 270; likely 95.2-99.0%) |
| Proposals that are right | 84.6% (33 of 39; likely 70.3-92.8%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 91.2% (93 of 102; likely 84.1-95.3%) |
| Exceptions on records that needed none | 0.0% (0 of 123; likely 0.0-3.0%) |
| Records settled by correct automatic matches | 73.0% (504 of 690; likely 69.6-76.2%) |
| Bank-side money settled by correct automatic matches | 85.0% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 | 9 |  |  |  |  | 0 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 9 |  |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 | 9 |  |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 6 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 6 |  |  |  | 6 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00046']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00098']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00100']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00123']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00155']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00170']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00201']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00268']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00269']

## dev (seed 7), strategy `component`

690 records, 213 automatic matches, 57 proposals, 133 exceptions, 0.065 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 213; likely 0.0-1.8%) |
| Automatic matches exactly right | 100.0% (213 of 213; likely 98.2-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 89.5% (51 of 57; likely 78.9-95.1%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 57; likely 0.0-6.3%) |
| All true pairings found (automatic or proposed) | 97.8% (264 of 270; likely 95.2-99.0%) |
| Proposals that are right | 89.5% (51 of 57; likely 78.9-95.1%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 100.0% (102 of 102; likely 96.4-100.0%) |
| Exceptions on records that needed none | 0.0% (0 of 133; likely 0.0-2.8%) |
| Records settled by correct automatic matches | 67.8% (468 of 690; likely 64.3-71.2%) |
| Bank-side money settled by correct automatic matches | 83.8% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 |  | 9 |  |  |  | 9 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 9 |  |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 |  | 9 |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 6 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 6 |  |  |  | 6 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

## holdout (seed 11), strategy `greedy`

688 records, 231 automatic matches, 39 proposals, 123 exceptions, 0.061 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 231; likely 0.0-1.6%) |
| Automatic matches exactly right | 100.0% (231 of 231; likely 98.4-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 57.9% (33 of 57; likely 45.0-69.8%) |
| Pairings that need a person, auto-accepted anyway | 31.6% (18 of 57; likely 21.0-44.5%) |
| All true pairings found (automatic or proposed) | 97.8% (264 of 270; likely 95.2-99.0%) |
| Proposals that are right | 84.6% (33 of 39; likely 70.3-92.8%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 91.2% (93 of 102; likely 84.1-95.3%) |
| Exceptions on records that needed none | 0.0% (0 of 123; likely 0.0-3.0%) |
| Records settled by correct automatic matches | 73.8% (508 of 688; likely 70.4-77.0%) |
| Bank-side money settled by correct automatic matches | 85.7% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 | 9 |  |  |  |  | 0 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 9 |  |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 | 9 |  |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 6 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 6 |  |  |  | 6 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00052']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00124']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00163']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00206']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00256']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00280']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00291']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00316']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00317']

## holdout (seed 11), strategy `component`

688 records, 213 automatic matches, 57 proposals, 133 exceptions, 0.062 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 213; likely 0.0-1.8%) |
| Automatic matches exactly right | 100.0% (213 of 213; likely 98.2-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 89.5% (51 of 57; likely 78.9-95.1%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 57; likely 0.0-6.3%) |
| All true pairings found (automatic or proposed) | 97.8% (264 of 270; likely 95.2-99.0%) |
| Proposals that are right | 89.5% (51 of 57; likely 78.9-95.1%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 100.0% (102 of 102; likely 96.4-100.0%) |
| Exceptions on records that needed none | 0.0% (0 of 133; likely 0.0-2.8%) |
| Records settled by correct automatic matches | 68.6% (472 of 688; likely 65.0-72.0%) |
| Bank-side money settled by correct automatic matches | 84.5% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 |  | 9 |  |  |  | 9 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 9 |  |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 |  | 9 |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 6 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 6 |  |  |  | 6 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

## stress (seed 13, 40% round amounts), strategy `greedy`

685 records, 233 automatic matches, 33 proposals, 118 exceptions, 0.062 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 1.3% (3 of 233; likely 0.4-3.7%) |
| Automatic matches exactly right | 98.7% (230 of 233; likely 96.3-99.6%) |
| True pairings the rules may settle alone, settled | 99.5% (212 of 213; likely 97.4-99.9%) |
| Pairings that need a person, proposed to one | 49.1% (28 of 57; likely 36.6-61.7%) |
| Pairings that need a person, auto-accepted anyway | 31.6% (18 of 57; likely 21.0-44.5%) |
| All true pairings found (automatic or proposed) | 95.6% (258 of 270; likely 92.4-97.4%) |
| Proposals that are right | 84.8% (28 of 33; likely 69.1-93.3%) |
| Records with no counterpart left unmatched | 98.7% (74 of 75; likely 92.8-99.8%) |
| Injected problems raised with the right reason | 85.3% (87 of 102; likely 77.1-90.9%) |
| Exceptions on records that needed none | 0.0% (0 of 118; likely 0.0-3.2%) |
| Records settled by correct automatic matches | 73.1% (501 of 685; likely 69.7-76.3%) |
| Bank-side money settled by correct automatic matches | 80.7% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 | 9 |  |  |  |  | 0 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 5 | 4 | 2 |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 | 9 |  |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  | 1 | 5 of 6 | 4 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 6 of 9 |
| noref_1to1 | 60 | 59 |  | 1 | 2 |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 5 | 1 |  |  | 5 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

False automatic matches:
- greedy: ['bank:BK-00002'] + ['ledger:JE-10161']
- greedy: ['bank:BK-00029'] + ['ledger:JE-10073']
- greedy: ['bank:BK-00033'] + ['ledger:JE-10002']

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00028']
- missing_ledger: UNMATCHED on ['bank:BK-00029']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00038']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00049']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00057']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00081']
- near_miss_ref: UNMATCHED on ['ledger:JE-10138']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00139']
- partial_payment: PARTIAL_MATCH on ['bank:BK-00149', 'ledger:JE-10179']
- near_miss_ref: UNMATCHED on ['ledger:JE-10201']

## stress (seed 13, 40% round amounts), strategy `component`

685 records, 199 automatic matches, 67 proposals, 132 exceptions, 0.064 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 199; likely 0.0-1.9%) |
| Automatic matches exactly right | 100.0% (199 of 199; likely 98.1-100.0%) |
| True pairings the rules may settle alone, settled | 93.4% (199 of 213; likely 89.3-96.0%) |
| Pairings that need a person, proposed to one | 80.7% (46 of 57; likely 68.7-88.9%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 57; likely 0.0-6.3%) |
| All true pairings found (automatic or proposed) | 95.9% (259 of 270; likely 92.9-97.7%) |
| Proposals that are right | 89.6% (60 of 67; likely 80.0-94.8%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 93.1% (95 of 102; likely 86.5-96.6%) |
| Exceptions on records that needed none | 0.0% (0 of 132; likely 0.0-2.8%) |
| Records settled by correct automatic matches | 64.1% (439 of 685; likely 60.4-67.6%) |
| Bank-side money settled by correct automatic matches | 78.2% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 |  | 9 |  |  |  | 9 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 5 | 4 |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 |  | 9 |  |  |  | 9 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 5 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 4 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 6 of 9 |
| noref_1to1 | 60 | 49 | 11 |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 5 | 1 |  |  | 5 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 6 | 3 |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- missing_ledger: UNMATCHED on ['bank:BK-00029']
- near_miss_ref: UNMATCHED on ['ledger:JE-10138']
- missing_bank: UNMATCHED on ['ledger:JE-10154']
- partial_payment: PARTIAL_MATCH on ['bank:BK-00149', 'ledger:JE-10179']
- near_miss_ref: UNMATCHED on ['ledger:JE-10201']
- missing_ledger: UNMATCHED on ['bank:BK-00197']
- near_miss_ref: UNMATCHED on ['ledger:JE-10240']

## Scale

6898 records reconciled in 2.63 s (one run, this machine); completeness checks failed: 0.

