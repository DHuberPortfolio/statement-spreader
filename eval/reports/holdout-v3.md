# Evaluation: holdout-v3

30 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 121.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 73.4% (2931 of 3991; likely 72.0-74.8%) |
| **Silent error rate** (wrong, of values with no review item) | 3.6% (77 of 2144; likely 2.9-4.5%) |
| Silent omissions (missing and nothing flagged) | 5.9% (237 of 3991; likely 5.2-6.7%) |
| Values sent to review | 35.4% (1174 of 3318; likely 33.8-37.0%) |
| Wrong values caught by review | 80.1% (310 of 387; likely 75.8-83.8%) |
| Right values sent to review anyway | 29.5% (864 of 2931; likely 27.9-31.2%) |
| Answer-key values present in the spread | 83.1% (3318 of 3991; likely 81.9-84.3%) |
| Not judged (the answer key cannot place a row the value includes) | 163 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.0% (5925 of 6730; likely 87.2-88.8%) |
| Value read right | 96.0% (5687 of 5925; likely 95.5-96.5%) |
| Period right | 92.8% (5497 of 5925; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 86.3% (3871 of 4486; likely 85.3-87.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.3% (3508 of 3643; likely 95.6-96.9%) |
| structure | 66.3% (345 of 520; likely 62.2-70.3%) |
| none | 0.0% (0 of 305; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 217, scale 107, period 56, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 33
- other_noncurrent_liabilities wrong_review: 22
- other_nonoperating wrong_review: 21
- buybacks missing_silent: 21
- other_opex wrong_review: 19
- cf_working_capital missing_silent: 16
- other_nonoperating wrong_auto: 12
- other_current_assets wrong_review: 10
- deferred_revenue_current wrong_review: 10
- income_tax wrong_review: 10
- dna_opex missing_silent: 9
- debt_issued missing_silent: 9
- sga missing_silent: 9
- dividends_paid missing_silent: 9
- acquisitions missing_silent: 9
- accrued_liabilities wrong_review: 8
- stock_issued missing_silent: 8
- cash_end missing_silent: 8
- net_income wrong_review: 8
- cash_end wrong_review: 8
- interest_expense wrong_review: 7
- income_tax missing_silent: 7
- net_income_parent wrong_auto: 7
- cf_net_income missing_silent: 7
- revenue wrong_review: 6
