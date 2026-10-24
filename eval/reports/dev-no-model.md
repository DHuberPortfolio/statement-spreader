# Evaluation: dev-no-model

33 documents (0 crashed), profile us-commercial 2026.10.24-1+63421598f685, 142.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 75.1% (3372 of 4491; likely 73.8-76.3%) |
| **Silent error rate** (wrong, of values with no review item) | 3.9% (96 of 2451; likely 3.2-4.8%) |
| Silent omissions (missing and nothing flagged) | 5.7% (255 of 4491; likely 5.0-6.4%) |
| Values sent to review | 33.1% (1213 of 3664; likely 31.6-34.6%) |
| Wrong values caught by review | 67.1% (196 of 292; likely 61.5-72.3%) |
| Right values sent to review anyway | 30.2% (1017 of 3372; likely 28.6-31.7%) |
| Answer-key values present in the spread | 81.6% (3664 of 4491; likely 80.4-82.7%) |
| Not judged (the answer key cannot place a row the value includes) | 127 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 82.5% (4223 of 5120; likely 81.4-83.5%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.4% (3752 of 3932; likely 94.7-96.0%) |
| structure | 56.0% (459 of 819; likely 52.6-59.4%) |
| none | 0.0% (0 of 351; likely 0.0-1.1%) |
| fuzzy | 66.7% (12 of 18; likely 43.7-83.7%) |

Wrong values by kind: value 270, scale 13, sign 7, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 68
- cf_investments_net wrong_auto: 23
- cf_commercial_paper_net missing_silent: 23
- debt_repaid missing_silent: 21
- cfi missing_silent: 20
- other_nonoperating wrong_review: 19
- dividends_paid missing_silent: 17
- other_opex wrong_review: 16
- debt_issued missing_silent: 15
- other_current_assets wrong_review: 14
- buybacks missing_silent: 13
- stock_issued missing_silent: 12
- other_noncurrent_liabilities wrong_review: 10
- cf_investments_net missing_silent: 9
- accrued_liabilities wrong_review: 8
- other_nonoperating wrong_auto: 8
- common_stock_apic wrong_auto: 8
- cf_working_capital wrong_review: 7
- cf_net_income missing_silent: 6
- cf_working_capital missing_silent: 6
- cfo missing_silent: 6
- fx_effect missing_silent: 6
- net_change_cash missing_silent: 6
- cf_investments_net wrong_review: 5
- net_income_parent wrong_auto: 5
