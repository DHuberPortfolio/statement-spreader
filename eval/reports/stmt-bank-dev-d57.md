# Evaluation: stmt-bank-dev-d57

11 documents (1 crashed), profile us-bank 2026.10.25-bank-2+812c6a699553, 77.5 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.0% (846 of 1032; likely 79.5-84.2%) |
| **Silent error rate** (wrong, of values with no review item) | 4.1% (31 of 755; likely 2.9-5.8%) |
| Silent omissions (missing and nothing flagged) | 6.6% (68 of 1032; likely 5.2-8.3%) |
| Values sent to review | 15.4% (137 of 892; likely 13.1-17.9%) |
| Wrong values caught by review | 32.6% (15 of 46; likely 20.9-47.0%) |
| Right values sent to review anyway | 14.4% (122 of 846; likely 12.2-16.9%) |
| Answer-key values present in the spread | 86.4% (892 of 1032; likely 84.2-88.4%) |
| Not judged (the answer key cannot place a row the value includes) | 35 values |
| Open review items per document (reviewer workload) | median 16, mean 16.5; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.8% (2341 of 2607; likely 88.6-90.9%) |
| Value read right | 99.4% (2326 of 2341; likely 98.9-99.6%) |
| Period right | 98.5% (2305 of 2341; likely 97.9-98.9%) |
| Template line right (where the key can judge) | 83.4% (944 of 1132; likely 81.1-85.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.9% (944 of 974; likely 95.6-97.8%) |
| none | 0.0% (0 of 119; likely 0.0-3.1%) |
| structure | 0.0% (0 of 39; likely 0.0-9.0%) |

Wrong values by kind: value 40, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 8
- cf_other_financing wrong_review: 6
- bank_securities wrong_auto: 4
- other_current_liabilities missing_silent: 4
- cf_sbc missing_silent: 4
- total_equity_parent missing_silent: 4
- stock_issued missing_silent: 4
- intangibles missing_silent: 4
- revenue missing_silent: 3
- other_opex missing_silent: 3
- cf_dna wrong_review: 3
- cf_deposits_net missing_silent: 3
- debt_issued missing_silent: 3
- debt_repaid missing_silent: 3
- cf_other_financing missing_silent: 3
- cf_commercial_paper_net missing_silent: 3
- eps_basic missing_silent: 3
- eps_diluted missing_silent: 3
- cfo wrong_auto: 3
- cf_investments_net wrong_auto: 3
- cfi wrong_auto: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_auto: 3
- cash wrong_auto: 2
- loans_gross wrong_auto: 2

Provenance: 2026-10-30T04:48:23+00:00, commit 8a7c63da413d with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-2+812c6a699553.
