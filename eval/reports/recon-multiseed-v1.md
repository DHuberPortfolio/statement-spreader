# Reconciliation, 10 seeds x 3 kinds of set (scale 300)

Seeds 101-110; profile bank-vs-gl e71b551878cb0de4; component strategy. Order-unstable sets: 0 []; completeness checks failed: 0; 5.5 s in all.

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
| false_match_rate | 0.1% (2 of 1978; likely 0.0-0.4%) |
| review_cases_auto_accepted | 0.0% (0 of 570; likely 0.0-0.7%) |
| auto_recall | 92.8% (1976 of 2130; likely 91.6-93.8%) |
| review_cases_reaching_review | 76.3% (435 of 570; likely 72.7-79.6%) |
| exception_recall | 88.9% (907 of 1020; likely 86.8-90.7%) |
| left_alone_accuracy | 99.6% (747 of 750; likely 98.8-99.9%) |
| proposal_precision | 86.6% (581 of 671; likely 83.8-89.0%) |
| unnecessary_exceptions | 0.4% (5 of 1326; likely 0.2-0.9%) |

Planted problems not raised, by scenario / code:
- missing_ledger / UNMATCHED: 30
- near_miss_ref / UNMATCHED: 29
- missing_bank / UNMATCHED: 24
- partial_payment / PARTIAL_MATCH: 15
- reversal / REVERSAL: 6
- duplicate_ledger / POSSIBLE_DUPLICATE: 5
- outstanding / TIMING_DIFFERENCE: 4

First failures:
- seed 101: missed UNMATCHED on ['bank:BK-00019'] (missing_ledger)
- seed 101: missed UNMATCHED on ['bank:BK-00033'] (missing_ledger)
- seed 101: missed UNMATCHED on ['ledger:JE-10044'] (missing_bank)
- seed 101: missed UNMATCHED on ['ledger:JE-10051'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['ledger:JE-10058'] (missing_bank)
- seed 101: missed UNMATCHED on ['ledger:JE-10076'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['bank:BK-00116'] (missing_ledger)
- seed 101: missed UNMATCHED on ['bank:BK-00168'] (missing_ledger)
- seed 101: missed REVERSAL on ['bank:BK-00199'] (reversal)
- seed 101: missed UNMATCHED on ['bank:BK-00276'] (missing_ledger)
- seed 101: missed PARTIAL_MATCH on ['bank:BK-00287', 'ledger:JE-10332'] (partial_payment)
- seed 101: missed UNMATCHED on ['ledger:JE-10341'] (near_miss_ref)
- seed 101: missed UNMATCHED on ['ledger:JE-10357'] (near_miss_ref)
- seed 102: missed TIMING_DIFFERENCE on ['ledger:JE-10044'] (outstanding)
- seed 102: missed UNMATCHED on ['bank:BK-00046'] (missing_ledger)
- seed 102: missed UNMATCHED on ['bank:BK-00048'] (missing_ledger)
- seed 102: missed UNMATCHED on ['ledger:JE-10076'] (missing_bank)
- seed 102: missed PARTIAL_MATCH on ['bank:BK-00194', 'ledger:JE-10232'] (partial_payment)
- seed 102: missed UNMATCHED on ['ledger:JE-10238'] (near_miss_ref)
- seed 102: missed REVERSAL on ['bank:BK-00212'] (reversal)
- seed 102: missed UNMATCHED on ['ledger:JE-10362'] (missing_bank)
- seed 103: missed UNMATCHED on ['ledger:JE-10006'] (near_miss_ref)
- seed 103: missed UNMATCHED on ['bank:BK-00006'] (missing_ledger)
- seed 103: missed UNMATCHED on ['bank:BK-00008'] (missing_ledger)
- seed 103: missed POSSIBLE_DUPLICATE on ['ledger:JE-10073', 'ledger:JE-10074'] (duplicate_ledger)

## messy

| Measure | Pooled |
|---|---|
| false_match_rate | 0.2% (4 of 2166; likely 0.1-0.5%) |
| review_cases_auto_accepted | 0.0% (0 of 570; likely 0.0-0.7%) |
| auto_recall | 84.1% (2162 of 2571; likely 82.6-85.5%) |
| review_cases_reaching_review | 80.7% (460 of 570; likely 77.3-83.7%) |
| exception_recall | 91.4% (932 of 1020; likely 89.5-92.9%) |
| left_alone_accuracy | 99.6% (747 of 750; likely 98.8-99.9%) |
| proposal_precision | 90.7% (817 of 901; likely 88.6-92.4%) |
| unnecessary_exceptions | 7.7% (113 of 1475; likely 6.4-9.1%) |

Planted problems not raised, by scenario / code:
- near_miss_ref / UNMATCHED: 23
- bank_fee / UNRECORDED_FEE: 13
- missing_ledger / UNMATCHED: 11
- partial_payment / PARTIAL_MATCH: 11
- missing_bank / UNMATCHED: 8
- fee_deducted / AMOUNT_DIFFERENCE: 6
- outstanding / TIMING_DIFFERENCE: 4
- currency_mismatch / CURRENCY_MISMATCH: 4
- reversal / REVERSAL: 3
- duplicate_ledger / POSSIBLE_DUPLICATE: 3
- keying_error / AMOUNT_DIFFERENCE: 2

First failures:
- seed 101: FALSE AUTO unique_amount_date ['bank:BK-00031'] + ['ledger:JE-10133']
- seed 101: FALSE AUTO assignment ['bank:BK-00245'] + ['ledger:JE-10057']
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
- seed 102: missed UNMATCHED on ['ledger:JE-10063'] (near_miss_ref)
- seed 102: missed UNMATCHED on ['ledger:JE-10081'] (near_miss_ref)
- seed 102: missed UNMATCHED on ['ledger:JE-10295'] (missing_bank)
- seed 102: missed UNMATCHED on ['ledger:JE-10337'] (missing_bank)
- seed 102: missed UNMATCHED on ['ledger:JE-10368'] (near_miss_ref)
- seed 103: missed AMOUNT_DIFFERENCE on ['bank:BK-00007', 'ledger:JE-10008'] (fee_deducted)
- seed 103: missed AMOUNT_DIFFERENCE on ['bank:BK-00065', 'ledger:JE-10075'] (fee_deducted)
- seed 103: missed UNMATCHED on ['ledger:JE-10107'] (near_miss_ref)
- seed 103: missed REVERSAL on ['bank:BK-00143'] (reversal)
- seed 103: missed UNMATCHED on ['bank:BK-00208'] (missing_ledger)
- seed 103: missed UNMATCHED on ['ledger:JE-10321'] (missing_bank)
- seed 103: missed UNMATCHED on ['ledger:JE-10365'] (missing_bank)

