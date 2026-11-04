# Evaluation: stmt-insurer-dev-d62

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+a7704928c034, 121.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 64.7% (725 of 1121; likely 61.8-67.4%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 188; likely 0.0-2.0%) |
| Silent omissions (missing and nothing flagged) | 7.3% (82 of 1121; likely 5.9-9.0%) |
| Values sent to review | 80.0% (754 of 942; likely 77.4-82.5%) |
| Wrong values caught by review | 100.0% (217 of 217; likely 98.3-100.0%) |
| Right values sent to review anyway | 74.1% (537 of 725; likely 70.8-77.1%) |
| Answer-key values present in the spread | 84.0% (942 of 1121; likely 81.8-86.1%) |
| Not judged (the answer key cannot place a row the value includes) | 44 values |
| Open review items per document (reviewer workload) | median 32, mean 31.4; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 87.9% (2415 of 2749; likely 86.6-89.0%) |
| Value read right | 84.5% (2040 of 2415; likely 83.0-85.9%) |
| Period right | 98.1% (2370 of 2415; likely 97.5-98.6%) |
| Template line right (where the key can judge) | 82.0% (997 of 1216; likely 79.7-84.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (950 of 997; likely 93.8-96.4%) |
| none | 0.0% (0 of 119; likely 0.0-3.1%) |
| structure | 45.4% (44 of 97; likely 35.8-55.3%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 147, value 70

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 17
- net_income_parent wrong_review: 12
- cf_working_capital missing_silent: 12
- revenue wrong_review: 10
- losses_lae wrong_review: 9
- net_investment_income wrong_review: 7
- realized_investment_gains wrong_review: 7
- total_insurance_expenses wrong_review: 7
- pretax_income wrong_review: 7
- other_opex wrong_review: 6
- shares_basic wrong_review: 6
- shares_diluted wrong_review: 6
- deferred_tax_liabilities missing_silent: 6
- deferred_tax_assets missing_silent: 6
- cf_investments_net missing_silent: 6
- acquisition_costs wrong_review: 6
- net_income wrong_review: 6
- cf_net_income wrong_review: 6
- cf_dna wrong_review: 6
- cfo wrong_review: 6
- cf_investments_net wrong_review: 6
- capex wrong_review: 6
- cfi wrong_review: 6
- cf_working_capital wrong_review: 5
- common_stock_apic wrong_review: 4

Provenance: 2026-11-04T00:19:42+00:00, commit d0a978102d16 with uncommitted changes; datasets: insurer-dev 156dc04bb1c32f07; configuration: profile us-insurer 2026.10.25-insurer-2+a7704928c034.
