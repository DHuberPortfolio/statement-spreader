# Evaluation: regress-final-platform

153 documents (0 crashed), profile us-commercial 2026.10.24-1+0ad0af213be8, 111.7 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 93.1% (17627 of 18942; likely 92.7-93.4%) |
| **Silent error rate** (wrong, of values with no review item) | 0.5% (76 of 15994; likely 0.4-0.6%) |
| Silent omissions (missing and nothing flagged) | 2.2% (423 of 18942; likely 2.0-2.5%) |
| Values sent to review | 10.4% (1859 of 17853; likely 10.0-10.9%) |
| Wrong values caught by review | 66.4% (150 of 226; likely 60.0-72.2%) |
| Right values sent to review anyway | 9.7% (1709 of 17627; likely 9.3-10.1%) |
| Answer-key values present in the spread | 94.3% (17853 of 18942; likely 93.9-94.6%) |
| Not judged (the answer key cannot place a row the value includes) | 187 values |
| Open review items per document (reviewer workload) | median 1, mean 6.3; blockers median 0 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 93.0% (12012 of 12913; likely 92.6-93.4%) |
| Value read right | 99.7% (11976 of 12012; likely 99.6-99.8%) |
| Period right | 96.2% (11554 of 12012; likely 95.8-96.5%) |
| Template line right (where the key can judge) | 93.1% (9476 of 10179; likely 92.6-93.6%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 97.8% (8659 of 8858; likely 97.4-98.0%) |
| structure | 79.8% (792 of 992; likely 77.2-82.2%) |
| none | 0.0% (0 of 298; likely 0.0-1.3%) |
| fuzzy | 80.6% (25 of 31; likely 63.7-90.8%) |

Wrong values by kind: value 201, scale 13, sign 10, period 2

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 47
- eps_diluted missing_silent: 22
- eps_basic missing_silent: 22
- operating_income missing_silent: 15
- pretax_income missing_silent: 15
- net_income missing_silent: 15
- income_tax missing_silent: 14
- common_stock_apic wrong_auto: 14
- cogs missing_silent: 13
- other_nonoperating wrong_review: 13
- revenue missing_silent: 12
- sga missing_silent: 12
- total_opex missing_silent: 12
- shares_diluted missing_silent: 11
- shares_basic missing_silent: 11
- other_noncurrent_liabilities wrong_review: 10
- cf_working_capital missing_silent: 10
- other_opex wrong_review: 10
- interest_expense missing_silent: 10
- interest_income missing_silent: 10
- other_nonoperating wrong_auto: 9
- rnd missing_silent: 9
- total_equity_parent missing_silent: 8
- total_liabilities_equity missing_silent: 8
- cf_net_income missing_silent: 6
