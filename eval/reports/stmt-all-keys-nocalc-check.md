# Evaluation: stmt-all-keys-nocalc-check

63 documents (1 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 936.8 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 77.6% (6453 of 8315; likely 76.7-78.5%) |
| **Silent error rate** (wrong, of values with no review item) | 2.9% (136 of 4629; likely 2.5-3.5%) |
| Silent omissions (missing and nothing flagged) | 3.0% (249 of 8315; likely 2.6-3.4%) |
| Values sent to review | 34.9% (2484 of 7113; likely 33.8-36.0%) |
| Wrong values caught by review | 79.4% (524 of 660; likely 76.1-82.3%) |
| Right values sent to review anyway | 30.4% (1960 of 6453; likely 29.3-31.5%) |
| Answer-key values present in the spread | 85.5% (7113 of 8315; likely 84.8-86.3%) |
| Not judged (the answer key cannot place a row the value includes) | 343 values |
| Open review items per document (reviewer workload) | median 21, mean 20.5; blockers median 6 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.7% (12736 of 14201; likely 89.2-90.2%) |
| Value read right | 97.5% (12413 of 12736; likely 97.2-97.7%) |
| Period right | 93.6% (11921 of 12736; likely 93.2-94.0%) |
| Template line right (where the key can judge) | 86.3% (8213 of 9515; likely 85.6-87.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.7% (7414 of 7748; likely 95.2-96.1%) |
| structure | 68.2% (772 of 1132; likely 65.4-70.8%) |
| none | 0.0% (0 of 602; likely 0.0-0.6%) |
| fuzzy | 81.8% (27 of 33; likely 65.6-91.4%) |

Wrong values by kind: value 387, scale 148, period 106, sign 19

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 84
- other_opex wrong_review: 34
- other_noncurrent_liabilities wrong_review: 32
- other_nonoperating wrong_review: 29
- eps_basic missing_silent: 25
- eps_diluted missing_silent: 25
- cf_working_capital missing_silent: 24
- deferred_revenue_current wrong_review: 14
- other_nonoperating wrong_auto: 14
- other_current_assets wrong_review: 14
- shares_basic wrong_review: 14
- income_tax wrong_review: 13
- cash_end wrong_review: 12
- common_stock_apic wrong_auto: 12
- net_income_parent wrong_auto: 11
- shares_diluted wrong_review: 11
- accrued_liabilities wrong_review: 10
- cf_investments_net wrong_review: 10
- st_debt wrong_review: 10
- interest_expense wrong_review: 10
- net_income wrong_review: 10
- net_change_cash wrong_review: 10
- cf_net_income missing_silent: 9
- cash_end missing_silent: 9
- pretax_income wrong_review: 9
