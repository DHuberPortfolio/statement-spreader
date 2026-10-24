# Evaluation: syn-v3

120 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 15.2 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 94.7% (13743 of 14517; likely 94.3-95.0%) |
| **Silent error rate** (wrong, of values with no review item) | 0.1% (12 of 13082; likely 0.1-0.2%) |
| Silent omissions (missing and nothing flagged) | 4.3% (627 of 14517; likely 4.0-4.7%) |
| Values sent to review | 4.9% (673 of 13755; likely 4.5-5.3%) |
| Wrong values caught by review | 0.0% (0 of 12; likely 0.0-24.3%) |
| Right values sent to review anyway | 4.9% (673 of 13743; likely 4.5-5.3%) |
| Answer-key values present in the spread | 94.8% (13755 of 14517; likely 94.4-95.1%) |
| Not judged (the answer key cannot place a row the value includes) | 0 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 97.4% (5100 of 5238; likely 96.9-97.8%) |
| Value read right | 100.0% (5100 of 5100; likely 99.9-100.0%) |
| Period right | 100.0% (5100 of 5100; likely 99.9-100.0%) |
| Template line right (where the key can judge) | 100.0% (5041 of 5041; likely 99.9-100.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 100.0% (4684 of 4684; likely 99.9-100.0%) |
| structure | 100.0% (341 of 341; likely 98.9-100.0%) |
| fuzzy | 100.0% (16 of 16; likely 80.6-100.0%) |

Wrong values by kind: value 12

Most frequent problems (line, outcome):

- cff missing_silent: 24
- cf_net_income missing_silent: 21
- cf_dna missing_silent: 21
- cf_sbc missing_silent: 21
- cf_working_capital missing_silent: 21
- cfo missing_silent: 21
- capex missing_silent: 21
- cfi missing_silent: 21
- debt_repaid missing_silent: 21
- net_change_cash missing_silent: 21
- cash_begin missing_silent: 21
- cash_end missing_silent: 21
- debt_issued missing_silent: 16
- common_stock_apic wrong_auto: 12
- cf_investments_net missing_silent: 11
- cf_other_investing missing_silent: 11
- cash missing_silent: 10
- receivables missing_silent: 10
- other_current_assets missing_silent: 10
- total_current_assets missing_silent: 10
- ppe_net missing_silent: 10
- other_noncurrent_assets missing_silent: 10
- total_assets missing_silent: 10
- payables missing_silent: 10
- accrued_liabilities missing_silent: 10
