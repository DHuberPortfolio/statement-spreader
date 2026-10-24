# Evaluation: holdout-v2

30 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 111.7 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 73.3% (2924 of 3991; likely 71.9-74.6%) |
| **Silent error rate** (wrong, of values with no review item) | 3.4% (73 of 2116; likely 2.8-4.3%) |
| Silent omissions (missing and nothing flagged) | 5.9% (237 of 3991; likely 5.2-6.7%) |
| Values sent to review | 36.2% (1202 of 3318; likely 34.6-37.9%) |
| Wrong values caught by review | 81.5% (321 of 394; likely 77.3-85.0%) |
| Right values sent to review anyway | 30.1% (881 of 2924; likely 28.5-31.8%) |
| Answer-key values present in the spread | 83.1% (3318 of 3991; likely 81.9-84.3%) |
| Not judged (the answer key cannot place a row the value includes) | 163 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.0% (5925 of 6730; likely 87.2-88.8%) |
| Value read right | 96.0% (5687 of 5925; likely 95.5-96.5%) |
| Period right | 92.8% (5497 of 5925; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 86.6% (3885 of 4486; likely 85.6-87.6%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.3% (3508 of 3643; likely 95.6-96.9%) |
| structure | 72.6% (357 of 492; likely 68.5-76.3%) |
| none | 0.0% (0 of 331; likely 0.0-1.1%) |
| fuzzy | 100.0% (20 of 20; likely 83.9-100.0%) |

Wrong values by kind: value 223, scale 108, period 56, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 33
- other_nonoperating wrong_review: 24
- other_noncurrent_liabilities wrong_review: 22
- buybacks missing_silent: 21
- other_opex wrong_review: 19
- cf_working_capital missing_silent: 16
- other_current_assets wrong_review: 14
- deferred_revenue_current wrong_review: 10
- income_tax wrong_review: 10
- dna_opex missing_silent: 9
- other_nonoperating wrong_auto: 9
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
