# Reconciliation, 10 seeds x 3 kinds of set (scale 300)

Seeds 101-110; profile bank-vs-gl e71b551878cb0de4; component strategy. Order-unstable sets: 0 []; completeness checks failed: 0; 4.9 s in all.

## clean

| Measure | Pooled |
|---|---|
| false_match_rate | 0.0% (0 of 2130; likely 0.0-0.2%) |
| review_cases_auto_accepted | 0.0% (0 of 570; likely 0.0-0.7%) |
| auto_recall | 100.0% (2130 of 2130; likely 99.8-100.0%) |
| review_cases_reaching_review | 87.5% (499 of 570; likely 84.6-90.0%) |
| exception_recall | 99.5% (1015 of 1020; likely 98.9-99.8%) |
| left_alone_accuracy | 100.0% (750 of 750; likely 99.5-100.0%) |
| proposal_precision | 90.6% (499 of 551; likely 87.8-92.7%) |
| unnecessary_exceptions | 0.0% (0 of 1325; likely 0.0-0.3%) |

Planted problems not raised, by scenario / code:
- near_miss_ref / UNMATCHED: 3
- missing_ledger / UNMATCHED: 1
- missing_bank / UNMATCHED: 1

First failures:
- seed 101: missed UNMATCHED on ['bank:BK-00034'] (missing_ledger)
- seed 102: missed UNMATCHED on ['ledger:JE-10005'] (near_miss_ref)
- seed 105: missed UNMATCHED on ['ledger:JE-10162'] (near_miss_ref)
- seed 110: missed UNMATCHED on ['ledger:JE-10062'] (missing_bank)
- seed 110: missed UNMATCHED on ['ledger:JE-10328'] (near_miss_ref)

## stress

| Measure | Pooled |
|---|---|
| false_match_rate | 0.0% (1 of 2114; likely 0.0-0.3%) |
| review_cases_auto_accepted | 0.0% (0 of 570; likely 0.0-0.7%) |
| auto_recall | 99.2% (2113 of 2130; likely 98.7-99.5%) |
| review_cases_reaching_review | 76.5% (436 of 570; likely 72.8-79.8%) |
| exception_recall | 91.1% (929 of 1020; likely 89.2-92.7%) |
| left_alone_accuracy | 99.7% (748 of 750; likely 99.0-99.9%) |
| proposal_precision | 84.7% (450 of 531; likely 81.4-87.6%) |
| unnecessary_exceptions | 0.4% (5 of 1296; likely 0.2-0.9%) |

Planted problems not raised, by scenario / code:
- near_miss_ref / UNMATCHED: 24
- missing_ledger / UNMATCHED: 23
- missing_bank / UNMATCHED: 19
- partial_payment / PARTIAL_MATCH: 15
- reversal / REVERSAL: 5
- duplicate_ledger / POSSIBLE_DUPLICATE: 4
- coincidental_sum / UNMATCHED: 1

First failures:
- seed 101: missed UNMATCHED on ['bank:BK-00019'] (missing_ledger)
- seed 101: missed UNMATCHED on ['bank:BK-00033'] (missing_ledger)
- seed 101: missed UNMATCHED on ['ledger:JE-10044'] (missing_bank)
- seed 101: missed UNMATCHED on ['ledger:JE-10051'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['ledger:JE-10058'] (missing_bank)
- seed 101: missed UNMATCHED on ['bank:BK-00168'] (missing_ledger)
- seed 101: missed REVERSAL on ['bank:BK-00199'] (reversal)
- seed 101: missed PARTIAL_MATCH on ['bank:BK-00287', 'ledger:JE-10332'] (partial_payment)
- seed 101: missed UNMATCHED on ['ledger:JE-10341'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['ledger:JE-10357'] (near_miss_ref)
- seed 102: missed UNMATCHED on ['bank:BK-00048'] (missing_ledger)
- seed 102: missed UNMATCHED on ['ledger:JE-10076'] (missing_bank)
- seed 102: missed PARTIAL_MATCH on ['bank:BK-00194', 'ledger:JE-10232'] (partial_payment)
- seed 102: missed REVERSAL on ['bank:BK-00212'] (reversal)
- seed 102: missed UNMATCHED on ['ledger:JE-10362'] (missing_bank)
- seed 103: missed UNMATCHED on ['ledger:JE-10006'] (near_miss_ref)
- seed 103: missed UNMATCHED on ['bank:BK-00006'] (missing_ledger)
- seed 103: missed UNMATCHED on ['bank:BK-00008'] (missing_ledger)
- seed 103: missed POSSIBLE_DUPLICATE on ['ledger:JE-10073', 'ledger:JE-10074'] (duplicate_ledger)
- seed 103: missed UNMATCHED on ['bank:BK-00082'] (missing_ledger)
- seed 103: missed UNMATCHED on ['ledger:JE-10111'] (near_miss_ref)
- seed 103: missed UNMATCHED on ['ledger:JE-10136'] (near_miss_ref)
- seed 103: missed PARTIAL_MATCH on ['bank:BK-00204', 'ledger:JE-10231'] (partial_payment)
- seed 103: missed PARTIAL_MATCH on ['bank:BK-00214', 'ledger:JE-10244'] (partial_payment)
- seed 103: missed UNMATCHED on ['ledger:JE-10256'] (near_miss_ref)

## messy

| Measure | Pooled |
|---|---|
| false_match_rate | 0.1% (2 of 2229; likely 0.0-0.3%) |
| review_cases_auto_accepted | 0.0% (0 of 570; likely 0.0-0.7%) |
| auto_recall | 86.6% (2227 of 2571; likely 85.2-87.9%) |
| review_cases_reaching_review | 80.7% (460 of 570; likely 77.3-83.7%) |
| exception_recall | 92.7% (946 of 1020; likely 91.0-94.2%) |
| left_alone_accuracy | 99.6% (747 of 750; likely 98.8-99.9%) |
| proposal_precision | 90.3% (757 of 838; likely 88.1-92.2%) |
| unnecessary_exceptions | 7.3% (105 of 1448; likely 6.0-8.7%) |

Planted problems not raised, by scenario / code:
- bank_fee / UNRECORDED_FEE: 13
- near_miss_ref / UNMATCHED: 13
- partial_payment / PARTIAL_MATCH: 11
- missing_ledger / UNMATCHED: 10
- missing_bank / UNMATCHED: 6
- fee_deducted / AMOUNT_DIFFERENCE: 6
- currency_mismatch / CURRENCY_MISMATCH: 4
- reversal / REVERSAL: 3
- outstanding / TIMING_DIFFERENCE: 3
- duplicate_ledger / POSSIBLE_DUPLICATE: 3
- keying_error / AMOUNT_DIFFERENCE: 2

First failures:
- seed 101: FALSE AUTO unique_amount_date ['bank:BK-00031'] + ['ledger:JE-10133']
- seed 101: missed UNMATCHED on ['bank:BK-00001'] (missing_ledger)
- seed 101: missed REVERSAL on ['bank:BK-00016'] (reversal)
- seed 101: missed UNMATCHED on ['bank:BK-00031'] (missing_ledger)
- seed 101: missed UNRECORDED_FEE on ['bank:BK-00041'] (bank_fee)
- seed 101: missed PARTIAL_MATCH on ['bank:BK-00055', 'ledger:JE-10057'] (partial_payment)
- seed 101: missed UNMATCHED on ['ledger:JE-10149'] (missing_bank)
- seed 101: missed UNMATCHED on ['bank:BK-00232'] (missing_ledger)
- seed 101: missed TIMING_DIFFERENCE on ['ledger:JE-10269'] (outstanding)
- seed 101: missed UNMATCHED on ['ledger:JE-10314'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['bank:BK-00280'] (missing_ledger)
- seed 101: missed UNMATCHED on ['ledger:JE-10330'] (near_miss_ref)
- seed 102: missed UNMATCHED on ['ledger:JE-10368'] (near_miss_ref)
- seed 103: FALSE AUTO assignment ['bank:BK-00153'] + ['ledger:JE-10064']
- seed 103: missed AMOUNT_DIFFERENCE on ['bank:BK-00007', 'ledger:JE-10008'] (fee_deducted)
- seed 103: missed AMOUNT_DIFFERENCE on ['bank:BK-00065', 'ledger:JE-10075'] (fee_deducted)
- seed 103: missed UNMATCHED on ['ledger:JE-10107'] (near_miss_ref)
- seed 103: missed REVERSAL on ['bank:BK-00143'] (reversal)
- seed 103: missed UNMATCHED on ['bank:BK-00208'] (missing_ledger)
- seed 103: missed UNMATCHED on ['ledger:JE-10321'] (missing_bank)
- seed 103: missed UNMATCHED on ['ledger:JE-10365'] (missing_bank)
- seed 103: missed UNRECORDED_FEE on ['bank:BK-00325'] (bank_fee)
- seed 103: missed CURRENCY_MISMATCH on ['bank:BK-00337', 'ledger:JE-10384'] (currency_mismatch)
- seed 103: missed REVERSAL on ['bank:BK-00352'] (reversal)
- seed 104: missed TIMING_DIFFERENCE on ['ledger:JE-10008'] (outstanding)

