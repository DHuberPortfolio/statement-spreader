# Reconciliation evaluation: recon-v1

Synthetic bank-vs-ledger sets (generator seeds {'dev': 7, 'holdout': 11, 'stress': 13}, scale 300), profile bank-vs-gl e71b551878cb0de4. The answer key is written by the generator, not computed by the matcher.

## dev (seed 7), strategy `greedy`

678 records, 231 automatic matches, 31 proposals, 114 exceptions, 0.069 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 231; likely 0.0-1.6%) |
| Automatic matches exactly right | 100.0% (231 of 231; likely 98.4-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 52.9% (27 of 51; likely 39.5-65.9%) |
| Pairings that need a person, auto-accepted anyway | 35.3% (18 of 51; likely 23.6-49.0%) |
| All true pairings found (automatic or proposed) | 97.7% (258 of 264; likely 95.1-99.0%) |
| Proposals that are right | 87.1% (27 of 31; likely 71.1-94.9%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 89.6% (86 of 96; likely 81.9-94.2%) |
| Exceptions on records that needed none | 0.0% (0 of 114; likely 0.0-3.3%) |
| Records settled by correct automatic matches | 74.5% (505 of 678; likely 71.1-77.6%) |
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
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 8 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00041']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00064']
- near_miss_ref: UNMATCHED on ['ledger:JE-10138']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00151']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00164']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00177']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00221']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00231']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00262']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00263']

## dev (seed 7), strategy `component`

678 records, 213 automatic matches, 49 proposals, 126 exceptions, 0.11 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 213; likely 0.0-1.8%) |
| Automatic matches exactly right | 100.0% (213 of 213; likely 98.2-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 88.2% (45 of 51; likely 76.6-94.5%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 51; likely 0.0-7.0%) |
| All true pairings found (automatic or proposed) | 97.7% (258 of 264; likely 95.1-99.0%) |
| Proposals that are right | 91.8% (45 of 49; likely 80.8-96.8%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 99.0% (95 of 96; likely 94.3-99.8%) |
| Exceptions on records that needed none | 0.0% (0 of 126; likely 0.0-3.0%) |
| Records settled by correct automatic matches | 69.2% (469 of 678; likely 65.6-72.5%) |
| Bank-side money settled by correct automatic matches | 84.2% |

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
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 8 of 9 |
| noref_1to1 | 60 | 60 |  |  |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- near_miss_ref: UNMATCHED on ['ledger:JE-10138']

## holdout (seed 11), strategy `greedy`

682 records, 231 automatic matches, 33 proposals, 117 exceptions, 0.094 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 231; likely 0.0-1.6%) |
| Automatic matches exactly right | 100.0% (231 of 231; likely 98.4-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 52.9% (27 of 51; likely 39.5-65.9%) |
| Pairings that need a person, auto-accepted anyway | 35.3% (18 of 51; likely 23.6-49.0%) |
| All true pairings found (automatic or proposed) | 97.7% (258 of 264; likely 95.1-99.0%) |
| Proposals that are right | 81.8% (27 of 33; likely 65.6-91.4%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 90.6% (87 of 96; likely 83.1-95.0%) |
| Exceptions on records that needed none | 0.0% (0 of 117; likely 0.0-3.2%) |
| Records settled by correct automatic matches | 74.5% (508 of 682; likely 71.1-77.6%) |
| Bank-side money settled by correct automatic matches | 84.8% |

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
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00068']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00116']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00204']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00209']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00250']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00274']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00285']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00310']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00311']

## holdout (seed 11), strategy `component`

682 records, 213 automatic matches, 51 proposals, 126 exceptions, 0.082 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 213; likely 0.0-1.8%) |
| Automatic matches exactly right | 100.0% (213 of 213; likely 98.2-100.0%) |
| True pairings the rules may settle alone, settled | 100.0% (213 of 213; likely 98.2-100.0%) |
| Pairings that need a person, proposed to one | 88.2% (45 of 51; likely 76.6-94.5%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 51; likely 0.0-7.0%) |
| All true pairings found (automatic or proposed) | 97.7% (258 of 264; likely 95.1-99.0%) |
| Proposals that are right | 88.2% (45 of 51; likely 76.6-94.5%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 100.0% (96 of 96; likely 96.2-100.0%) |
| Exceptions on records that needed none | 0.0% (0 of 126; likely 0.0-3.0%) |
| Records settled by correct automatic matches | 69.2% (472 of 682; likely 65.6-72.6%) |
| Bank-side money settled by correct automatic matches | 83.6% |

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
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

## stress (seed 13, 40% round amounts), strategy `greedy`

677 records, 234 automatic matches, 23 proposals, 112 exceptions, 0.086 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 3.0% (7 of 234; likely 1.5-6.0%) |
| Automatic matches exactly right | 97.0% (227 of 234; likely 94.0-98.5%) |
| True pairings the rules may settle alone, settled | 98.1% (209 of 213; likely 95.3-99.3%) |
| Pairings that need a person, proposed to one | 43.1% (22 of 51; likely 30.5-56.7%) |
| Pairings that need a person, auto-accepted anyway | 35.3% (18 of 51; likely 23.6-49.0%) |
| All true pairings found (automatic or proposed) | 94.3% (249 of 264; likely 90.8-96.5%) |
| Proposals that are right | 95.7% (22 of 23; likely 79.0-99.2%) |
| Records with no counterpart left unmatched | 93.3% (70 of 75; likely 85.3-97.1%) |
| Injected problems raised with the right reason | 84.4% (81 of 96; likely 75.8-90.3%) |
| Exceptions on records that needed none | 1.8% (2 of 112; likely 0.5-6.3%) |
| Records settled by correct automatic matches | 73.3% (496 of 677; likely 69.8-76.5%) |
| Bank-side money settled by correct automatic matches | 81.5% |

| Scenario | Cases | Auto right | Proposed right | Missed | False auto | No-counterpart records left alone | Problems raised |
|---|---|---|---|---|---|---|---|
| ambiguous_twins | 9 | 9 |  |  |  |  | 0 of 9 |
| bank_fee |  |  |  |  |  | 9 of 9 | 9 of 9 |
| batch_noref | 9 |  | 4 | 5 | 1 |  |  |
| batch_ref | 15 | 15 |  |  |  |  |  |
| coincidental_sum |  |  |  |  | 2 | 16 of 18 | 5 of 6 |
| currency_mismatch |  |  |  |  |  | 6 of 6 | 3 of 3 |
| duplicate_ledger | 9 | 9 |  |  |  |  | 8 of 9 |
| fee_deducted | 12 |  | 12 |  |  |  | 12 of 12 |
| keying_error | 6 |  | 6 |  |  |  | 6 of 6 |
| late_clearing | 9 | 9 |  |  |  |  |  |
| missing_bank |  |  |  |  |  | 6 of 6 | 5 of 6 |
| missing_ledger |  |  |  |  | 1 | 5 of 6 | 5 of 6 |
| near_miss_ref | 9 | 9 |  |  | 2 | 7 of 9 | 7 of 9 |
| noref_1to1 | 60 | 56 |  | 4 | 4 |  |  |
| noref_late | 6 |  |  | 6 | 2 |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 9 |  |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

False automatic matches:
- greedy: ['bank:BK-00059'] + ['ledger:JE-10085']
- greedy: ['bank:BK-00073'] + ['ledger:JE-10230']
- greedy: ['bank:BK-00191'] + ['ledger:JE-10101']
- greedy: ['bank:BK-00234'] + ['ledger:JE-10034']
- greedy: ['bank:BK-00262'] + ['ledger:JE-10233']
- greedy: ['bank:BK-00280'] + ['ledger:JE-10320']
- greedy: ['bank:BK-00304'] + ['ledger:JE-10197']

Problems not raised as expected:
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00003']
- near_miss_ref: UNMATCHED on ['ledger:JE-10034']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00044']
- missing_ledger: UNMATCHED on ['bank:BK-00059']
- near_miss_ref: UNMATCHED on ['ledger:JE-10085']
- missing_bank: UNMATCHED on ['ledger:JE-10128']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00105']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00133']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00143']
- ambiguous_twins: AMBIGUOUS_CANDIDATES on ['bank:BK-00166']

## stress (seed 13, 40% round amounts), strategy `component`

677 records, 199 automatic matches, 58 proposals, 127 exceptions, 0.097 s. Same result with rows shuffled: yes. Completeness checks failed: 0.

| Measure | Result |
|---|---|
| **False-match rate** (wrong, of matches made without a person) | 0.0% (0 of 199; likely 0.0-1.9%) |
| Automatic matches exactly right | 100.0% (199 of 199; likely 98.1-100.0%) |
| True pairings the rules may settle alone, settled | 93.4% (199 of 213; likely 89.3-96.0%) |
| Pairings that need a person, proposed to one | 78.4% (40 of 51; likely 65.4-87.5%) |
| Pairings that need a person, auto-accepted anyway | 0.0% (0 of 51; likely 0.0-7.0%) |
| All true pairings found (automatic or proposed) | 94.3% (249 of 264; likely 90.8-96.5%) |
| Proposals that are right | 86.2% (50 of 58; likely 75.1-92.8%) |
| Records with no counterpart left unmatched | 100.0% (75 of 75; likely 95.1-100.0%) |
| Injected problems raised with the right reason | 91.7% (88 of 96; likely 84.4-95.7%) |
| Exceptions on records that needed none | 0.8% (1 of 127; likely 0.1-4.3%) |
| Records settled by correct automatic matches | 65.0% (440 of 677; likely 61.3-68.5%) |
| Bank-side money settled by correct automatic matches | 78.8% |

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
| missing_bank |  |  |  |  |  | 6 of 6 | 3 of 6 |
| missing_ledger |  |  |  |  |  | 6 of 6 | 5 of 6 |
| near_miss_ref | 9 | 9 |  |  |  | 9 of 9 | 6 of 9 |
| noref_1to1 | 60 | 49 | 7 | 4 |  |  |  |
| noref_late | 6 |  |  | 6 |  |  |  |
| outstanding |  |  |  |  |  | 12 of 12 | 12 of 12 |
| ref_1to1 | 102 | 102 |  |  |  |  |  |
| reversal | 9 | 6 | 3 |  |  | 9 of 9 | 9 of 9 |
| split_ref | 9 | 9 |  |  |  |  |  |

Problems not raised as expected:
- missing_bank: UNMATCHED on ['ledger:JE-10006']
- near_miss_ref: UNMATCHED on ['ledger:JE-10034']
- missing_ledger: UNMATCHED on ['bank:BK-00059']
- near_miss_ref: UNMATCHED on ['ledger:JE-10079']
- near_miss_ref: UNMATCHED on ['ledger:JE-10085']
- missing_bank: UNMATCHED on ['ledger:JE-10128']
- missing_bank: UNMATCHED on ['ledger:JE-10220']
- duplicate_ledger: POSSIBLE_DUPLICATE on ['ledger:JE-10319', 'ledger:JE-10320']

## Scale

6778 records reconciled in 3.25 s (one run, this machine); completeness checks failed: 0.

