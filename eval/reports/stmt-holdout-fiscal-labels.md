# Evaluation: stmt-holdout-fiscal-labels

30 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 99.3 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 78.1% (3106 of 3978; likely 76.8-79.3%) |
| **Silent error rate** (wrong, of values with no review item) | 1.5% (32 of 2128; likely 1.1-2.1%) |
| Silent omissions (missing and nothing flagged) | 2.2% (89 of 3978; likely 1.8-2.7%) |
| Values sent to review | 37.8% (1295 of 3423; likely 36.2-39.5%) |
| Wrong values caught by review | 89.9% (285 of 317; likely 86.1-92.8%) |
| Right values sent to review anyway | 32.5% (1010 of 3106; likely 30.9-34.2%) |
| Answer-key values present in the spread | 86.0% (3423 of 3978; likely 84.9-87.1%) |
| Not judged (the answer key cannot place a row the value includes) | 164 values |
| Open review items per document (reviewer workload) | median 24, mean 23.1; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.9% (5985 of 6730; likely 88.2-89.7%) |
| Value read right | 95.2% (5698 of 5985; likely 94.6-95.7%) |
| Period right | 95.7% (5727 of 5985; likely 95.1-96.2%) |
| Template line right (where the key can judge) | 86.4% (3889 of 4501; likely 85.4-87.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3526 of 3664; likely 95.6-96.8%) |
| structure | 68.3% (345 of 505; likely 64.1-72.2%) |
| none | 0.0% (0 of 314; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 170, scale 140, sign 7

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 37
- other_noncurrent_liabilities wrong_review: 22
- other_opex wrong_review: 22
- cf_working_capital missing_silent: 16
- eps_basic missing_silent: 12
- eps_diluted missing_silent: 12
- other_nonoperating wrong_review: 12
- other_current_assets wrong_review: 10
- deferred_revenue_current wrong_review: 10
- accrued_liabilities wrong_review: 8
- cash_end missing_silent: 6
- revenue wrong_review: 6
- total_costs missing_silent: 6
- st_debt wrong_review: 6
- rnd wrong_review: 6
- interest_expense wrong_review: 6
- net_income wrong_review: 6
- net_income_parent wrong_review: 6
- shares_basic wrong_review: 6
- shares_diluted wrong_review: 6
- receivables wrong_review: 5
- income_tax wrong_review: 5
- other_nonoperating wrong_auto: 5
- deferred_tax_assets wrong_review: 4
- total_assets wrong_review: 4

Provenance: 2026-10-25T22:32:48+00:00, commit 03059c4da7a8 with uncommitted changes; datasets: sec-holdout 8e7f8dff07628aa1; configuration: profile us-commercial 2026.10.24-1+0ad0af213be8.
