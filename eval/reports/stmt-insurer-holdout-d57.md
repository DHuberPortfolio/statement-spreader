# Evaluation: stmt-insurer-holdout-d57

14 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+173a892793fc, 213.4 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 63.1% (924 of 1465; likely 60.6-65.5%) |
| **Silent error rate** (wrong, of values with no review item) | 6.2% (50 of 813; likely 4.7-8.0%) |
| Silent omissions (missing and nothing flagged) | 10.9% (160 of 1465; likely 9.4-12.6%) |
| Values sent to review | 21.4% (222 of 1035; likely 19.1-24.1%) |
| Wrong values caught by review | 55.0% (61 of 111; likely 45.7-63.9%) |
| Right values sent to review anyway | 17.4% (161 of 924; likely 15.1-20.0%) |
| Answer-key values present in the spread | 70.6% (1035 of 1465; likely 68.3-72.9%) |
| Not judged (the answer key cannot place a row the value includes) | 72 values |
| Open review items per document (reviewer workload) | median 23, mean 24.9; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 83.9% (3190 of 3800; likely 82.7-85.1%) |
| Value read right | 99.2% (3163 of 3190; likely 98.8-99.4%) |
| Period right | 97.7% (3118 of 3190; likely 97.2-98.2%) |
| Template line right (where the key can judge) | 69.4% (1078 of 1554; likely 67.0-71.6%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 93.7% (1051 of 1122; likely 92.1-95.0%) |
| none | 0.0% (0 of 260; likely 0.0-1.5%) |
| structure | 12.7% (21 of 166; likely 8.4-18.6%) |
| fuzzy | 100.0% (6 of 6; likely 61.0-100.0%) |

Wrong values by kind: value 101, scale 7, sign 3

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 21
- cf_other_financing wrong_review: 21
- common_stock_apic wrong_auto: 11
- other_opex wrong_review: 9
- eps_diluted missing_silent: 9
- cf_investments_net wrong_auto: 9
- net_income_parent wrong_review: 9
- debt_repaid wrong_auto: 8
- premiums_receivable missing_silent: 6
- total_insurance_expenses missing_silent: 6
- eps_basic missing_silent: 6
- deferred_tax_assets missing_silent: 6
- loss_reserves missing_silent: 6
- deferred_tax_liabilities missing_silent: 6
- cf_investments_net missing_silent: 5
- future_policy_benefits missing_silent: 4
- st_debt missing_silent: 4
- lt_debt missing_silent: 4
- total_liabilities missing_silent: 4
- common_stock_apic missing_silent: 4
- retained_earnings missing_silent: 4
- aoci missing_silent: 4
- total_equity_parent missing_silent: 4
- total_equity missing_silent: 4
- total_liabilities_equity missing_silent: 4

Provenance: 2026-10-30T04:56:11+00:00, commit 8a7c63da413d with uncommitted changes; datasets: insurer-holdout 6b26e428fa3f884a; configuration: profile us-insurer 2026.10.25-insurer-2+173a892793fc.
