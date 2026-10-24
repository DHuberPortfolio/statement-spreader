# Evaluation: holdout-model-catchall

30 documents (1 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 180.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 77.0% (2913 of 3784; likely 75.6-78.3%) |
| **Silent error rate** (wrong, of values with no review item) | 3.7% (78 of 2081; likely 3.0-4.7%) |
| Silent omissions (missing and nothing flagged) | 3.6% (138 of 3784; likely 3.1-4.3%) |
| Values sent to review | 38.0% (1276 of 3357; likely 36.4-39.7%) |
| Wrong values caught by review | 82.4% (366 of 444; likely 78.6-85.7%) |
| Right values sent to review anyway | 31.2% (910 of 2913; likely 29.6-32.9%) |
| Answer-key values present in the spread | 88.7% (3357 of 3784; likely 87.7-89.7%) |
| Not judged (the answer key cannot place a row the value includes) | 262 values |
| Open review items per document (reviewer workload) | median 24, mean 24.7; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.2% (5824 of 6526; likely 88.5-90.0%) |
| Value read right | 95.1% (5537 of 5824; likely 94.5-95.6%) |
| Period right | 92.8% (5402 of 5824; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 93.5% (4093 of 4377; likely 92.7-94.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3439 of 3574; likely 95.5-96.8%) |
| model | 77.4% (342 of 442; likely 73.2-81.0%) |
| structure | 87.8% (294 of 335; likely 83.8-90.8%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |
| none | 0.0% (0 of 8; likely 0.0-32.4%) |

Wrong values by kind: value 244, scale 136, period 57, sign 7

Most frequent problems (line, outcome):

- other_noncurrent_liabilities wrong_review: 20
- cf_sbc wrong_review: 20
- cf_other_financing wrong_auto: 17
- cf_working_capital wrong_review: 17
- other_opex wrong_review: 16
- other_nonoperating wrong_review: 13
- deferred_revenue_current wrong_review: 10
- net_income wrong_review: 10
- net_income_parent wrong_review: 9
- cash_end wrong_review: 9
- interest_expense wrong_review: 8
- pretax_income wrong_review: 8
- net_change_cash wrong_review: 8
- buybacks wrong_review: 7
- cash_end missing_silent: 7
- revenue wrong_review: 7
- sga wrong_review: 7
- income_tax wrong_review: 7
- shares_basic wrong_review: 7
- shares_diluted wrong_review: 7
- cf_deferred_tax wrong_review: 7
- cogs wrong_review: 7
- eps_diluted wrong_review: 7
- accrued_liabilities wrong_review: 6
- common_stock_apic wrong_review: 6
