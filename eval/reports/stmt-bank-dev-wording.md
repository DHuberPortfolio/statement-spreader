# Evaluation: stmt-bank-dev-wording

11 documents (1 crashed), profile us-bank 2026.10.25-bank-1+946b893ea4c8, 106.3 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 71.8% (737 of 1026; likely 69.0-74.5%) |
| **Silent error rate** (wrong, of values with no review item) | 4.8% (31 of 645; likely 3.4-6.7%) |
| Silent omissions (missing and nothing flagged) | 6.8% (70 of 1026; likely 5.4-8.5%) |
| Values sent to review | 26.2% (229 of 874; likely 23.4-29.2%) |
| Wrong values caught by review | 77.4% (106 of 137; likely 69.7-83.6%) |
| Right values sent to review anyway | 16.7% (123 of 737; likely 14.2-19.6%) |
| Answer-key values present in the spread | 85.2% (874 of 1026; likely 82.9-87.2%) |
| Not judged (the answer key cannot place a row the value includes) | 41 values |
| Open review items per document (reviewer workload) | median 17, mean 18.4; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.8% (2341 of 2607; likely 88.6-90.9%) |
| Value read right | 90.9% (2127 of 2341; likely 89.6-92.0%) |
| Period right | 98.5% (2305 of 2341; likely 97.9-98.9%) |
| Template line right (where the key can judge) | 82.3% (932 of 1132; likely 80.0-84.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.3% (932 of 968; likely 94.9-97.3%) |
| none | 0.0% (0 of 125; likely 0.0-3.0%) |
| structure | 0.0% (0 of 39; likely 0.0-9.0%) |

Wrong values by kind: scale 97, value 40

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 6
- shares_basic wrong_review: 6
- cf_other_financing wrong_review: 6
- bank_securities wrong_auto: 4
- other_current_liabilities missing_silent: 4
- cf_sbc missing_silent: 4
- total_equity_parent missing_silent: 4
- cash wrong_review: 4
- intangibles missing_silent: 4
- bank_interest_income missing_silent: 3
- bank_interest_expense missing_silent: 3
- revenue missing_silent: 3
- other_opex missing_silent: 3
- eps_basic missing_silent: 3
- eps_diluted missing_silent: 3
- cf_dna wrong_review: 3
- cf_deposits_net missing_silent: 3
- debt_issued missing_silent: 3
- debt_repaid missing_silent: 3
- cf_other_financing missing_silent: 3
- stock_issued missing_silent: 3
- cf_commercial_paper_net missing_silent: 3
- bank_interest_income wrong_review: 3
- bank_interest_expense wrong_review: 3
- net_interest_income wrong_review: 3

Provenance: 2026-10-25T23:08:32+00:00, commit 2c305ad5495d with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-1+946b893ea4c8.
