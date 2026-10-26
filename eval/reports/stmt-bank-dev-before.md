# Evaluation: stmt-bank-dev-before

11 documents (1 crashed), profile us-bank 2026.10.25-bank-1+271918ae4a63, 109.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 68.4% (703 of 1028; likely 65.5-71.2%) |
| **Silent error rate** (wrong, of values with no review item) | 7.5% (47 of 627; likely 5.7-9.8%) |
| Silent omissions (missing and nothing flagged) | 8.6% (88 of 1028; likely 7.0-10.4%) |
| Values sent to review | 26.4% (225 of 852; likely 23.6-29.5%) |
| Wrong values caught by review | 68.5% (102 of 149; likely 60.6-75.4%) |
| Right values sent to review anyway | 17.5% (123 of 703; likely 14.9-20.5%) |
| Answer-key values present in the spread | 82.9% (852 of 1028; likely 80.5-85.1%) |
| Not judged (the answer key cannot place a row the value includes) | 39 values |
| Open review items per document (reviewer workload) | median 21, mean 19.2; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.8% (2341 of 2607; likely 88.6-90.9%) |
| Value read right | 90.9% (2127 of 2341; likely 89.6-92.0%) |
| Period right | 98.5% (2305 of 2341; likely 97.9-98.9%) |
| Template line right (where the key can judge) | 78.4% (888 of 1132; likely 76.0-80.7%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.1% (888 of 934; likely 93.5-96.3%) |
| none | 0.0% (0 of 161; likely 0.0-2.3%) |
| structure | 0.0% (0 of 37; likely 0.0-9.4%) |

Wrong values by kind: scale 93, value 56

Most frequent problems (line, outcome):

- deposits wrong_auto: 10
- st_investments wrong_auto: 8
- cf_working_capital missing_silent: 6
- preferred_equity missing_silent: 6
- st_investments missing_silent: 6
- shares_basic wrong_review: 6
- intangibles missing_silent: 6
- cf_other_financing wrong_review: 6
- bank_securities missing_silent: 4
- other_current_liabilities missing_silent: 4
- cf_sbc missing_silent: 4
- bank_securities wrong_auto: 4
- total_equity_parent missing_silent: 4
- cash wrong_review: 4
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

Provenance: 2026-10-25T22:56:46+00:00, commit feb91439b87a with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-1+271918ae4a63.
