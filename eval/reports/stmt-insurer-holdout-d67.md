# Evaluation: stmt-insurer-holdout-d67

14 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+ff2a27d5511b, 226.4 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 71.9% (1045 of 1454; likely 69.5-74.1%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 250; likely 0.0-1.5%) |
| Silent omissions (missing and nothing flagged) | 5.4% (78 of 1454; likely 4.3-6.6%) |
| Values sent to review | 78.4% (905 of 1155; likely 75.9-80.6%) |
| Wrong values caught by review | 100.0% (110 of 110; likely 96.6-100.0%) |
| Right values sent to review anyway | 76.1% (795 of 1045; likely 73.4-78.6%) |
| Answer-key values present in the spread | 79.4% (1155 of 1454; likely 77.3-81.4%) |
| Not judged (the answer key cannot place a row the value includes) | 83 values |
| Open review items per document (reviewer workload) | median 32, mean 33.3; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.3% (3395 of 3800; likely 88.3-90.3%) |
| Value read right | 99.4% (3374 of 3395; likely 99.1-99.6%) |
| Period right | 97.7% (3317 of 3395; likely 97.1-98.2%) |
| Template line right (where the key can judge) | 73.0% (1209 of 1657; likely 70.8-75.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 93.8% (1184 of 1262; likely 92.4-95.0%) |
| none | 0.0% (0 of 242; likely 0.0-1.6%) |
| structure | 16.3% (25 of 153; likely 11.3-23.0%) |

Wrong values by kind: value 101, scale 6, sign 3

Most frequent problems (line, outcome):

- cf_working_capital missing_silent: 17
- common_stock_apic wrong_review: 14
- cf_other_financing wrong_review: 13
- net_income_parent wrong_review: 12
- other_opex wrong_review: 9
- cf_investments_net wrong_review: 9
- debt_repaid wrong_review: 8
- premiums_receivable missing_silent: 6
- cf_working_capital wrong_review: 6
- deferred_tax_assets missing_silent: 6
- cf_investments_net missing_silent: 5
- total_equity_parent wrong_review: 4
- total_equity wrong_review: 4
- future_policy_benefits wrong_review: 4
- deferred_tax_liabilities missing_silent: 4
- operating_income missing_silent: 3
- acquisitions missing_silent: 3
- losses_lae wrong_review: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_review: 3
- income_tax wrong_review: 3
- nci_net_income wrong_review: 3
- cf_commercial_paper_net missing_silent: 3
- net_income wrong_review: 3
- capex missing_silent: 3

Provenance: 2026-11-04T18:33:32+00:00, commit ab54be2be039 with uncommitted changes; datasets: insurer-holdout 6b26e428fa3f884a; configuration: profile us-insurer 2026.10.25-insurer-2+ff2a27d5511b.
