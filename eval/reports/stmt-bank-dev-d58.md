# Evaluation: stmt-bank-dev-d58

11 documents (1 crashed), profile us-bank 2026.10.25-bank-2+2f82c64be98d, 201.0 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 82.7% (853 of 1032; likely 80.2-84.8%) |
| **Silent error rate** (wrong, of values with no review item) | 4.1% (31 of 755; likely 2.9-5.8%) |
| Silent omissions (missing and nothing flagged) | 5.9% (61 of 1032; likely 4.6-7.5%) |
| Values sent to review | 16.0% (144 of 899; likely 13.8-18.6%) |
| Wrong values caught by review | 32.6% (15 of 46; likely 20.9-47.0%) |
| Right values sent to review anyway | 15.1% (129 of 853; likely 12.9-17.7%) |
| Answer-key values present in the spread | 87.1% (899 of 1032; likely 84.9-89.0%) |
| Not judged (the answer key cannot place a row the value includes) | 35 values |
| Open review items per document (reviewer workload) | median 18, mean 16.9; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.8% (2341 of 2607; likely 88.6-90.9%) |
| Value read right | 99.4% (2326 of 2341; likely 98.9-99.6%) |
| Period right | 98.5% (2305 of 2341; likely 97.9-98.9%) |
| Template line right (where the key can judge) | 84.0% (951 of 1132; likely 81.8-86.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.9% (947 of 977; likely 95.7-97.8%) |
| none | 0.0% (0 of 119; likely 0.0-3.1%) |
| structure | 11.1% (4 of 36; likely 4.4-25.3%) |

Wrong values by kind: value 40, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 8
- cf_other_financing wrong_review: 6
- bank_securities wrong_auto: 4
- other_current_liabilities missing_silent: 4
- cf_sbc missing_silent: 4
- stock_issued missing_silent: 4
- intangibles missing_silent: 4
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
- allowance_loan_losses wrong_auto: 2
- loans_net wrong_auto: 2

Provenance: 2026-11-01T02:01:39+00:00, commit 5d00382fa480 with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-2+2f82c64be98d.
