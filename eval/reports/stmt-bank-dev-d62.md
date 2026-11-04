# Evaluation: stmt-bank-dev-d62

11 documents (1 crashed), profile us-bank 2026.10.25-bank-2+d568968a4ae3, 79.6 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 84.2% (866 of 1029; likely 81.8-86.3%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 312; likely 0.0-1.2%) |
| Silent omissions (missing and nothing flagged) | 6.1% (63 of 1029; likely 4.8-7.8%) |
| Values sent to review | 65.4% (590 of 902; likely 62.2-68.4%) |
| Wrong values caught by review | 100.0% (36 of 36; likely 90.4-100.0%) |
| Right values sent to review anyway | 64.0% (554 of 866; likely 60.7-67.1%) |
| Answer-key values present in the spread | 87.7% (902 of 1029; likely 85.5-89.5%) |
| Not judged (the answer key cannot place a row the value includes) | 38 values |
| Open review items per document (reviewer workload) | median 26, mean 22.4; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 93.9% (2449 of 2607; likely 93.0-94.8%) |
| Value read right | 99.4% (2434 of 2449; likely 99.0-99.6%) |
| Period right | 98.5% (2413 of 2449; likely 98.0-98.9%) |
| Template line right (where the key can judge) | 83.2% (969 of 1165; likely 80.9-85.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 97.0% (965 of 995; likely 95.7-97.9%) |
| none | 0.0% (0 of 134; likely 0.0-2.8%) |
| structure | 11.1% (4 of 36; likely 4.4-25.3%) |

Wrong values by kind: value 30, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 10
- cf_other_financing wrong_review: 6
- cash wrong_review: 4
- bank_securities wrong_review: 4
- other_current_liabilities missing_silent: 4
- cf_investments_net missing_silent: 4
- stock_issued missing_silent: 4
- intangibles missing_silent: 4
- other_opex missing_silent: 3
- cf_dna wrong_review: 3
- cf_sbc missing_silent: 3
- cf_deposits_net missing_silent: 3
- debt_issued missing_silent: 3
- debt_repaid missing_silent: 3
- cf_other_financing missing_silent: 3
- cf_commercial_paper_net missing_silent: 3
- eps_basic missing_silent: 3
- eps_diluted missing_silent: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_review: 3
- loans_gross wrong_review: 2
- allowance_loan_losses wrong_review: 2
- loans_net wrong_review: 2
- lt_debt wrong_review: 2
- ppe_net missing_silent: 2

Provenance: 2026-11-04T00:15:38+00:00, commit d0a978102d16 with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-2+d568968a4ae3.
