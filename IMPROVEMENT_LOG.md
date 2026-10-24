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
| 10 | Red-team fixes (15 findings, see THREAT_MODEL.md); table context stops at the previous table; scorer counts a missing value as caught only when a flagged row prints it; key leaves total non-operating income unjudged when its parts are tagged | 79.6% | 2.7% (69 of 2,520) | 4.4% | Yes. Final measurement on the same code: holdout 73.5% right, 3.3% silent (70 of 2,100, likely 2.6-4.2%), 6.2% silent omissions; with the local model, holdout 75.0%, 2.9% (61 of 2,086), 4.1%, and wrong values caught 81.5% -> 86.7%. Reviewer workload: median 21 open review items per filing (25 with the model) |
| 11 | PDF reader rewrite (parallel agent; printed SEC 10-Ks 43.3% -> 77.1% right, synthetic PDFs 91.3% -> 97.3%) and its recommendations for detection and structure; release measurement | 80.0% | 2.8% (70 of 2,542) | 3.9% | Yes. Release numbers: holdout 73.5% right, 3.2% silent (68 of 2,100), 5.3% silent omissions; with the local model 75.0%, 2.8% (59 of 2,086), 3.8%. Synthetic 97.0% right, 6 silent errors in 13,452 auto-accepted values |
| 12 | Experiment: a failed check flags only its printed total, inputs with weaker provenance and lines named in its hint (the check still blocks approval) | 80.0% | 3.1% (95 of 3,061) | 3.9% | **Reverted.** Right values sent to review fell from 30.5% to 16.3%, but wrong values caught fell from 68.2% to 56.8% and silent errors rose from 70 to 95: the newly silent values were confident exact-alias mappings that were wrong, which provenance cannot tell apart from right ones |
| 13 | Scorer: PDFs and Excel locate the key's unplaceable rows by label, period and value (no HTML cell paths), so their "unjudged" values stop counting as wrong | PDF: 80.5% | PDF: 3.3% (87 of 2,650) | PDF: 2.6% | Yes. A measurement correction: printed SEC 10-Ks were 77.5% / 7.0% only because 174 values the key cannot judge were scored wrong |

Known measurement limitation (fixed in #4): when a filing tags a row with a
company-specific concept, the answer key does not know which template line that row feeds, so the
key's total for that line can be incomplete and a correct spread value is scored wrong (seen on
Apple's working-capital line: the key misses "vendor non-trade receivables").

## Next (ranked by expected value per hour)

1. **Measure ROI for real.** Time 3+ documents spread by hand and 3+ reviewed in the tool (the ROI page's timer), by an
   analyst, on documents like the organisation's own. Until then, time saved is "not measured" on purpose.
2. **Cut reviewer workload without hiding errors** (one attempt reverted, #12). A failed check flags every line it touches (bs_assets_parts flags
   ~28 correct values per wrong one on the dev split). Narrow the flags to the lines the hint implicates (the row whose
   amount equals the difference), measured on dev: the catch rate must not fall.
3. **Mapping recall on unseen filings** (holdout 73.5% vs dev 80.0%): the gap is mostly long-tail labels. Options:
   grow aliases from reviewer memory across documents; run the local model on catch-all mappings too (not only
   unplaced rows) as a second opinion.
4. **PDF silent errors** (3.3% on printed 10-Ks after the scorer fix #13, vs 2.8% in HTML): formerly partly the scorer (PDFs cannot
   use the "unjudged" correction because it matches HTML cell paths; match on label, period and value instead), partly
   real (sign and section cues are weaker in PDFs).
5. **OCR for scanned statements** (refused today): an open-source OCR model behind the same `DocumentIR`.
6. **Deployment basics**: SSO and roles, retention and deletion, a server database, a connector to the organisation's
   document store, the model behind the organisation's approved endpoint.
7. **Restatement detection across filings**: compare a prior-year column with last year's approved spread.
