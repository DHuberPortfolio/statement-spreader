# XBRL second reader: xbrl-check

**Not independent of the SEC answer keys**, which are built from the same tags. These figures say how often the printed-number reader and the tags disagree, and who was right on a hand-checked sample; they are not accuracy figures and are not comparable with the README's.

| Split | Filings | Printed numbers with a tag on their cell | Readers agree | Disagree: value | scale | period | Disagreements on values not already sent to review |
|---|---|---|---|---|---|---|---|
| dev | 33 | 6,233 | 96.8% (6035 of 6233; likely 96.4-97.2%) | 0 | 27 | 171 | 5 |
| holdout | 30 | 5,381 | 91.7% (4933 of 5381; likely 90.9-92.4%) | 0 | 240 | 208 | 19 |

Hand-checked sample: 30 disagreements drawn at random (seed 20261025) from both splits; verdicts recorded: 30.

| Who was right (checked against the printed filing) | Disagreements |
|---|---|
| tag | 29 |
| printed | 1 |

Provenance: 2026-10-25T07:59:29+00:00, commit 2a4d9733eaf9 with uncommitted changes; datasets: sec-dev 83478e9b205ab8ac, sec-holdout 8e7f8dff07628aa1; configuration: profile us-commercial 2026.10.24-1+0ad0af213be8, second_reader on (measurement only).
