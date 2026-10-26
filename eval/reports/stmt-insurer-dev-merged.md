# Evaluation: stmt-insurer-dev-merged

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+413e86b955cb, 271.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 63.2% (708 of 1121; likely 60.3-65.9%) |
| **Silent error rate** (wrong, of values with no review item) | 3.1% (20 of 636; likely 2.0-4.8%) |
| Silent omissions (missing and nothing flagged) | 7.8% (87 of 1121; likely 6.3-9.5%) |
| Values sent to review | 32.1% (301 of 937; likely 29.2-35.2%) |
| Wrong values caught by review | 91.3% (209 of 229; likely 86.9-94.3%) |
| Right values sent to review anyway | 13.0% (92 of 708; likely 10.7-15.7%) |
| Answer-key values present in the spread | 83.6% (937 of 1121; likely 81.3-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 44 values |
| Open review items per document (reviewer workload) | median 25, mean 24.9; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 83.6% (2298 of 2749; likely 82.2-84.9%) |
| Value read right | 83.7% (1923 of 2298; likely 82.1-85.1%) |
| Period right | 98.0% (2253 of 2298; likely 97.4-98.5%) |
| Template line right (where the key can judge) | 82.2% (977 of 1189; likely 79.9-84.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (935 of 982; likely 93.7-96.4%) |
| none | 0.0% (0 of 110; likely 0.0-3.4%) |
| structure | 41.5% (39 of 94; likely 32.1-51.6%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 147, value 82

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 17
- net_income_parent wrong_review: 12
- cf_working_capital missing_silent: 10
- revenue wrong_review: 9
- cf_net_income wrong_review: 9
- cfo wrong_review: 9
- cf_investments_net wrong_review: 9
- cfi wrong_review: 9
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
- cf_dna wrong_review: 6
- capex wrong_review: 6
- treasury_stock missing_silent: 4
- nci_equity missing_silent: 4
- shares_basic wrong_review: 4

Provenance: 2026-10-26T03:52:43+00:00, commit 82c0f5da08a8; datasets: insurer-dev 081b20ffb7a0eac6; configuration: profile us-insurer 2026.10.25-insurer-2+413e86b955cb.
