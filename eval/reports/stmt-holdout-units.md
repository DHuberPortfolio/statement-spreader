# Evaluation: stmt-holdout-units

30 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 115.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 81.6% (3241 of 3972; likely 80.4-82.8%) |
| **Silent error rate** (wrong, of values with no review item) | 1.5% (32 of 2154; likely 1.1-2.1%) |
| Silent omissions (missing and nothing flagged) | 2.1% (83 of 3972; likely 1.7-2.6%) |
| Values sent to review | 37.0% (1263 of 3417; likely 35.4-38.6%) |
| Wrong values caught by review | 81.8% (144 of 176; likely 75.5-86.8%) |
| Right values sent to review anyway | 34.5% (1119 of 3241; likely 32.9-36.2%) |
| Answer-key values present in the spread | 86.0% (3417 of 3972; likely 84.9-87.1%) |
| Not judged (the answer key cannot place a row the value includes) | 170 values |
| Open review items per document (reviewer workload) | median 24, mean 23.0; blockers median 5 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 88.9% (5985 of 6730; likely 88.2-89.7%) |
| Value read right | 99.6% (5961 of 5985; likely 99.4-99.7%) |
| Period right | 95.7% (5727 of 5985; likely 95.1-96.2%) |
| Template line right (where the key can judge) | 86.4% (3889 of 4501; likely 85.4-87.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.2% (3526 of 3664; likely 95.6-96.8%) |
| structure | 68.3% (345 of 505; likely 64.1-72.2%) |
| none | 0.0% (0 of 314; likely 0.0-1.2%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 168, sign 7, scale 1

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 34
- other_noncurrent_liabilities wrong_review: 22
- other_opex wrong_review: 19
- cf_working_capital missing_silent: 16
- eps_basic missing_silent: 15
- eps_diluted missing_silent: 15
- other_current_assets wrong_review: 10
- deferred_revenue_current wrong_review: 10
- other_nonoperating wrong_review: 9
- accrued_liabilities wrong_review: 8
- cash_end missing_silent: 6
- revenue wrong_review: 6
- total_costs missing_silent: 6
- receivables wrong_review: 5
- other_nonoperating wrong_auto: 5
- deferred_tax_assets wrong_review: 4
- common_stock_apic wrong_auto: 4
- total_equity_parent missing_silent: 4
- st_debt wrong_review: 4
- discontinued_ops missing_silent: 4
- accrued_liabilities wrong_auto: 4
- other_current_liabilities wrong_review: 4
- cogs wrong_auto: 3
- income_tax wrong_auto: 3
- cf_net_income missing_silent: 3

Provenance: 2026-10-25T22:58:39+00:00, commit feb91439b87a with uncommitted changes; datasets: sec-holdout 8e7f8dff07628aa1; configuration: profile us-commercial 2026.10.24-1+0ad0af213be8.
