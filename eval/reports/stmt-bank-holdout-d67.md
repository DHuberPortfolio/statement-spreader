# Evaluation: stmt-bank-holdout-d67

10 documents (0 crashed), profile us-bank 2026.10.25-bank-2+0727323187fd, 143.7 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 78.8% (946 of 1201; likely 76.4-81.0%) |
| **Silent error rate** (wrong, of values with no review item) | 0.7% (2 of 302; likely 0.2-2.4%) |
| Silent omissions (missing and nothing flagged) | 7.8% (94 of 1201; likely 6.4-9.5%) |
| Values sent to review | 70.2% (710 of 1012; likely 67.3-72.9%) |
| Wrong values caught by review | 97.0% (64 of 66; likely 89.6-99.2%) |
| Right values sent to review anyway | 68.3% (646 of 946; likely 65.3-71.2%) |
| Answer-key values present in the spread | 84.3% (1012 of 1201; likely 82.1-86.2%) |
| Not judged (the answer key cannot place a row the value includes) | 49 values |
| Open review items per document (reviewer workload) | median 32, mean 32.1; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 92.0% (2800 of 3043; likely 91.0-92.9%) |
| Value read right | 99.5% (2787 of 2800; likely 99.2-99.7%) |
| Period right | 98.5% (2758 of 2800; likely 98.0-98.9%) |
| Template line right (where the key can judge) | 80.5% (1070 of 1330; likely 78.2-82.5%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 94.4% (1057 of 1120; likely 92.9-95.6%) |
| none | 0.0% (0 of 130; likely 0.0-2.9%) |
| structure | 9.9% (7 of 71; likely 4.9-19.0%) |
| fuzzy | 66.7% (6 of 9; likely 35.4-87.9%) |

Wrong values by kind: value 60, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 15
- cf_other_financing wrong_review: 14
- st_investments wrong_review: 8
- bank_securities wrong_review: 8
- cf_investments_net missing_silent: 6
- deposits missing_silent: 4
- common_stock_apic wrong_review: 4
- allowance_loan_losses missing_silent: 4
- other_current_liabilities missing_silent: 4
- loans_net missing_silent: 4
- bank_interest_income missing_silent: 3
- bank_interest_expense missing_silent: 3
- other_nonoperating missing_silent: 3
- revenue wrong_review: 3
- noninterest_expense missing_silent: 3
- eps_basic missing_silent: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_review: 3
- cf_investments_net wrong_review: 3
- debt_issued wrong_review: 3
- nii_after_provision wrong_review: 3
- cf_net_income missing_silent: 3
- cf_dna missing_silent: 3
- cf_sbc missing_silent: 3
- cf_deferred_tax missing_silent: 3

Provenance: 2026-11-04T18:27:36+00:00, commit ab54be2be039 with uncommitted changes; datasets: bank-holdout db44c0a14beaaf5a; configuration: profile us-bank 2026.10.25-bank-2+0727323187fd.
