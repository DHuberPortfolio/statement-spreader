# Evaluation: stmt-bank-holdout-merged

10 documents (0 crashed), profile us-bank 2026.10.25-bank-2+343c5cbc6927, 552.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 68.7% (831 of 1209; likely 66.1-71.3%) |
| **Silent error rate** (wrong, of values with no review item) | 5.9% (46 of 782; likely 4.4-7.8%) |
| Silent omissions (missing and nothing flagged) | 11.3% (137 of 1209; likely 9.7-13.2%) |
| Values sent to review | 17.0% (160 of 942; likely 14.7-19.5%) |
| Wrong values caught by review | 58.6% (65 of 111; likely 49.3-67.3%) |
| Right values sent to review anyway | 11.4% (95 of 831; likely 9.4-13.8%) |
| Answer-key values present in the spread | 77.9% (942 of 1209; likely 75.5-80.2%) |
| Not judged (the answer key cannot place a row the value includes) | 41 values |
| Open review items per document (reviewer workload) | median 27, mean 24.3; blockers median 2 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 80.4% (2447 of 3043; likely 79.0-81.8%) |
| Value read right | 99.5% (2434 of 2447; likely 99.1-99.7%) |
| Period right | 98.5% (2411 of 2447; likely 98.0-98.9%) |
| Template line right (where the key can judge) | 80.1% (925 of 1155; likely 77.7-82.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 94.6% (917 of 969; likely 93.0-95.9%) |
| none | 0.0% (0 of 121; likely 0.0-3.1%) |
| structure | 3.6% (2 of 56; likely 1.0-12.1%) |
| fuzzy | 66.7% (6 of 9; likely 35.4-87.9%) |

Wrong values by kind: value 105, scale 6

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 14
- cfi wrong_review: 9
- cf_investments_net wrong_auto: 9
- cf_working_capital missing_silent: 8
- deposits missing_silent: 6
- lt_debt missing_silent: 6
- treasury_stock missing_silent: 6
- other_nonoperating missing_silent: 6
- eps_basic missing_silent: 6
- loans_net missing_silent: 6
- cfo wrong_auto: 6
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
- intangibles missing_silent: 4

Provenance: 2026-10-26T03:48:04+00:00, commit 82c0f5da08a8; datasets: bank-holdout db44c0a14beaaf5a; configuration: profile us-bank 2026.10.25-bank-2+343c5cbc6927.
