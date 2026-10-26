# Evaluation: stmt-bank-dev-after

11 documents (1 crashed), profile us-bank 2026.10.25-bank-2+343c5cbc6927, 300.9 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 73.0% (749 of 1026; likely 70.2-75.6%) |
| **Silent error rate** (wrong, of values with no review item) | 4.8% (31 of 645; likely 3.4-6.7%) |
| Silent omissions (missing and nothing flagged) | 5.7% (58 of 1026; likely 4.4-7.2%) |
| Values sent to review | 27.2% (241 of 886; likely 24.4-30.2%) |
| Wrong values caught by review | 77.4% (106 of 137; likely 69.7-83.6%) |
| Right values sent to review anyway | 18.0% (135 of 749; likely 15.4-20.9%) |
| Answer-key values present in the spread | 86.4% (886 of 1026; likely 84.1-88.3%) |
| Not judged (the answer key cannot place a row the value includes) | 41 values |
| Open review items per document (reviewer workload) | median 16, mean 18.3; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.8% (2341 of 2607; likely 88.6-90.9%) |
| Value read right | 90.9% (2127 of 2341; likely 89.6-92.0%) |
| Period right | 98.5% (2305 of 2341; likely 97.9-98.9%) |
| Template line right (where the key can judge) | 83.4% (944 of 1132; likely 81.1-85.4%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.9% (944 of 974; likely 95.6-97.8%) |
| none | 0.0% (0 of 119; likely 0.0-3.1%) |
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
- revenue missing_silent: 3
- other_opex missing_silent: 3
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
- provision_credit_losses wrong_review: 3
- nii_after_provision wrong_review: 3
- noninterest_income wrong_review: 3
- sga wrong_review: 3

Provenance: 2026-10-25T23:36:48+00:00, commit 2c305ad5495d with uncommitted changes; datasets: bank-dev 68cdb39e53db043f; configuration: profile us-bank 2026.10.25-bank-2+343c5cbc6927.
