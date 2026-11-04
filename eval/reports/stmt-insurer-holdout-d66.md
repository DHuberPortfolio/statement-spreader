# Evaluation: stmt-insurer-holdout-d66

14 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+d077afa34342, 512.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 71.0% (1037 of 1461; likely 68.6-73.2%) |
| **Silent error rate** (wrong, of values with no review item) | 0.0% (0 of 252; likely 0.0-1.5%) |
| Silent omissions (missing and nothing flagged) | 5.8% (85 of 1461; likely 4.7-7.1%) |
| Values sent to review | 77.9% (890 of 1142; likely 75.4-80.2%) |
| Wrong values caught by review | 100.0% (105 of 105; likely 96.5-100.0%) |
| Right values sent to review anyway | 75.7% (785 of 1037; likely 73.0-78.2%) |
| Answer-key values present in the spread | 78.2% (1142 of 1461; likely 76.0-80.2%) |
| Not judged (the answer key cannot place a row the value includes) | 76 values |
| Open review items per document (reviewer workload) | median 29, mean 32.5; blockers median 2 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.3% (3395 of 3800; likely 88.3-90.3%) |
| Value read right | 99.4% (3374 of 3395; likely 99.1-99.6%) |
| Period right | 97.7% (3317 of 3395; likely 97.1-98.2%) |
| Template line right (where the key can judge) | 72.1% (1194 of 1657; likely 69.8-74.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 93.7% (1163 of 1241; likely 92.2-94.9%) |
| none | 0.0% (0 of 251; likely 0.0-1.5%) |
| structure | 15.7% (25 of 159; likely 10.9-22.2%) |
| fuzzy | 100.0% (6 of 6; likely 61.0-100.0%) |

Wrong values by kind: value 96, scale 6, sign 3

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
- loss_reserves missing_silent: 4
- deferred_tax_liabilities missing_silent: 4
- operating_income missing_silent: 3
- acquisitions missing_silent: 3
- shares_basic wrong_review: 3
- shares_diluted wrong_review: 3
- income_tax wrong_review: 3
- nci_net_income wrong_review: 3
- cf_commercial_paper_net missing_silent: 3
- net_income wrong_review: 3
- capex missing_silent: 3
- pretax_income missing_silent: 3

Provenance: 2026-11-04T07:52:19+00:00, commit 22f07e2c3d97 with uncommitted changes; datasets: insurer-holdout 6b26e428fa3f884a; configuration: profile us-insurer 2026.10.25-insurer-2+d077afa34342.
