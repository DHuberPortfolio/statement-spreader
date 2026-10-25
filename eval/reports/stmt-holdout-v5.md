# Evaluation: stmt-holdout-v5

30 documents (1 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 114.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 73.5% (2858 of 3890; likely 72.1-74.8%) |
| **Silent error rate** (wrong, of values with no review item) | 3.2% (66 of 2093; likely 2.5-4.0%) |
| Silent omissions (missing and nothing flagged) | 3.9% (152 of 3890; likely 3.3-4.6%) |
| Values sent to review | 36.3% (1193 of 3286; likely 34.7-38.0%) |
| Wrong values caught by review | 84.6% (362 of 428; likely 80.9-87.7%) |
| Right values sent to review anyway | 29.1% (831 of 2858; likely 27.4-30.8%) |
| Answer-key values present in the spread | 84.5% (3286 of 3890; likely 83.3-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 156 values |
| Open review items per document (reviewer workload) | median 20, mean 20.4; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.2% (5824 of 6526; likely 88.5-90.0%) |
| Value read right | 95.1% (5537 of 5824; likely 94.5-95.6%) |
| Period right | 92.8% (5402 of 5824; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 86.3% (3778 of 4377; likely 85.3-87.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3439 of 3574; likely 95.5-96.8%) |
| structure | 66.7% (321 of 481; likely 62.4-70.8%) |
| none | 0.0% (0 of 304; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 182, scale 135, period 104, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 35
- other_noncurrent_liabilities wrong_review: 22
- other_opex wrong_review: 22
- cf_working_capital missing_silent: 16
- eps_basic missing_silent: 15
- eps_diluted missing_silent: 15
- other_nonoperating wrong_review: 14
- deferred_revenue_current wrong_review: 10
- interest_expense wrong_review: 10
- cash_end wrong_review: 10
- net_income wrong_review: 9
- shares_basic wrong_review: 9
- shares_diluted wrong_review: 9
- other_current_assets wrong_review: 8
- cash_end missing_silent: 8
- net_income_parent wrong_review: 7
- cf_dna wrong_review: 7
- cfo wrong_review: 7
- cfi wrong_review: 7
- net_change_cash wrong_review: 7
- pretax_income wrong_review: 7
- accrued_liabilities wrong_review: 6
- total_costs missing_silent: 6
- st_debt wrong_review: 6
- revenue wrong_review: 6
