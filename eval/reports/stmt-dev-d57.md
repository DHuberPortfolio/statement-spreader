# Evaluation: stmt-dev-d57

33 documents (0 crashed), profile us-commercial 2026.10.24-1+06c306f08a37, 91.4 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.1% (3629 of 4422; likely 80.9-83.2%) |
| **Silent error rate** (wrong, of values with no review item) | 2.0% (51 of 2548; likely 1.5-2.6%) |
| Silent omissions (missing and nothing flagged) | 2.3% (102 of 4422; likely 1.9-2.8%) |
| Values sent to review | 33.4% (1276 of 3824; likely 31.9-34.9%) |
| Wrong values caught by review | 73.8% (144 of 195; likely 67.3-79.5%) |
| Right values sent to review anyway | 31.2% (1132 of 3629; likely 29.7-32.7%) |
| Answer-key values present in the spread | 86.5% (3824 of 4422; likely 85.4-87.5%) |
| Not judged (the answer key cannot place a row the value includes) | 190 values |
| Open review items per document (reviewer workload) | median 24, mean 22.7; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 94.3% (6519 of 6912; likely 93.7-94.8%) |
| Template line right (where the key can judge) | 86.3% (4441 of 5144; likely 85.4-87.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3981 of 4180; likely 94.6-95.8%) |
| structure | 69.6% (451 of 648; likely 66.0-73.0%) |
| none | 0.0% (0 of 301; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 179, scale 13, sign 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 49
- other_nonoperating wrong_review: 15
- other_noncurrent_liabilities wrong_review: 10
- eps_basic missing_silent: 10
- eps_diluted missing_silent: 10
- other_nonoperating wrong_auto: 9
- cf_working_capital missing_silent: 9
- common_stock_apic wrong_auto: 8
- cf_investments_net wrong_review: 7
- other_current_assets wrong_review: 6
- other_opex wrong_review: 6
- cf_commercial_paper_net wrong_auto: 5
- operating_income missing_silent: 5
- cfo missing_silent: 5
- shares_basic wrong_review: 5
- total_costs missing_silent: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
- cf_net_income missing_silent: 4
- cf_investments_net missing_silent: 4
- net_change_cash missing_silent: 4
- ppe_net wrong_review: 4
- receivables wrong_review: 4
- shares_diluted wrong_auto: 4

Provenance: 2026-10-30T04:45:39+00:00, commit 8a7c63da413d with uncommitted changes; datasets: sec-dev 3cb0069d56fc398b; configuration: profile us-commercial 2026.10.24-1+06c306f08a37.
