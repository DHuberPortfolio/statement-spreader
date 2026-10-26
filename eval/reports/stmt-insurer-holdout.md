# Evaluation: stmt-insurer-holdout

14 documents (0 crashed), profile us-insurer 2026.10.25-insurer-2+413e86b955cb, 924.7 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 59.1% (867 of 1468; likely 56.5-61.5%) |
| **Silent error rate** (wrong, of values with no review item) | 7.8% (58 of 744; likely 6.1-9.9%) |
| Silent omissions (missing and nothing flagged) | 7.9% (116 of 1468; likely 6.6-9.4%) |
| Values sent to review | 28.8% (301 of 1045; likely 26.1-31.6%) |
| Wrong values caught by review | 67.4% (120 of 178; likely 60.2-73.9%) |
| Right values sent to review anyway | 20.9% (181 of 867; likely 18.3-23.7%) |
| Answer-key values present in the spread | 71.2% (1045 of 1468; likely 68.8-73.4%) |
| Not judged (the answer key cannot place a row the value includes) | 69 values |
| Open review items per document (reviewer workload) | median 24, mean 25.6; blockers median 3 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 75.1% (2854 of 3800; likely 73.7-76.5%) |
| Value read right | 99.4% (2836 of 2854; likely 99.0-99.6%) |
| Period right | 97.7% (2788 of 2854; likely 97.1-98.2%) |
| Template line right (where the key can judge) | 69.0% (992 of 1438; likely 66.5-71.3%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 93.4% (965 of 1033; likely 91.7-94.8%) |
| none | 0.0% (0 of 245; likely 0.0-1.5%) |
| structure | 13.6% (21 of 154; likely 9.1-19.9%) |
| fuzzy | 100.0% (6 of 6; likely 61.0-100.0%) |

Wrong values by kind: value 178

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 24
- cf_working_capital missing_silent: 15
- common_stock_apic wrong_auto: 13
- other_opex wrong_review: 9
- eps_diluted missing_silent: 9
- cf_investments_net wrong_auto: 9
- net_change_cash wrong_review: 9
- net_income_parent wrong_review: 9
- debt_repaid wrong_auto: 8
- premiums_receivable missing_silent: 6
- total_insurance_expenses missing_silent: 6
- eps_basic missing_silent: 6
- revenue wrong_review: 6
- income_tax wrong_review: 6
- cfo wrong_review: 6
- cfi wrong_review: 6
- cash_end wrong_review: 6
- deferred_tax_assets missing_silent: 6
- loss_reserves missing_silent: 6
- deferred_tax_liabilities missing_silent: 6
- cf_net_income wrong_review: 5
- future_policy_benefits missing_silent: 4
- operating_income missing_silent: 3
- acquisitions missing_silent: 3
- net_investment_income wrong_review: 3

Provenance: 2026-10-26T03:21:59+00:00, commit 13ac4499c88d; datasets: insurer-holdout 4563b89687d822df (DIFFERS FROM ITS MANIFEST); configuration: profile us-insurer 2026.10.25-insurer-2+413e86b955cb.
