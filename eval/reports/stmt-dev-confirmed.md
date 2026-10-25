# Evaluation: stmt-dev-confirmed

33 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 148.8 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 81.5% (3608 of 4428; likely 80.3-82.6%) |
| **Silent error rate** (wrong, of values with no review item) | 2.3% (59 of 2516; likely 1.8-3.0%) |
| Silent omissions (missing and nothing flagged) | 2.2% (97 of 4428; likely 1.8-2.7%) |
| Values sent to review | 34.3% (1314 of 3830; likely 32.8-35.8%) |
| Wrong values caught by review | 73.4% (163 of 222; likely 67.2-78.8%) |
| Right values sent to review anyway | 31.9% (1151 of 3608; likely 30.4-33.4%) |
| Answer-key values present in the spread | 86.5% (3830 of 4428; likely 85.5-87.5%) |
| Not judged (the answer key cannot place a row the value includes) | 184 values |
| Open review items per document (reviewer workload) | median 24, mean 23.4; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 94.3% (6519 of 6912; likely 93.7-94.8%) |
| Template line right (where the key can judge) | 86.3% (4435 of 5138; likely 85.4-87.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3975 of 4174; likely 94.5-95.8%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 193, scale 13, sign 12, period 4

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 49
- other_nonoperating wrong_review: 15
- other_opex wrong_review: 12
- other_noncurrent_liabilities wrong_review: 10
- eps_basic missing_silent: 10
- eps_diluted missing_silent: 10
- other_nonoperating wrong_auto: 9
- cf_working_capital missing_silent: 8
- common_stock_apic wrong_auto: 8
- cf_investments_net wrong_review: 7
- income_tax wrong_review: 7
- other_current_assets wrong_review: 6
- cf_commercial_paper_net wrong_auto: 5
- operating_income missing_silent: 5
- cfo missing_silent: 5
- shares_basic wrong_review: 5
- cash_end wrong_review: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
- income_tax wrong_auto: 4
- cf_net_income missing_silent: 4
- cf_investments_net missing_silent: 4
- net_change_cash missing_silent: 4
- ppe_net wrong_review: 4

Provenance: 2026-10-25T08:11:51+00:00, commit a42ce9d554ab with uncommitted changes; datasets: sec-dev 83478e9b205ab8ac; configuration: profile us-commercial 2026.10.24-1+0ad0af213be8.
