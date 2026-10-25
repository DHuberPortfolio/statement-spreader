# Evaluation: stmt-insurer-dev-wording

10 documents (0 crashed), profile us-insurer 2026.10.25-insurer-1+294fc918d4b5, 189.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 57.2% (641 of 1121; likely 54.3-60.0%) |
| **Silent error rate** (wrong, of values with no review item) | 2.6% (15 of 568; likely 1.6-4.3%) |
| Silent omissions (missing and nothing flagged) | 8.5% (95 of 1121; likely 7.0-10.3%) |
| Values sent to review | 38.8% (360 of 928; likely 35.7-42.0%) |
| Wrong values caught by review | 94.8% (272 of 287; likely 91.6-96.8%) |
| Right values sent to review anyway | 13.7% (88 of 641; likely 11.3-16.6%) |
| Answer-key values present in the spread | 82.8% (928 of 1121; likely 80.5-84.9%) |
| Not judged (the answer key cannot place a row the value includes) | 44 values |
| Open review items per document (reviewer workload) | median 25, mean 25.5; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 83.6% (2298 of 2749; likely 82.2-84.9%) |
| Value read right | 77.4% (1778 of 2298; likely 75.6-79.0%) |
| Period right | 98.0% (2253 of 2298; likely 97.4-98.5%) |
| Template line right (where the key can judge) | 81.4% (968 of 1189; likely 79.1-83.5%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (926 of 973; likely 93.6-96.3%) |
| none | 0.0% (0 of 116; likely 0.0-3.2%) |
| structure | 40.2% (39 of 97; likely 31.0-50.2%) |
| fuzzy | 100.0% (3 of 3; likely 43.8-100.0%) |

Wrong values by kind: scale 205, value 82

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 17
- revenue wrong_review: 12
- net_income_parent wrong_review: 12
- losses_lae wrong_review: 9
- total_insurance_expenses wrong_review: 9
- net_income wrong_review: 9
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
- interest_expense wrong_review: 6
- total_equity wrong_review: 6
- deferred_tax_liabilities missing_silent: 6
- eps_basic missing_silent: 6
- eps_diluted missing_silent: 6
- deferred_tax_assets missing_silent: 6
- cf_investments_net missing_silent: 6

Provenance: 2026-10-25T23:11:56+00:00, commit 2c305ad5495d with uncommitted changes; datasets: insurer-dev 081b20ffb7a0eac6; configuration: profile us-insurer 2026.10.25-insurer-1+294fc918d4b5.
