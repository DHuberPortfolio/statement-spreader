# Evaluation: stmt-bank-holdout-d58

10 documents (0 crashed), profile us-bank 2026.10.25-bank-2+2f82c64be98d, 333.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 71.0% (856 of 1206; likely 68.4-73.5%) |
| **Silent error rate** (wrong, of values with no review item) | 4.4% (35 of 799; likely 3.2-6.0%) |
| Silent omissions (missing and nothing flagged) | 14.4% (174 of 1206; likely 12.6-16.5%) |
| Values sent to review | 14.4% (134 of 933; likely 12.3-16.8%) |
| Wrong values caught by review | 54.5% (42 of 77; likely 43.5-65.2%) |
| Right values sent to review anyway | 10.7% (92 of 856; likely 8.8-13.0%) |
| Answer-key values present in the spread | 77.4% (933 of 1206; likely 74.9-79.6%) |
| Not judged (the answer key cannot place a row the value includes) | 44 values |
| Open review items per document (reviewer workload) | median 28, mean 24.4; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 86.2% (2624 of 3043; likely 85.0-87.4%) |
| Value read right | 99.5% (2611 of 2624; likely 99.2-99.7%) |
| Period right | 98.6% (2588 of 2624; likely 98.1-99.0%) |
| Template line right (where the key can judge) | 79.1% (964 of 1218; likely 76.8-81.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 94.6% (956 of 1011; likely 93.0-95.8%) |
| none | 0.0% (0 of 142; likely 0.0-2.6%) |
| structure | 3.6% (2 of 56; likely 1.0-12.1%) |
| fuzzy | 66.7% (6 of 9; likely 35.4-87.9%) |

Wrong values by kind: value 71, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 14
- cf_other_financing wrong_review: 11
- cf_investments_net missing_silent: 8
- deposits missing_silent: 6
- lt_debt missing_silent: 6
- treasury_stock missing_silent: 6
- other_nonoperating missing_silent: 6
- eps_basic missing_silent: 6
- cf_investments_net wrong_auto: 6
- loans_net missing_silent: 6
- st_investments wrong_auto: 6
- st_debt missing_silent: 4
- total_liabilities missing_silent: 4
- preferred_equity missing_silent: 4
- common_stock_apic missing_silent: 4
- retained_earnings missing_silent: 4
- aoci missing_silent: 4
- total_equity_parent missing_silent: 4
- total_equity missing_silent: 4
- common_stock_apic wrong_auto: 4
- loans_held_for_sale missing_silent: 4
- allowance_loan_losses missing_silent: 4
- other_current_liabilities missing_silent: 4
- cf_deposits_net missing_silent: 4
- cf_commercial_paper_net missing_silent: 4

Provenance: 2026-11-01T01:44:32+00:00, commit 5d00382fa480 with uncommitted changes; datasets: bank-holdout db44c0a14beaaf5a; configuration: profile us-bank 2026.10.25-bank-2+2f82c64be98d.
