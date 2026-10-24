# Evaluation: dev-model-catchall

33 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 210.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 85.6% (3659 of 4274; likely 84.5-86.6%) |
| **Silent error rate** (wrong, of values with no review item) | 2.4% (59 of 2457; likely 1.9-3.1%) |
| Silent omissions (missing and nothing flagged) | 2.8% (121 of 4274; likely 2.4-3.4%) |
| Values sent to review | 37.4% (1466 of 3923; likely 35.9-38.9%) |
| Wrong values caught by review | 77.7% (205 of 264; likely 72.3-82.3%) |
| Right values sent to review anyway | 34.5% (1261 of 3659; likely 32.9-36.0%) |
| Answer-key values present in the spread | 91.8% (3923 of 4274; likely 90.9-92.6%) |
| Not judged (the answer key cannot place a row the value includes) | 338 values |
| Open review items per document (reviewer workload) | median 26, mean 27.1; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 93.4% (6454 of 6912; likely 92.8-93.9%) |
| Template line right (where the key can judge) | 93.1% (4784 of 5138; likely 92.4-93.8%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3975 of 4174; likely 94.5-95.8%) |
| model | 82.1% (391 of 476; likely 78.4-85.3%) |
| structure | 87.6% (409 of 467; likely 84.3-90.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |
| none | 0.0% (0 of 6; likely 0.0-39.0%) |

Wrong values by kind: value 239, scale 12, sign 10, period 3

Most frequent problems (line, outcome):

- cf_sbc wrong_review: 27
- other_nonoperating wrong_review: 16
- cf_other_financing wrong_review: 14
- other_opex wrong_review: 11
- eps_basic wrong_review: 10
- cf_other_financing wrong_auto: 10
- eps_diluted wrong_review: 9
- buybacks wrong_review: 8
- net_income_parent wrong_review: 7
- ppe_net wrong_review: 7
- other_noncurrent_liabilities wrong_review: 6
- debt_repaid wrong_review: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- total_equity_parent missing_silent: 6
- total_equity wrong_auto: 6
- cf_commercial_paper_net wrong_auto: 5
- other_noncurrent_liabilities wrong_auto: 5
- income_tax missing_silent: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
