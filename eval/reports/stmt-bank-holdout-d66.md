# Evaluation: stmt-bank-holdout-d66

10 documents (0 crashed), profile us-bank 2026.10.25-bank-2+a709ec078556, 354.0 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 78.6% (945 of 1203; likely 76.1-80.8%) |
| **Silent error rate** (wrong, of values with no review item) | 0.6% (2 of 310; likely 0.2-2.3%) |
| Silent omissions (missing and nothing flagged) | 8.6% (103 of 1203; likely 7.1-10.3%) |
| Values sent to review | 69.2% (695 of 1005; likely 66.2-71.9%) |
| Wrong values caught by review | 96.7% (58 of 60; likely 88.6-99.1%) |
| Right values sent to review anyway | 67.4% (637 of 945; likely 64.4-70.3%) |
| Answer-key values present in the spread | 83.5% (1005 of 1203; likely 81.3-85.5%) |
| Not judged (the answer key cannot place a row the value includes) | 47 values |
| Open review items per document (reviewer workload) | median 31, mean 30.8; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 92.0% (2800 of 3043; likely 91.0-92.9%) |
| Value read right | 99.5% (2787 of 2800; likely 99.2-99.7%) |
| Period right | 98.5% (2758 of 2800; likely 98.0-98.9%) |
| Template line right (where the key can judge) | 80.1% (1065 of 1330; likely 77.8-82.1%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 94.5% (1052 of 1113; likely 93.0-95.7%) |
| none | 0.0% (0 of 137; likely 0.0-2.7%) |
| structure | 9.9% (7 of 71; likely 4.9-19.0%) |
| fuzzy | 66.7% (6 of 9; likely 35.4-87.9%) |

Wrong values by kind: value 54, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 15
- cf_other_financing wrong_review: 14
- st_investments wrong_review: 8
- other_nonoperating missing_silent: 6
- cf_investments_net missing_silent: 6
- deposits missing_silent: 4
- lt_debt missing_silent: 4
- common_stock_apic wrong_review: 4
- bank_securities wrong_review: 4
- allowance_loan_losses missing_silent: 4
- other_current_liabilities missing_silent: 4
- loans_net missing_silent: 4
- intangibles missing_silent: 4
- bank_interest_income missing_silent: 3
- bank_interest_expense missing_silent: 3
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

Provenance: 2026-11-04T07:47:50+00:00, commit 22f07e2c3d97 with uncommitted changes; datasets: bank-holdout db44c0a14beaaf5a; configuration: profile us-bank 2026.10.25-bank-2+a709ec078556.
