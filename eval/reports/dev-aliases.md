# Evaluation: dev-aliases

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 150.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 79.4% (3523 of 4439; likely 78.1-80.5%) |
| **Silent error rate** (wrong, of values with no review item) | 2.9% (72 of 2519; likely 2.3-3.6%) |
| Silent omissions (missing and nothing flagged) | 4.6% (205 of 4439; likely 4.0-5.3%) |
| Values sent to review | 32.9% (1235 of 3754; likely 31.4-34.4%) |
| Wrong values caught by review | 68.8% (159 of 231; likely 62.6-74.5%) |
| Right values sent to review anyway | 30.5% (1076 of 3523; likely 29.0-32.1%) |
| Answer-key values present in the spread | 84.6% (3754 of 4439; likely 83.5-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 179 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 86.2% (4414 of 5120; likely 85.2-87.1%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3945 of 4141; likely 94.6-95.9%) |
| structure | 73.1% (457 of 625; likely 69.5-76.4%) |
| none | 0.0% (0 of 336; likely 0.0-1.1%) |
| fuzzy | 66.7% (12 of 18; likely 43.7-83.7%) |

Wrong values by kind: value 206, scale 13, sign 10, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 19
- dividends_paid missing_silent: 17
- buybacks missing_silent: 16
- debt_repaid missing_silent: 15
- stock_issued missing_silent: 12
- debt_issued missing_silent: 12
- other_noncurrent_liabilities wrong_review: 10
- other_opex wrong_review: 10
- cf_working_capital missing_silent: 9
- other_nonoperating wrong_auto: 8
- other_current_assets wrong_review: 8
- common_stock_apic wrong_auto: 8
- cf_net_income missing_silent: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- cf_commercial_paper_net wrong_auto: 5
- net_income_parent wrong_auto: 5
- income_tax missing_silent: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- cf_working_capital wrong_review: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
