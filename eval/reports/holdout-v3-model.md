# Evaluation: holdout-v3-model

30 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 305.4 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 75.3% (2956 of 3928; likely 73.9-76.6%) |
| **Silent error rate** (wrong, of values with no review item) | 3.2% (69 of 2145; likely 2.5-4.1%) |
| Silent omissions (missing and nothing flagged) | 5.5% (218 of 3928; likely 4.9-6.3%) |
| Values sent to review | 37.2% (1269 of 3414; likely 35.6-38.8%) |
| Wrong values caught by review | 84.9% (389 of 458; likely 81.4-87.9%) |
| Right values sent to review anyway | 29.8% (880 of 2956; likely 28.1-31.4%) |
| Answer-key values present in the spread | 86.9% (3414 of 3928; likely 85.8-87.9%) |
| Not judged (the answer key cannot place a row the value includes) | 226 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.0% (5925 of 6730; likely 87.2-88.8%) |
| Value read right | 96.0% (5687 of 5925; likely 95.5-96.5%) |
| Period right | 92.8% (5497 of 5925; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 91.6% (4109 of 4486; likely 90.7-92.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.3% (3508 of 3643; likely 95.6-96.9%) |
| structure | 66.3% (345 of 520; likely 62.2-70.3%) |
| model | 80.1% (238 of 297; likely 75.2-84.3%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |
| none | 0.0% (0 of 8; likely 0.0-32.4%) |

Wrong values by kind: value 289, scale 104, period 58, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 33
- other_nonoperating wrong_review: 21
- other_noncurrent_liabilities wrong_review: 20
- other_opex wrong_review: 19
- buybacks missing_silent: 19
- cf_working_capital wrong_review: 17
- other_current_assets wrong_review: 12
- other_nonoperating wrong_auto: 12
- deferred_revenue_current wrong_review: 10
- income_tax wrong_review: 10
- dna_opex missing_silent: 9
- debt_issued missing_silent: 9
- sga missing_silent: 9
- cash_end wrong_review: 9
- stock_issued missing_silent: 8
- net_income wrong_review: 8
- nci_net_income wrong_review: 8
- st_debt wrong_review: 8
- net_change_cash wrong_review: 8
- dividends_paid missing_silent: 8
- other_nonoperating missing_silent: 8
- other_current_liabilities wrong_review: 8
- cash_end missing_silent: 7
- interest_expense wrong_review: 7
- income_tax missing_silent: 7
