# Evaluation: dev-final-model

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 121.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.8% (3587 of 4333; likely 81.6-83.9%) |
| **Silent error rate** (wrong, of values with no review item) | 2.1% (52 of 2463; likely 1.6-2.8%) |
| Silent omissions (missing and nothing flagged) | 3.5% (150 of 4333; likely 3.0-4.0%) |
| Values sent to review | 35.9% (1381 of 3844; likely 34.4-37.5%) |
| Wrong values caught by review | 79.8% (205 of 257; likely 74.4-84.2%) |
| Right values sent to review anyway | 32.8% (1176 of 3587; likely 31.3-34.3%) |
| Answer-key values present in the spread | 88.7% (3844 of 4333; likely 87.7-89.6%) |
| Not judged (the answer key cannot place a row the value includes) | 279 values |
| Open review items per document (reviewer workload) | median 26, mean 27.0; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 91.4% (4657 of 5096; likely 90.6-92.1%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3936 of 4132; likely 94.6-95.9%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| model | 89.4% (261 of 292; likely 85.3-92.4%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |
| none | 0.0% (0 of 6; likely 0.0-39.0%) |

Wrong values by kind: value 231, scale 13, sign 10, period 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 16
- other_opex wrong_review: 15
- eps_basic wrong_review: 10
- eps_diluted wrong_review: 9
- other_noncurrent_liabilities wrong_review: 8
- net_income_parent wrong_review: 7
- ppe_net wrong_review: 7
- income_tax missing_silent: 6
- eps_basic missing_silent: 6
- eps_diluted missing_silent: 6
- other_current_liabilities wrong_review: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- other_current_assets wrong_review: 6
- total_equity_parent missing_silent: 6
- total_equity wrong_auto: 6
- cf_commercial_paper_net wrong_auto: 5
- shares_basic missing_silent: 5
- shares_diluted missing_silent: 5
- other_noncurrent_liabilities wrong_auto: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- debt_issued missing_silent: 5
