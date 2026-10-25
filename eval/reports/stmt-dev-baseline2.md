# Evaluation: stmt-dev-baseline2

33 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 143.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 80.0% (3542 of 4425; likely 78.8-81.2%) |
| **Silent error rate** (wrong, of values with no review item) | 2.8% (70 of 2542; likely 2.2-3.5%) |
| Silent omissions (missing and nothing flagged) | 3.9% (171 of 4425; likely 3.3-4.5%) |
| Values sent to review | 32.4% (1220 of 3762; likely 31.0-33.9%) |
| Wrong values caught by review | 68.2% (150 of 220; likely 61.8-74.0%) |
| Right values sent to review anyway | 30.2% (1070 of 3542; likely 28.7-31.7%) |
| Answer-key values present in the spread | 85.0% (3762 of 4425; likely 83.9-86.0%) |
| Not judged (the answer key cannot place a row the value includes) | 187 values |
| Open review items per document (reviewer workload) | median 21, mean 20.4; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 93.4% (6454 of 6912; likely 92.8-93.9%) |
| Template line right (where the key can judge) | 86.3% (4435 of 5138; likely 85.4-87.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3975 of 4174; likely 94.5-95.8%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 195, scale 13, sign 10, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 13
- eps_diluted missing_silent: 13
- eps_basic missing_silent: 13
- other_noncurrent_liabilities wrong_review: 10
- cf_working_capital missing_silent: 10
- other_opex wrong_review: 10
- other_nonoperating wrong_auto: 9
- common_stock_apic wrong_auto: 8
- operating_income missing_silent: 6
- pretax_income missing_silent: 6
- cf_net_income missing_silent: 6
- cfo missing_silent: 6
- cf_investments_net missing_silent: 6
- net_change_cash missing_silent: 6
- other_current_assets wrong_review: 6
- net_income missing_silent: 6
- cf_commercial_paper_net wrong_auto: 5
- net_income_parent wrong_auto: 5
- cf_investments_net wrong_review: 5
- income_tax missing_silent: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- debt_issued missing_silent: 5
- debt_repaid missing_silent: 5
