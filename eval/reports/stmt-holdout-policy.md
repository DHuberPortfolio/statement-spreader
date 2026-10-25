# Evaluation: stmt-holdout-policy

30 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 140.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 74.1% (2948 of 3978; likely 72.7-75.4%) |
| **Silent error rate** (wrong, of values with no review item) | 2.3% (49 of 2101; likely 1.8-3.1%) |
| Silent omissions (missing and nothing flagged) | 3.8% (150 of 3978; likely 3.2-4.4%) |
| Values sent to review | 37.6% (1268 of 3369; likely 36.0-39.3%) |
| Wrong values caught by review | 88.4% (372 of 421; likely 84.9-91.1%) |
| Right values sent to review anyway | 30.4% (896 of 2948; likely 28.8-32.1%) |
| Answer-key values present in the spread | 84.7% (3369 of 3978; likely 83.5-85.8%) |
| Not judged (the answer key cannot place a row the value includes) | 164 values |
| Open review items per document (reviewer workload) | median 24, mean 23.3; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.9% (5985 of 6730; likely 88.2-89.7%) |
| Value read right | 95.2% (5698 of 5985; likely 94.6-95.7%) |
| Period right | 92.8% (5557 of 5985; likely 92.2-93.5%) |
| Template line right (where the key can judge) | 86.4% (3889 of 4501; likely 85.4-87.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3526 of 3664; likely 95.6-96.8%) |
| structure | 68.3% (345 of 505; likely 64.1-72.2%) |
| none | 0.0% (0 of 314; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 170, scale 140, period 104, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 35
- other_noncurrent_liabilities wrong_review: 22
- other_opex wrong_review: 22
- cf_working_capital missing_silent: 16
- eps_basic missing_silent: 14
- eps_diluted missing_silent: 14
- other_nonoperating wrong_review: 14
- other_current_assets wrong_review: 10
- deferred_revenue_current wrong_review: 10
- interest_expense wrong_review: 10
- revenue wrong_review: 9
- net_income wrong_review: 9
- net_income_parent wrong_review: 9
- shares_basic wrong_review: 9
- shares_diluted wrong_review: 9
- accrued_liabilities wrong_review: 8
- cash_end missing_silent: 8
- income_tax wrong_review: 8
- cash_end wrong_review: 8
- cf_dna wrong_review: 7
- cfo wrong_review: 7
- cfi wrong_review: 7
- net_change_cash wrong_review: 7
- pretax_income wrong_review: 7
- total_costs missing_silent: 6

Provenance: 2026-10-25T06:25:56+00:00, commit 63b9bb0c64d4 with uncommitted changes; datasets: sec-holdout 8e7f8dff07628aa1; configuration: profile us-commercial 2026.10.24-1+0ad0af213be8.
