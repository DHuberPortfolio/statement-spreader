# Evaluation: stmt-insurer-dev-before

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-1+95c74fe0affc, 212.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 53.7% (604 of 1124; likely 50.8-56.6%) |
| **Silent error rate** (wrong, of values with no review item) | 2.4% (13 of 532; likely 1.4-4.1%) |
| Silent omissions (missing and nothing flagged) | 11.2% (126 of 1124; likely 9.5-13.2%) |
| Values sent to review | 39.0% (340 of 872; likely 35.8-42.3%) |
| Wrong values caught by review | 95.1% (255 of 268; likely 91.9-97.1%) |
| Right values sent to review anyway | 14.1% (85 of 604; likely 11.5-17.1%) |
| Answer-key values present in the spread | 77.6% (872 of 1124; likely 75.1-79.9%) |
| Not judged (the answer key cannot place a row the value includes) | 41 values |
| Open review items per document (reviewer workload) | median 24, mean 25.0; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 83.6% (2298 of 2749; likely 82.2-84.9%) |
| Value read right | 77.4% (1778 of 2298; likely 75.6-79.0%) |
| Period right | 98.0% (2253 of 2298; likely 97.4-98.5%) |
| Template line right (where the key can judge) | 76.9% (914 of 1189; likely 74.4-79.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 94.9% (869 of 916; likely 93.2-96.1%) |
| structure | 30.2% (42 of 139; likely 23.2-38.3%) |
| none | 0.0% (0 of 131; likely 0.0-2.8%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 194, value 74

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 17
- net_income_parent wrong_review: 12
- revenue wrong_review: 9
- net_income wrong_review: 9
- realized_investment_gains missing_silent: 9
- cf_working_capital missing_silent: 9
- cf_net_income wrong_review: 9
- cfo wrong_review: 9
- cf_investments_net wrong_review: 9
- cfi wrong_review: 9
- income_tax wrong_review: 7
- shares_basic wrong_review: 7
- shares_diluted wrong_review: 7
- total_equity_parent missing_silent: 7
- pretax_income wrong_review: 7
- premiums_earned wrong_review: 6
- other_opex wrong_review: 6
- losses_lae wrong_review: 6
- interest_expense wrong_review: 6
- total_equity wrong_review: 6
- deferred_tax_liabilities missing_silent: 6
- losses_lae missing_silent: 6
- eps_basic missing_silent: 6
- eps_diluted missing_silent: 6
- deferred_tax_assets missing_silent: 6

Provenance: 2026-10-25T23:00:25+00:00, commit feb91439b87a with uncommitted changes; datasets: insurer-dev 081b20ffb7a0eac6; configuration: profile us-insurer 2026.10.25-insurer-1+95c74fe0affc.
