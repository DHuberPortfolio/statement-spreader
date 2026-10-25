# Evaluation: stmt-all-scale-fix

63 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 185.1 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 78.0% (6556 of 8406; likely 77.1-78.9%) |
| **Silent error rate** (wrong, of values with no review item) | 2.5% (115 of 4675; likely 2.1-2.9%) |
| Silent omissions (missing and nothing flagged) | 2.9% (247 of 8406; likely 2.6-3.3%) |
| Values sent to review | 35.1% (2524 of 7199; likely 34.0-36.2%) |
| Wrong values caught by review | 82.1% (528 of 643; likely 79.0-84.9%) |
| Right values sent to review anyway | 30.4% (1996 of 6556; likely 29.3-31.6%) |
| Answer-key values present in the spread | 85.6% (7199 of 8406; likely 84.9-86.4%) |
| Not judged (the answer key cannot place a row the value includes) | 348 values |
| Open review items per document (reviewer workload) | median 21, mean 20.5; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (12897 of 14405; likely 89.0-90.0%) |
| Value read right | 97.5% (12574 of 12897; likely 97.2-97.8%) |
| Period right | 93.6% (12076 of 12897; likely 93.2-94.0%) |
| Template line right (where the key can judge) | 86.4% (8324 of 9639; likely 85.7-87.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.7% (7501 of 7838; likely 95.2-96.1%) |
| structure | 68.9% (796 of 1156; likely 66.1-71.5%) |
| none | 0.0% (0 of 612; likely 0.0-0.6%) |
| fuzzy | 81.8% (27 of 33; likely 65.6-91.4%) |

Wrong values by kind: value 363, scale 153, period 108, sign 19

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 84
- other_opex wrong_review: 34
- other_noncurrent_liabilities wrong_review: 32
- other_nonoperating wrong_review: 29
- cf_working_capital missing_silent: 24
- eps_basic missing_silent: 24
- eps_diluted missing_silent: 24
- other_current_assets wrong_review: 16
- income_tax wrong_review: 15
- deferred_revenue_current wrong_review: 14
- other_nonoperating wrong_auto: 14
- shares_basic wrong_review: 14
- cash_end wrong_review: 13
- accrued_liabilities wrong_review: 12
- common_stock_apic wrong_auto: 12
- shares_diluted wrong_review: 11
- cf_investments_net wrong_review: 10
- st_debt wrong_review: 10
- interest_expense wrong_review: 10
- net_income_parent wrong_review: 10
- net_change_cash wrong_review: 10
- cf_net_income missing_silent: 9
- cash_end missing_silent: 9
- net_income wrong_review: 9
- pretax_income wrong_review: 9
