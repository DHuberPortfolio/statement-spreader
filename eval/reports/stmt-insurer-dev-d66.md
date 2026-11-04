# Evaluation: stmt-insurer-dev-d66

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+d077afa34342, 311.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 66.9% (748 of 1118; likely 64.1-69.6%) |
| **Silent error rate** (wrong, of values with no review item) | 0.5% (1 of 193; likely 0.1-2.9%) |
| Silent omissions (missing and nothing flagged) | 4.3% (48 of 1118; likely 3.3-5.6%) |
| Values sent to review | 80.5% (799 of 992; likely 78.0-82.9%) |
| Wrong values caught by review | 99.6% (243 of 244; likely 97.7-99.9%) |
| Right values sent to review anyway | 74.3% (556 of 748; likely 71.1-77.3%) |
| Answer-key values present in the spread | 88.7% (992 of 1118; likely 86.7-90.5%) |
| Not judged (the answer key cannot place a row the value includes) | 47 values |
| Open review items per document (reviewer workload) | median 31, mean 31.7; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 85.1% (2340 of 2749; likely 83.7-86.4%) |
| Value read right | 82.2% (1924 of 2340; likely 80.6-83.7%) |
| Period right | 98.1% (2295 of 2340; likely 97.4-98.6%) |
| Template line right (where the key can judge) | 85.7% (1047 of 1221; likely 83.7-87.6%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 97.0% (1006 of 1037; likely 95.8-97.9%) |
| none | 0.0% (0 of 102; likely 0.0-3.6%) |
| structure | 48.1% (38 of 79; likely 37.4-58.9%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 185, value 59

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 13
- cf_other_financing wrong_review: 11
- revenue wrong_review: 10
- net_income_parent wrong_review: 9
- cf_investments_net missing_silent: 9
- losses_lae wrong_review: 9
- net_investment_income wrong_review: 7
- realized_investment_gains wrong_review: 7
- total_insurance_expenses wrong_review: 7
- pretax_income wrong_review: 7
- common_stock_apic wrong_review: 6
- other_opex wrong_review: 6
- shares_basic wrong_review: 6
- shares_diluted wrong_review: 6
- total_equity_parent wrong_review: 6
- total_equity wrong_review: 6
- acquisition_costs wrong_review: 6
- net_income wrong_review: 6
- cf_net_income wrong_review: 6
- cf_dna wrong_review: 6
- cfo wrong_review: 6
- cf_investments_net wrong_review: 6
- capex wrong_review: 6
- cfi wrong_review: 6
- cf_working_capital wrong_review: 5

Provenance: 2026-11-04T07:48:57+00:00, commit 22f07e2c3d97 with uncommitted changes; datasets: insurer-dev 156dc04bb1c32f07; configuration: profile us-insurer 2026.10.25-insurer-2+d077afa34342.
