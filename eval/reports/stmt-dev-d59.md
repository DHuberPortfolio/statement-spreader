# Evaluation: stmt-dev-d59

33 documents (0 crashed), profile us-commercial 2026.10.24-1+6326bff395cd, 124.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.9% (3664 of 4422; likely 81.7-83.9%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 329; likely 0.0-1.2%) |
| Silent omissions (missing and nothing flagged) | 1.8% (78 of 4422; likely 1.4-2.2%) |
| Values sent to review | 91.5% (3530 of 3859; likely 90.6-92.3%) |
| Wrong values caught by review | 100.0% (195 of 195; likely 98.1-100.0%) |
| Right values sent to review anyway | 91.0% (3335 of 3664; likely 90.1-91.9%) |
| Answer-key values present in the spread | 87.3% (3859 of 4422; likely 86.3-88.2%) |
| Not judged (the answer key cannot place a row the value includes) | 190 values |
| Open review items per document (reviewer workload) | median 31, mean 30.0; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 94.3% (6519 of 6912; likely 93.7-94.8%) |
| Template line right (where the key can judge) | 87.1% (4478 of 5144; likely 86.1-87.9%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (4004 of 4203; likely 94.6-95.9%) |
| structure | 74.0% (465 of 628; likely 70.5-77.3%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 179, scale 13, sign 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 49
- other_nonoperating wrong_review: 24
- other_noncurrent_liabilities wrong_review: 13
- eps_basic missing_silent: 10
- eps_diluted missing_silent: 10
- cf_working_capital missing_silent: 9
- cf_investments_net wrong_review: 8
- common_stock_apic wrong_review: 8
- total_equity wrong_review: 7
- accrued_liabilities wrong_review: 6
- other_current_assets wrong_review: 6
- shares_basic wrong_review: 6
- shares_diluted wrong_review: 6
- other_opex wrong_review: 6
- cf_commercial_paper_net wrong_review: 5
- total_costs missing_silent: 5
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
- cf_net_income missing_silent: 4
- cf_investments_net missing_silent: 4
- ppe_net wrong_review: 4
- receivables wrong_review: 4
- debt_issued missing_silent: 4
- debt_repaid missing_silent: 4
- total_equity_parent wrong_review: 4

Provenance: 2026-11-01T07:36:59+00:00, commit 703c153052a8 with uncommitted changes; datasets: sec-dev 3cb0069d56fc398b; configuration: profile us-commercial 2026.10.24-1+6326bff395cd.
