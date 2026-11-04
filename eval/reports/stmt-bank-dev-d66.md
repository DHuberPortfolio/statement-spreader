# Evaluation: stmt-bank-dev-d66

11 documents (1 crashed), profile us-bank 2026.10.25-bank-2+a709ec078556, 201.4 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 87.8% (905 of 1031; likely 85.6-89.6%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 323; likely 0.0-1.2%) |
| Silent omissions (missing and nothing flagged) | 4.3% (44 of 1031; likely 3.2-5.7%) |
| Values sent to review | 65.2% (606 of 929; likely 62.1-68.2%) |
| Wrong values caught by review | 100.0% (24 of 24; likely 86.2-100.0%) |
| Right values sent to review anyway | 64.3% (582 of 905; likely 61.1-67.4%) |
| Answer-key values present in the spread | 90.1% (929 of 1031; likely 88.1-91.8%) |
| Not judged (the answer key cannot place a row the value includes) | 36 values |
| Open review items per document (reviewer workload) | median 29, mean 23.7; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 93.9% (2449 of 2607; likely 93.0-94.8%) |
| Value read right | 99.4% (2434 of 2449; likely 99.0-99.6%) |
| Period right | 98.5% (2413 of 2449; likely 98.0-98.9%) |
| Template line right (where the key can judge) | 85.1% (991 of 1165; likely 82.9-87.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.8% (987 of 1020; likely 95.5-97.7%) |
| none | 0.0% (0 of 118; likely 0.0-3.2%) |
| structure | 14.8% (4 of 27; likely 5.9-32.5%) |

Wrong values by kind: value 18, scale 6

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 8
- cf_other_financing wrong_review: 6
- other_current_liabilities missing_silent: 4
- other_opex missing_silent: 3
- eps_diluted wrong_review: 3
- shares_diluted missing_silent: 3
- cf_deposits_net missing_silent: 3
- debt_issued missing_silent: 3
- debt_repaid missing_silent: 3
- cf_other_financing missing_silent: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_review: 3
- lt_debt wrong_review: 2
- cf_investments_net missing_silent: 2
- ppe_net missing_silent: 2
- common_stock_apic wrong_review: 2
- st_investments wrong_review: 2
- bank_securities wrong_review: 2
- intangibles missing_silent: 2
- common_stock_apic missing_silent: 2
- loans_held_for_sale missing_silent: 2
- loans_net missing_silent: 2
- acquisitions missing_silent: 1
- stock_issued missing_silent: 1
- other_nonoperating wrong_review: 1

Provenance: 2026-11-04T07:45:28+00:00, commit 22f07e2c3d97 with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-2+a709ec078556.
