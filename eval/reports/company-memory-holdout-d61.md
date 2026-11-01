# Company memory: company-memory-holdout-d61

30 holdout companies: the prior-year 10-K approved against its own key, then the current 10-K spread without and with what that approval left behind.

| Measure | Without memory | With memory |
|---|---|---|
| **Silent error rate** | 0.6% (5 of 825; likely 0.3-1.4%) | 0.0% (0 of 1231; likely 0.0-0.3%) |
| Wrong values caught by review | 97.1% (165 of 170; likely 93.3-98.7%) | 100.0% (63 of 63; likely 94.3-100.0%) |
| Silent omissions | 1.7% (67 of 3972; likely 1.3-2.1%) | 0.8% (30 of 3938; likely 0.5-1.1%) |
| Values right | 81.8% (3249 of 3972; likely 80.6-83.0%) | 91.1% (3589 of 3938; likely 90.2-92.0%) |
| Right values sent to review | 74.8% (2429 of 3249; likely 73.2-76.2%) | 65.7% (2358 of 3589; likely 64.1-67.2%) |
| Open review items per document | median 32, mean 29.4 | median 32, mean 31.1 |

Wrong values that were silent without memory and are caught with it: 0; caught before and silent now: 0.

Rows placed by the company's confirmed mappings: 1303 judged, 1297 right.

Comparison items (differences from the approved prior year), labelled with the keys:

| What it really was | Items |
|---|---|
| misread | 147 |
| misread and restatement | 7 |
| restatement | 51 |
| unknown (no key value) | 35 |

What the item said, against what it really was:

| Really | Item said | Items |
|---|---|---|
| misread | misread | 7 |
| misread | restatement | 3 |
| misread | unclear | 137 |
| misread and restatement | unclear | 7 |
| restatement | misread | 9 |
| restatement | restatement | 6 |
| restatement | unclear | 36 |
| unknown (no key value) | misread | 2 |
| unknown (no key value) | restatement | 3 |
| unknown (no key value) | unclear | 30 |

Provenance: 2026-11-01T21:55:13+00:00, commit 25949c79377c with uncommitted changes; datasets: sec-holdout 40a19fa8c6f786c4, sec-holdout-prior 9180bcb40a44d9c3; configuration: profile us-commercial 2026.10.24-1+6326bff395cd.
