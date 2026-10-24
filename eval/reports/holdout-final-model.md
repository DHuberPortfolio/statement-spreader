# Evaluation: holdout-final-model

30 documents (1 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 143.3 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 75.0% (2870 of 3827; likely 73.6-76.3%) |
| **Silent error rate** (wrong, of values with no review item) | 2.9% (61 of 2086; likely 2.3-3.7%) |
| Silent omissions (missing and nothing flagged) | 4.1% (157 of 3827; likely 3.5-4.8%) |
| Values sent to review | 37.3% (1243 of 3329; likely 35.7-39.0%) |
| Wrong values caught by review | 86.7% (398 of 459; likely 83.3-89.5%) |
| Right values sent to review anyway | 29.4% (845 of 2870; likely 27.8-31.1%) |
| Answer-key values present in the spread | 87.0% (3329 of 3827; likely 85.9-88.0%) |
| Not judged (the answer key cannot place a row the value includes) | 219 values |
| Open review items per document (reviewer workload) | median 25, mean 25.0; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.2% (5824 of 6526; likely 88.5-90.0%) |
| Value read right | 95.1% (5537 of 5824; likely 94.5-95.6%) |
| Period right | 92.8% (5402 of 5824; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 91.7% (4015 of 4377; likely 90.9-92.5%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3439 of 3574; likely 95.5-96.8%) |
| structure | 66.7% (321 of 481; likely 62.4-70.8%) |
| model | 80.1% (237 of 296; likely 75.1-84.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |
| none | 0.0% (0 of 8; likely 0.0-32.4%) |

Wrong values by kind: value 254, scale 140, period 58, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 33
- other_opex wrong_review: 22
- other_noncurrent_liabilities wrong_review: 20
- cf_working_capital wrong_review: 17
- other_nonoperating wrong_review: 13
- net_income wrong_review: 12
- other_current_assets wrong_review: 10
- deferred_revenue_current wrong_review: 10
- net_income_parent wrong_review: 9
- income_tax wrong_review: 9
- cash_end wrong_review: 9
- st_debt wrong_review: 8
- interest_expense wrong_review: 8
- pretax_income missing_silent: 8
- net_change_cash wrong_review: 8
- other_current_liabilities wrong_review: 8
- cash_end missing_silent: 7
- dividends_paid wrong_review: 7
- revenue wrong_review: 7
- sga wrong_review: 7
- shares_basic wrong_review: 7
- shares_diluted wrong_review: 7
- cf_deferred_tax wrong_review: 7
- pretax_income wrong_review: 7
- net_income_parent wrong_auto: 7
