# Evaluation: dev-final

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 117.8 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 79.6% (3521 of 4425; likely 78.4-80.7%) |
| **Silent error rate** (wrong, of values with no review item) | 2.7% (69 of 2520; likely 2.2-3.5%) |
| Silent omissions (missing and nothing flagged) | 4.4% (193 of 4425; likely 3.8-5.0%) |
| Values sent to review | 32.6% (1220 of 3740; likely 31.1-34.1%) |
| Wrong values caught by review | 68.5% (150 of 219; likely 62.1-74.3%) |
| Right values sent to review anyway | 30.4% (1070 of 3521; likely 28.9-31.9%) |
| Answer-key values present in the spread | 84.5% (3740 of 4425; likely 83.4-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 187 values |
| Open review items per document (reviewer workload) | median 21, mean 20.8; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 86.3% (4396 of 5096; likely 85.3-87.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3936 of 4132; likely 94.6-95.9%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 194, scale 13, sign 10, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- eps_basic missing_silent: 16
- eps_diluted missing_silent: 16
- other_nonoperating wrong_review: 13
- other_noncurrent_liabilities wrong_review: 10
- cf_working_capital missing_silent: 10
- other_opex wrong_review: 10
- other_nonoperating wrong_auto: 8
- common_stock_apic wrong_auto: 8
- operating_income missing_silent: 7
- pretax_income missing_silent: 7
- net_income missing_silent: 7
- income_tax missing_silent: 6
- cf_net_income missing_silent: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- other_current_assets wrong_review: 6
- cf_commercial_paper_net wrong_auto: 5
- cogs missing_silent: 5
- net_income_parent wrong_auto: 5
- shares_basic missing_silent: 5
- shares_diluted missing_silent: 5
- cf_investments_net wrong_review: 5
- shares_basic wrong_review: 5
