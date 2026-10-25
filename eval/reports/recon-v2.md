# Reconciliation evaluation: recon-v2

Synthetic bank-vs-ledger sets (generator seeds {'dev': 7, 'holdout': 11, 'stress': 13}, scale 300), profile bank-vs-gl e71b551878cb0de4. The answer key is written by the generator, not computed by the matcher.

## dev (seed 7), strategy `greedy`

690 records, 231 automatic matches, 39 proposals, 123 exceptions, 0.068 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

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

690 records, 213 automatic matches, 57 proposals, 133 exceptions, 0.061 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

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

688 records, 231 automatic matches, 39 proposals, 123 exceptions, 0.058 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

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

688 records, 213 automatic matches, 57 proposals, 133 exceptions, 0.059 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

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

685 records, 232 automatic matches, 33 proposals, 120 exceptions, 0.061 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 5.2% (12 of 232; likely 3.0-8.8%) |
| Automatic matches exactly right | 94.8% (220 of 232; likely 91.2-97.0%) |
| True pairings the rules may settle alone, settled | 94.8% (202 of 213; likely 91.0-97.1%) |
| Pairings that need a person, proposed to one | 47.4% (27 of 57; likely 35.0-60.1%) |
| Pairings that need a person, auto-accepted anyway | 31.6% (18 of 57; likely 21.0-44.5%) |
| All true pairings found (automatic or proposed) | 91.5% (247 of 270; likely 87.5-94.3%) |
| Proposals that are right | 81.8% (27 of 33; likely 65.6-91.4%) |
| Records with no counterpart left unmatched | 97.3% (73 of 75; likely 90.8-99.3%) |
| Injected problems raised with the right reason | 83.3% (85 of 102; likely 74.9-89.3%) |
| Exceptions on records that needed none | 4.2% (5 of 120; likely 1.8-9.4%) |
| Records settled by correct automatic matches | 70.2% (481 of 685; likely 66.7-73.5%) |
| Bank-side money settled by correct automatic matches | 80.2% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 | 9 |  |  |  |  | 0 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 4 | 5 | 4 |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 | 9 |  |  |  |  | 8 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 6 of 6 |
| missing_ledger |  |  |  |  | 1 | 5 of 6 | 4 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 6 of 9 |
| noref_1to1 | 60 | 49 |  | 11 | 11 |  |  |
| noref_late | 6 |  |  | 6 | 1 |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 5 | 1 |  |  | 5 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  | 1 | 8 of 9 | 8 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

False automatic matches:
- greedy: ['bank:BK-00002'] + ['ledger:JE-10161']
- greedy: ['bank:BK-00010'] + ['ledger:JE-10127']
- greedy: ['bank:BK-00018'] + ['ledger:JE-10156']
- greedy: ['bank:BK-00029'] + ['ledger:JE-10073']
- greedy: ['bank:BK-00033'] + ['ledger:JE-10002']
- greedy: ['bank:BK-00079'] + ['ledger:JE-10013']
- greedy: ['bank:BK-00114'] + ['ledger:JE-10171']
- greedy: ['bank:BK-00140'] + ['ledger:JE-10136']
- greedy: ['bank:BK-00267'] + ['ledger:JE-10066']
- greedy: ['bank:BK-00291'] + ['ledger:JE-10178']

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

685 records, 196 automatic matches, 70 proposals, 131 exceptions, 0.062 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 196; likely 0.0-1.9%) |
| Automatic matches exactly right | 100.0% (196 of 196; likely 98.1-100.0%) |
| True pairings the rules may settle alone, settled | 92.0% (196 of 213; likely 87.6-95.0%) |
| Pairings that need a person, proposed to one | 78.9% (45 of 57; likely 66.7-87.5%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 57; likely 0.0-6.3%) |
| All true pairings found (automatic or proposed) | 93.3% (252 of 270; likely 89.7-95.7%) |
| Proposals that are right | 80.0% (56 of 70; likely 69.2-87.7%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 91.2% (93 of 102; likely 84.1-95.3%) |
| Exceptions on records that needed none | 0.8% (1 of 131; likely 0.1-4.2%) |
| Records settled by correct automatic matches | 63.2% (433 of 685; likely 59.5-66.7%) |
| Bank-side money settled by correct automatic matches | 78.0% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 |  | 9 |  |  |  | 9 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 4 | 5 |  |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  |  | 18 of 18 | 6 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 |  | 9 |  |  |  | 8 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 5 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 4 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 6 of 9 |
| noref_1to1 | 60 | 46 | 8 | 6 |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| partial_payment | 6 |  | 5 | 1 |  |  | 5 of 6 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 6 | 3 |  |  | 9 of 9 | 8 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- missing_ledger: UNMATCHED on ['bank:BK-00029']
- near_miss_ref: UNMATCHED on ['ledger:JE-10138']
- missing_bank: UNMATCHED on ['ledger:JE-10154']
- partial_payment: PARTIAL_MATCH on ['bank:BK-00149', 'ledger:JE-10179']
- near_miss_ref: UNMATCHED on ['ledger:JE-10201']
- missing_ledger: UNMATCHED on ['bank:BK-00197']
- near_miss_ref: UNMATCHED on ['ledger:JE-10240']
- duplicate_ledger: POSSIBLE_DUPLICATE on ['ledger:JE-10323', 'ledger:JE-10324']
- reversal: REVERSAL on ['bank:BK-00291']

## Scale

6898 records reconciled in 2.62 s (one run, this machine); completeness checks failed: 0.

