# Evaluation: stmt-holdout-d61

30 documents (0 crashed), profile us-commercial 2026.10.24-1+6326bff395cd, 88.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 81.8% (3249 of 3972; likely 80.6-83.0%) |
| **Silent error rate** (wrong, of values with no review item) | 0.6% (5 of 825; likely 0.3-1.4%) |
| Silent omissions (missing and nothing flagged) | 1.7% (67 of 3972; likely 1.3-2.1%) |
| Values sent to review | 75.9% (2594 of 3419; likely 74.4-77.3%) |
| Wrong values caught by review | 97.1% (165 of 170; likely 93.3-98.7%) |
| Right values sent to review anyway | 74.8% (2429 of 3249; likely 73.2-76.2%) |
| Answer-key values present in the spread | 86.1% (3419 of 3972; likely 85.0-87.1%) |
| Not judged (the answer key cannot place a row the value includes) | 170 values |
| Open review items per document (reviewer workload) | median 32, mean 29.4; blockers median 4 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.9% (5985 of 6730; likely 88.2-89.7%) |
| Value read right | 99.6% (5961 of 5985; likely 99.4-99.7%) |
| Period right | 95.7% (5727 of 5985; likely 95.1-96.2%) |
| Template line right (where the key can judge) | 86.5% (3893 of 4501; likely 85.5-87.5%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3526 of 3664; likely 95.6-96.8%) |
| structure | 69.1% (349 of 505; likely 64.9-73.0%) |
| none | 0.0% (0 of 314; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 168, sign 1, scale 1

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 34
- other_noncurrent_liabilities wrong_review: 24
- other_opex wrong_review: 16
- cf_working_capital missing_silent: 16
- eps_basic missing_silent: 15
- eps_diluted missing_silent: 15
- other_nonoperating wrong_review: 14
- accrued_liabilities wrong_review: 12
- other_current_assets wrong_review: 11
- deferred_revenue_current wrong_review: 10
- revenue wrong_review: 6
- receivables wrong_review: 5
- deferred_tax_assets wrong_review: 4
- total_equity_parent wrong_review: 4
- total_equity wrong_review: 4
- common_stock_apic wrong_review: 4
- st_debt wrong_review: 4
- discontinued_ops missing_silent: 4
- other_current_liabilities wrong_review: 4
- cogs wrong_review: 3
- cf_net_income missing_silent: 3
- nci_net_income missing_silent: 3
- net_income_parent wrong_auto: 3
- st_debt wrong_auto: 2
- other_noncurrent_assets wrong_review: 2

Provenance: 2026-11-01T21:50:41+00:00, commit 25949c79377c with uncommitted changes; datasets: sec-holdout 40a19fa8c6f786c4; configuration: profile us-commercial 2026.10.24-1+6326bff395cd.
