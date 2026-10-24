# Improvement log

Each entry: what was wrong, the hypothesis, the change, and the measured effect on the SEC dev split
(33 filings, 4,618 answer-key values). The holdout split is not used for tuning.

| # | Change | Accuracy | Silent error rate | Silent omissions | Kept? |
|---|---|---|---|---|---|
| 0 | Baseline (first full run) | 60.8% | 7.1% (129 of 1,816) | 17.2% | - |
| 1 | Year-only column headers take the fiscal year-end from the title or another statement; first version read any date near the table | 60.0% | 6.7% | 21.8% | Reverted in part: audit-report dates ("August 4, 2026") were read as period ends |
| 2 | Only dates after period wording ("years ended June 30", "as of") count; header-row label cell read first; "% change" tables penalised in detection; unit statements like "Millions, except per share" recognised | 69.4% | 6.3% (152 of 2,410) | 8.4% | Yes. No filing got worse; PG, PEP, UNP, HAS went from ~0 to mostly right |
| 3 | A cost printed in parentheses inside a printed total is a deduction: spread as a positive cost (found by a unit test: interest expense "(10)" broke the pre-tax check) | 70.3% | 6.4% (158 of 2,478) | 8.4% | Yes (silent rate change within noise; accuracy up) |

Known measurement limitation (to fix in the scorer): when a filing tags a row with a
company-specific concept, the answer key does not know which template line that row feeds, so the
key's total for that line can be incomplete and a correct spread value is scored wrong (seen on
Apple's working-capital line: the key misses "vendor non-trade receivables").
