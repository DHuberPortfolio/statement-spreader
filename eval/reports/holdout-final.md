# Evaluation: holdout-final

30 documents (1 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 133.3 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 73.5% (2858 of 3890; likely 72.1-74.8%) |
| **Silent error rate** (wrong, of values with no review item) | 3.3% (70 of 2100; likely 2.6-4.2%) |
| Silent omissions (missing and nothing flagged) | 6.2% (241 of 3890; likely 5.5-7.0%) |
| Values sent to review | 35.1% (1136 of 3236; likely 33.5-36.8%) |
| Wrong values caught by review | 81.5% (308 of 378; likely 77.3-85.1%) |
| Right values sent to review anyway | 29.0% (828 of 2858; likely 27.3-30.7%) |
| Answer-key values present in the spread | 83.2% (3236 of 3890; likely 82.0-84.3%) |
| Not judged (the answer key cannot place a row the value includes) | 156 values |
| Open review items per document (reviewer workload) | median 21, mean 20.7; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.2% (5824 of 6526; likely 88.5-90.0%) |
| Value read right | 95.1% (5537 of 5824; likely 94.5-95.6%) |
| Period right | 92.8% (5402 of 5824; likely 92.1-93.4%) |
| Template line right (where the key can judge) | 86.3% (3778 of 4377; likely 85.3-87.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3439 of 3574; likely 95.5-96.8%) |
| structure | 66.7% (321 of 481; likely 62.4-70.8%) |
| none | 0.0% (0 of 304; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 180, scale 135, period 56, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 33
- other_noncurrent_liabilities wrong_review: 22
- other_opex wrong_review: 22
- eps_basic missing_silent: 20
- eps_diluted missing_silent: 20
- cf_working_capital missing_silent: 16
- other_nonoperating wrong_review: 13
- deferred_revenue_current wrong_review: 10
- cash_end missing_silent: 10
- pretax_income missing_silent: 10
- revenue missing_silent: 10
- sga missing_silent: 10
- net_income_parent wrong_auto: 10
- net_income wrong_review: 9
- other_current_assets wrong_review: 8
- interest_expense wrong_review: 8
- cash_end wrong_review: 8
- income_tax missing_silent: 8
- shares_basic wrong_review: 7
- shares_diluted wrong_review: 7
- cogs missing_silent: 7
- dna_opex missing_silent: 7
- operating_income missing_silent: 7
- cf_net_income missing_silent: 7
- accrued_liabilities wrong_review: 6
