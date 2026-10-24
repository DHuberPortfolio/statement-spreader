# Evaluation: dev-final-model

33 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 95.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 83.3% (3608 of 4333; likely 82.1-84.3%) |
| **Silent error rate** (wrong, of values with no review item) | 2.1% (53 of 2485; likely 1.6-2.8%) |
| Silent omissions (missing and nothing flagged) | 3.0% (128 of 4333; likely 2.5-3.5%) |
| Values sent to review | 35.7% (1381 of 3866; likely 34.2-37.2%) |
| Wrong values caught by review | 79.5% (205 of 258; likely 74.1-83.9%) |
| Right values sent to review anyway | 32.6% (1176 of 3608; likely 31.1-34.1%) |
| Answer-key values present in the spread | 89.2% (3866 of 4333; likely 88.3-90.1%) |
| Not judged (the answer key cannot place a row the value includes) | 279 values |
| Open review items per document (reviewer workload) | median 25, mean 26.6; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 93.4% (6454 of 6912; likely 92.8-93.9%) |
| Template line right (where the key can judge) | 91.4% (4696 of 5138; likely 90.6-92.1%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3975 of 4174; likely 94.5-95.8%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| model | 89.4% (261 of 292; likely 85.3-92.4%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |
| none | 0.0% (0 of 6; likely 0.0-39.0%) |

Wrong values by kind: value 232, scale 13, sign 10, period 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 16
- other_opex wrong_review: 15
- eps_basic wrong_review: 10
- eps_diluted wrong_review: 9
- other_noncurrent_liabilities wrong_review: 8
- net_income_parent wrong_review: 7
- ppe_net wrong_review: 7
- other_current_liabilities wrong_review: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- other_current_assets wrong_review: 6
- total_equity_parent missing_silent: 6
- total_equity wrong_auto: 6
- cf_commercial_paper_net wrong_auto: 5
- other_noncurrent_liabilities wrong_auto: 5
- income_tax missing_silent: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- debt_issued missing_silent: 5
- debt_repaid missing_silent: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
