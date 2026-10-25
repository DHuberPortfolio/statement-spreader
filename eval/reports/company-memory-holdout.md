# Company memory: company-memory-holdout

29 holdout companies: the prior-year 10-K approved against its own key, then the current 10-K spread without and with what that approval left behind. Not counted, because the engine crashed: DECK prior year: ValueError: invalid literal for int() with base 10: 'col1'.

| Measure | Without memory | With memory |
|---|---|---|
| **Silent error rate** | 2.3% (47 of 2053; likely 1.7-3.0%) | 0.4% (10 of 2334; likely 0.2-0.8%) |
| Wrong values caught by review | 88.6% (366 of 413; likely 85.2-91.3%) | 97.2% (350 of 360; likely 95.0-98.5%) |
| Silent omissions | 3.9% (150 of 3890; likely 3.3-4.5%) | 2.4% (92 of 3859; likely 1.9-2.9%) |
| Values right | 73.9% (2873 of 3890; likely 72.5-75.2%) | 81.7% (3154 of 3859; likely 80.5-82.9%) |
| Right values sent to review | 30.2% (867 of 2873; likely 28.5-31.9%) | 26.3% (830 of 3154; likely 24.8-27.9%) |
| Open review items per document | median 24, mean 23.2 | median 26, mean 31.0 |

Wrong values that were silent without memory and are caught with it: 24; caught before and silent now: 0.

Rows placed by the company's confirmed mappings: 1251 judged, 1245 right.

Comparison items (differences from the approved prior year), labelled with the keys:

| What it really was | Items |
|---|---|
| misread | 307 |
| misread and restatement | 7 |
| restatement | 51 |
| unknown (no key value) | 33 |

What the item said, against what it really was:

| Really | Item said | Items |
|---|---|---|
| misread | misread | 120 |
| misread | restatement | 10 |
| misread | unclear | 177 |
| misread and restatement | unclear | 7 |
| restatement | misread | 9 |
| restatement | restatement | 6 |
| restatement | unclear | 36 |
| unknown (no key value) | misread | 2 |
| unknown (no key value) | restatement | 3 |
| unknown (no key value) | unclear | 28 |

Provenance: 2026-10-25T07:17:36+00:00, commit 342cddd4cbe0 with uncommitted changes; datasets: sec-holdout 8e7f8dff07628aa1, sec-holdout-prior (unversioned); configuration: profile us-commercial 2026.10.24-1+0ad0af213be8.
