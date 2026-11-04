# Evaluation: stmt-dev-d66

33 documents (0 crashed), profile us-commercial 2026.11.04-1+b2166b77ced3, 236.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 86.4% (3812 of 4413; likely 85.3-87.4%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 1377; likely 0.0-0.3%) |
| Silent omissions (missing and nothing flagged) | 1.5% (64 of 4413; likely 1.1-1.8%) |
| Values sent to review | 65.6% (2631 of 4008; likely 64.2-67.1%) |
| Wrong values caught by review | 100.0% (196 of 196; likely 98.1-100.0%) |
| Right values sent to review anyway | 63.9% (2435 of 3812; likely 62.3-65.4%) |
| Answer-key values present in the spread | 90.8% (4008 of 4413; likely 89.9-91.6%) |
| Not judged (the answer key cannot place a row the value includes) | 199 values |
| Open review items per document (reviewer workload) | median 30, mean 28.9; blockers median 4 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.9% (6980 of 7675; likely 90.3-91.6%) |
| Value read right | 99.5% (6947 of 6980; likely 99.3-99.7%) |
| Period right | 94.4% (6587 of 6980; likely 93.8-94.9%) |
| Template line right (where the key can judge) | 89.0% (4628 of 5200; likely 88.1-89.8%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.7% (4172 of 4360; likely 95.0-96.3%) |
| structure | 76.4% (447 of 585; likely 72.8-79.7%) |
| none | 0.0% (0 of 240; likely 0.0-1.6%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 186, scale 7, sign 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 44
- other_nonoperating wrong_review: 24
- other_noncurrent_liabilities wrong_review: 12
- cf_investments_net wrong_review: 8
- common_stock_apic wrong_review: 8
- cf_working_capital wrong_review: 8
- total_equity wrong_review: 7
- cf_working_capital missing_silent: 7
- accrued_liabilities wrong_review: 6
- eps_basic wrong_review: 6
- buybacks wrong_review: 6
- other_current_assets wrong_review: 6
- other_opex wrong_review: 6
- eps_basic missing_silent: 6
- eps_diluted missing_silent: 6
- total_equity_parent wrong_review: 6
- shares_diluted wrong_review: 5
- total_costs missing_silent: 5
- shares_basic missing_silent: 4
- cf_net_income missing_silent: 4
- cf_investments_net missing_silent: 4
- receivables wrong_review: 4
- other_current_liabilities wrong_review: 4
- net_income_parent wrong_review: 4
- st_debt wrong_review: 4

Provenance: 2026-11-04T07:46:27+00:00, commit 22f07e2c3d97 with uncommitted changes; datasets: sec-dev 8b57b063772784de; configuration: profile us-commercial 2026.11.04-1+b2166b77ced3.
