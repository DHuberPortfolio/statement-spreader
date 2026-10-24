# Evaluation: dev-model-qwen3-4b

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 345.9 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 83.2% (3616 of 4348; likely 82.0-84.2%) |
| **Silent error rate** (wrong, of values with no review item) | 2.2% (53 of 2451; likely 1.7-2.8%) |
| Silent omissions (missing and nothing flagged) | 4.6% (198 of 4348; likely 4.0-5.2%) |
| Values sent to review | 36.9% (1434 of 3885; likely 35.4-38.4%) |
| Wrong values caught by review | 80.3% (216 of 269; likely 75.1-84.6%) |
| Right values sent to review anyway | 33.7% (1218 of 3616; likely 32.2-35.2%) |
| Answer-key values present in the spread | 89.4% (3885 of 4348; likely 88.4-90.2%) |
| Not judged (the answer key cannot place a row the value includes) | 270 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 92.0% (4710 of 5120; likely 91.2-92.7%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3945 of 4141; likely 94.6-95.9%) |
| structure | 73.1% (457 of 625; likely 69.5-76.4%) |
| model | 90.5% (296 of 327; likely 86.9-93.2%) |
| fuzzy | 66.7% (12 of 18; likely 43.7-83.7%) |
| none | 0.0% (0 of 9; likely 0.0-29.9%) |

Wrong values by kind: value 243, scale 13, sign 10, period 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 25
- dividends_paid missing_silent: 16
- buybacks missing_silent: 16
- debt_repaid missing_silent: 15
- other_opex wrong_review: 15
- debt_issued missing_silent: 12
- stock_issued missing_silent: 11
- eps_basic wrong_review: 10
- eps_diluted wrong_review: 9
- other_noncurrent_liabilities wrong_review: 8
- other_current_assets wrong_review: 8
- sga missing_silent: 7
- ppe_net wrong_review: 7
- other_current_liabilities wrong_review: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- cf_commercial_paper_net wrong_auto: 5
- income_tax missing_silent: 5
- total_equity wrong_review: 5
- other_noncurrent_liabilities wrong_auto: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- cf_working_capital wrong_review: 5
