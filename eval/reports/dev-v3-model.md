# Evaluation: dev-v3-model

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 114.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.5% (3584 of 4342; likely 81.4-83.6%) |
| **Silent error rate** (wrong, of values with no review item) | 2.2% (54 of 2482; likely 1.7-2.8%) |
| Silent omissions (missing and nothing flagged) | 4.8% (210 of 4342; likely 4.2-5.5%) |
| Values sent to review | 35.6% (1371 of 3853; likely 34.1-37.1%) |
| Wrong values caught by review | 79.9% (215 of 269; likely 74.7-84.3%) |
| Right values sent to review anyway | 32.3% (1156 of 3584; likely 30.7-33.8%) |
| Answer-key values present in the spread | 88.7% (3853 of 4342; likely 87.8-89.6%) |
| Not judged (the answer key cannot place a row the value includes) | 276 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 91.2% (4669 of 5120; likely 90.4-91.9%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3945 of 4141; likely 94.6-95.9%) |
| structure | 68.0% (451 of 663; likely 64.4-71.5%) |
| model | 89.5% (264 of 295; likely 85.5-92.5%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |
| none | 0.0% (0 of 6; likely 0.0-39.0%) |

Wrong values by kind: value 243, scale 13, sign 10, period 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 28
- dividends_paid missing_silent: 16
- buybacks missing_silent: 16
- debt_repaid missing_silent: 15
- other_opex wrong_review: 15
- debt_issued missing_silent: 12
- stock_issued missing_silent: 11
- eps_basic wrong_review: 10
- eps_diluted wrong_review: 9
- other_noncurrent_liabilities wrong_review: 8
- net_income_parent wrong_review: 7
- sga missing_silent: 7
- ppe_net wrong_review: 7
- shares_basic missing_silent: 6
- shares_diluted missing_silent: 6
- other_current_liabilities wrong_review: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- other_current_assets wrong_review: 6
- total_equity_parent missing_silent: 6
- total_equity wrong_auto: 6
- cf_commercial_paper_net wrong_auto: 5
- income_tax missing_silent: 5
