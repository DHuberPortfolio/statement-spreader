# Evaluation: stmt-dev-v3

33 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 149.0 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 80.9% (3582 of 4426; likely 79.7-82.1%) |
| **Silent error rate** (wrong, of values with no review item) | 2.8% (71 of 2541; likely 2.2-3.5%) |
| Silent omissions (missing and nothing flagged) | 2.5% (111 of 4426; likely 2.1-3.0%) |
| Values sent to review | 33.4% (1275 of 3816; likely 31.9-34.9%) |
| Wrong values caught by review | 69.7% (163 of 234; likely 63.5-75.2%) |
| Right values sent to review anyway | 31.0% (1112 of 3582; likely 29.5-32.6%) |
| Answer-key values present in the spread | 86.2% (3816 of 4426; likely 85.2-87.2%) |
| Not judged (the answer key cannot place a row the value includes) | 186 values |
| Open review items per document (reviewer workload) | median 21, mean 20.5; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.1% (6912 of 7675; likely 89.4-90.7%) |
| Value read right | 99.5% (6876 of 6912; likely 99.3-99.6%) |
| Period right | 93.2% (6440 of 6912; likely 92.6-93.7%) |
| Template line right (where the key can judge) | 86.3% (4435 of 5138; likely 85.4-87.2%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.2% (3975 of 4174; likely 94.5-95.8%) |
| structure | 69.3% (451 of 651; likely 65.6-72.7%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 206, scale 13, sign 12, period 3

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 49
- other_nonoperating wrong_review: 15
- other_opex wrong_review: 12
- eps_basic missing_silent: 11
- eps_diluted missing_silent: 11
- other_noncurrent_liabilities wrong_review: 10
- other_nonoperating wrong_auto: 9
- cf_working_capital missing_silent: 8
- common_stock_apic wrong_auto: 8
- cf_investments_net wrong_review: 7
- income_tax wrong_review: 7
- operating_income missing_silent: 6
- net_income_parent wrong_auto: 6
- other_current_assets wrong_review: 6
- cf_commercial_paper_net wrong_auto: 5
- cfo missing_silent: 5
- shares_basic wrong_review: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
- cogs missing_silent: 4
- pretax_income missing_silent: 4
- income_tax wrong_auto: 4
- cf_net_income missing_silent: 4
- cf_investments_net missing_silent: 4
