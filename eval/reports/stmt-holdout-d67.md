# Evaluation: stmt-holdout-d67

30 documents (0 crashed), profile us-commercial 2026.11.04-1+e6cf4754763d, 91.3 s.

| Measure | Result |
|---|---|
| Spread values right (of all values in the answer keys) | 86.6% (3439 of 3973; likely 85.5-87.6%) |
| **Silent error rate** (wrong, of values with no review item) | 0.2% (2 of 1156; likely 0.0-0.6%) |
| Silent omissions (missing and nothing flagged) | 1.4% (56 of 3973; likely 1.1-1.8%) |
| Values sent to review | 68.0% (2451 of 3607; likely 66.4-69.5%) |
| Wrong values caught by review | 98.8% (166 of 168; likely 95.8-99.7%) |
| Right values sent to review anyway | 66.4% (2285 of 3439; likely 64.8-68.0%) |
| Answer-key values present in the spread | 90.8% (3607 of 3973; likely 89.8-91.6%) |
| Not judged (the answer key cannot place a row the value includes) | 169 values |
| Open review items per document (reviewer workload) | median 30, mean 28.7; blockers median 4 |

Printed numbers (SEC cells located by the answer key's tags):

| Measure | Result |
|---|---|
| Found at the right source cell | 90.4% (6082 of 6730; likely 89.6-91.1%) |
| Value read right | 99.7% (6064 of 6082; likely 99.5-99.8%) |
| Period right | 95.6% (5815 of 6082; likely 95.1-96.1%) |
| Template line right (where the key can judge) | 88.2% (4065 of 4609; likely 87.2-89.1%) |

Template line right, by how the row was mapped:

| Method | Result |
|---|---|
| alias | 96.7% (3722 of 3850; likely 96.1-97.2%) |
| structure | 69.6% (325 of 467; likely 65.3-73.6%) |
| none | 0.0% (0 of 274; likely 0.0-1.4%) |
| fuzzy | 100.0% (18 of 18; likely 82.4-100.0%) |

Wrong values by kind: value 166, sign 1, scale 1

Most frequent problems (line, outcome):

- cf_other_financing wrong_review: 32
- other_noncurrent_liabilities wrong_review: 22
- cf_working_capital missing_silent: 19
- other_nonoperating wrong_review: 17
- other_opex wrong_review: 16
- accrued_liabilities wrong_review: 12
- deferred_revenue_current wrong_review: 10
- other_current_assets wrong_review: 9
- revenue wrong_review: 6
- common_stock_apic wrong_review: 6
- other_current_liabilities wrong_review: 6
- receivables wrong_review: 5
- cf_net_income missing_silent: 5
- ppe_net wrong_review: 4
- total_equity_parent wrong_review: 4
- total_equity wrong_review: 4
- operating_lease_liab_noncurrent missing_silent: 4
- buybacks wrong_review: 3
- acquisitions missing_silent: 3
- total_equity missing_silent: 3
- cogs wrong_review: 3
- eps_diluted wrong_review: 3
- st_debt wrong_review: 2
- st_debt wrong_auto: 2
- cf_dna missing_silent: 2

Provenance: 2026-11-04T18:23:51+00:00, commit ab54be2be039 with uncommitted changes; datasets: sec-holdout 40a19fa8c6f786c4; configuration: profile us-commercial 2026.11.04-1+e6cf4754763d.
