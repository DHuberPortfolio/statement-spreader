# Evaluation: stmt-insurer-dev-d57

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+173a892793fc, 117.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 64.2% (720 of 1121; likely 61.4-67.0%) |
| **Silent error rate** (wrong, of values with no review item) | 3.0% (20 of 666; likely 2.0-4.6%) |
| Silent omissions (missing and nothing flagged) | 7.9% (89 of 1121; likely 6.5-9.7%) |
| Values sent to review | 28.9% (271 of 937; likely 26.1-31.9%) |
| Wrong values caught by review | 90.8% (197 of 217; likely 86.2-94.0%) |
| Right values sent to review anyway | 10.3% (74 of 720; likely 8.3-12.7%) |
| Answer-key values present in the spread | 83.6% (937 of 1121; likely 81.3-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 44 values |
| Open review items per document (reviewer workload) | median 25, mean 24.4; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 87.9% (2415 of 2749; likely 86.6-89.0%) |
| Value read right | 84.5% (2040 of 2415; likely 83.0-85.9%) |
| Period right | 98.1% (2370 of 2415; likely 97.5-98.6%) |
| Template line right (where the key can judge) | 81.6% (992 of 1216; likely 79.3-83.7%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (950 of 997; likely 93.8-96.4%) |
| none | 0.0% (0 of 119; likely 0.0-3.1%) |
| structure | 40.2% (39 of 97; likely 31.0-50.2%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 147, value 70

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 17
- net_income_parent wrong_review: 12
- cf_working_capital missing_silent: 12
- revenue wrong_review: 9
- total_equity_parent missing_silent: 7
- pretax_income wrong_review: 7
- other_opex wrong_review: 6
- deferred_tax_liabilities missing_silent: 6
- deferred_tax_assets missing_silent: 6
- cf_investments_net missing_silent: 6
- net_investment_income wrong_review: 6
- realized_investment_gains wrong_review: 6
- losses_lae wrong_review: 6
- acquisition_costs wrong_review: 6
- total_insurance_expenses wrong_review: 6
- net_income wrong_review: 6
- cf_net_income wrong_review: 6
- cf_dna wrong_review: 6
- cfo wrong_review: 6
- cf_investments_net wrong_review: 6
- capex wrong_review: 6
- cfi wrong_review: 6
- treasury_stock missing_silent: 4
- nci_equity missing_silent: 4
- shares_basic wrong_review: 4

Provenance: 2026-10-30T04:52:37+00:00, commit 8a7c63da413d with uncommitted changes; datasets: insurer-dev 156dc04bb1c32f07; configuration: profile us-insurer 2026.10.25-insurer-2+173a892793fc.
