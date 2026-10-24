# Improvement log

Each entry: what was wrong, the hypothesis, the change, and the measured effect on the SEC dev split
(33 filings, 4,618 answer-key values). The holdout split is not used for tuning.

| # | Change | Accuracy | Silent error rate | Silent omissions | Kept? |
|---|---|---|---|---|---|
| 0 | Baseline (first full run) | 60.8% | 7.1% (129 of 1,816) | 17.2% | - |
| 1 | Year-only column headers take the fiscal year-end from the title or another statement; first version read any date near the table | 60.0% | 6.7% | 21.8% | Reverted in part: audit-report dates ("August 4, 2026") were read as period ends |
| 2 | Only dates after period wording ("years ended June 30", "as of") count; header-row label cell read first; "% change" tables penalised in detection; unit statements like "Millions, except per share" recognised | 69.4% | 6.3% (152 of 2,410) | 8.4% | Yes. No filing got worse; PG, PEP, UNP, HAS went from ~0 to mostly right |
| 3 | A cost printed in parentheses inside a printed total is a deduction: spread as a positive cost (found by a unit test: interest expense "(10)" broke the pre-tax check) | 70.3% | 6.4% (158 of 2,478) | 8.4% | Yes (silent rate change within noise; accuracy up) |
| 4 | Scorer: one namespace-free cell path for reader and key (attribution now measurable: 89.5% of tagged cells found, 99.5% of those read right); values the key cannot judge (company-specific tags) moved to "unjudged" | 72.3% | 3.7% (90 of 2,410) | 8.7% | Yes. A measurement correction, not a pipeline gain: 125 values were scored wrong only because the key was incomplete |
| 5 | Cover page "fiscal year ended January 3, 2026" dates year-only columns (52/53-week years) | 75.0% | 3.7% (90 of 2,440) | 5.7% | Yes |
| 6 | Fixes from the synthetic corpus: tax sign with costs in parentheses, "weighted average shares outstanding - basic", "in U.S. dollars" as a unit, units from period columns only, ambiguous three-decimal amounts refused, Excel year/date headers | 75.1% | 3.9% (96 of 2,451) | 5.7% | Yes. Synthetic silent error rate 1.9% -> 0.3%; SEC change within noise |
| 7 | Mapping accuracy measured per method (alias 95.4%, section catch-all 56.0%, fuzzy 66.7%); aliases added for the rows catch-alls got wrong (financing, investing, opex, receivables, accrued); totals worded "...investing activities" mapped by footing; fuzzy confidence 0.85 -> 0.7 (measured 12 of 18) | 79.4% | 2.9% (72 of 2,519) | 4.6% | Yes. First holdout measurement (30 filings, never tuned on): 73.3% right, 3.4% silent (73 of 2,116, likely 2.8-4.3%), 5.9% silent omissions. Synthetic: 94.7% right, 0.1% silent |
| 8 | From building the UI and using it: a cost printed in parentheses with no total to explain it is spread positive (and said so); check tolerance counts only printed numbers present; ratios with every input missing not computed; a footing-proven subtotal of rows already on different lines (Coca-Cola's "Total cash, cash equivalents and short-term investments") is left out instead of double-counted; a failed check names the row whose amount equals the difference | 79.4% | 2.9% (73 of 2,539) | 4.3% | Yes (omissions down; silent rate unchanged) |
| 9 | Local model tier (Qwen3-4B-Instruct-2507, Q4_K_M, llama.cpp CUDA on the RTX 3060 Ti) for rows no rule placed; grammar-constrained to the statement's line ids, never sees numbers, confidence capped so every suggestion is reviewed. Measured against the same code without it (#7) | 83.2% | 2.2% (53 of 2,451) | 4.6% | Yes, optional. The model's own placements were right 90.5% of the time (296 of 327); wrong values caught rose from 68.8% to 80.3%; review rate rose from 32.9% to 36.9%; 306 calls, about 10 s of local GPU time per filing, $0 |

Known measurement limitation (fixed in #4): when a filing tags a row with a
company-specific concept, the answer key does not know which template line that row feeds, so the
key's total for that line can be incomplete and a correct spread value is scored wrong (seen on
Apple's working-capital line: the key misses "vendor non-trade receivables").
