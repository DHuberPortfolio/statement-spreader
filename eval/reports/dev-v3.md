# Evaluation: dev-v3

33 documents (0 crashed), profile us-commercial 2026.10.24-1+189ff92e3b46, 99.0 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 79.4% (3521 of 4434; likely 78.2-80.6%) |
| **Silent error rate** (wrong, of values with no review item) | 2.9% (73 of 2539; likely 2.3-3.6%) |
| Silent omissions (missing and nothing flagged) | 4.3% (189 of 4434; likely 3.7-4.9%) |
| Values sent to review | 32.3% (1210 of 3749; likely 30.8-33.8%) |
| Wrong values caught by review | 68.0% (155 of 228; likely 61.7-73.7%) |
| Right values sent to review anyway | 30.0% (1055 of 3521; likely 28.5-31.5%) |
| Answer-key values present in the spread | 84.6% (3749 of 4434; likely 83.5-85.6%) |
| Not judged (the answer key cannot place a row the value includes) | 184 values |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 89.5% (6870 of 7675; likely 88.8-90.2%) |
| Value read right | 99.5% (6834 of 6870; likely 99.3-99.6%) |
| Period right | 93.3% (6412 of 6870; likely 92.7-93.9%) |
| Template line right (where the key can judge) | 86.0% (4405 of 5120; likely 85.1-87.0%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 95.3% (3945 of 4141; likely 94.6-95.9%) |
| structure | 68.0% (451 of 663; likely 64.4-71.5%) |
| none | 0.0% (0 of 301; likely 0.0-1.3%) |
| fuzzy | 60.0% (9 of 15; likely 35.7-80.2%) |

Wrong values by kind: value 203, scale 13, sign 10, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- other_nonoperating wrong_review: 20
- dividends_paid missing_silent: 14
- buybacks missing_silent: 13
- debt_repaid missing_silent: 12
- stock_issued missing_silent: 12
- other_noncurrent_liabilities wrong_review: 10
- other_nonoperating wrong_auto: 10
- other_opex wrong_review: 10
- cf_working_capital missing_silent: 9
- debt_issued missing_silent: 9
- common_stock_apic wrong_auto: 8
- cf_net_income missing_silent: 6
- cf_investments_net missing_silent: 6
- other_current_assets wrong_review: 6
- cf_commercial_paper_net wrong_auto: 5
- net_income_parent wrong_auto: 5
- income_tax missing_silent: 5
- shares_basic wrong_review: 5
- income_tax wrong_review: 5
- accrued_liabilities wrong_review: 4
- deferred_revenue_current wrong_review: 4
- deferred_tax_assets wrong_review: 4
- income_tax wrong_auto: 4
- revenue missing_silent: 4
