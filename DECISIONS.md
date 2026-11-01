# Decisions

Each decision: what was chosen, why, and what would change it.

**D1. Read only what a person can see.** The HTML reader ignores inline XBRL tags, hidden elements
and `<script>`/`<style>`. Private-company statements have no tags, so reading them would make the
SEC results meaningless for the real use case; hidden text is a way to smuggle numbers or
instructions into a document. The evaluator reads the tags separately to build answer keys.

**D2. One layout engine for HTML, PDF and Excel.** Every reader produces rows of positioned
tokens; `layout.py` finds value columns from where numbers sit. Format-specific code stays in the
readers, and every fix to column finding helps all three formats.

**D3. Totals are found by footing, not by the word "Total".** A row is a total when it equals the
sum of the rows above it in every period. This catches misread numbers (a total that stops footing)
and tells the spread which rows are components, so "Products + Services + Total net sales" is not
counted three times.

**D4. Decimal end to end; rounding tolerance from the printed scale.** A statement in millions
rounds each number to the nearest million, so a check combining n printed numbers may be off by
n x 0.5 million without anything being wrong. Only printed numbers actually present count toward n.

**D5. Mapping is a cascade with a measured confidence.** Memory, alias, section rules, fuzzy
spelling, structure, then an optional model. Confidences were set from measured accuracy on the dev
split (alias 95%, fuzzy 67% -> 0.7, most section catch-alls ~56% -> 0.75 and reviewed, the
working-capital rule 98% -> 0.92). A value is auto-accepted only when nothing doubts it.

**D6. Checks and ratios are formulas in config, evaluated by a small safe language.** No `eval`:
formulas are parsed to a syntax tree and walked; only arithmetic, line names and four functions are
allowed. A deployment edits YAML, not Python, and a typo fails at load time.

**D7. Missing is not zero.** A formula whose inputs are missing is "not computable: X missing";
`_or_zero` exists only where absence genuinely means zero (no noncontrolling interests), and a ratio
with every input missing is never computed.

**D8. The model only suggests, and never sees numbers.** The local model gets labels and section
headers, answers from a grammar-constrained closed list of line ids, and its confidence is capped
below the review threshold. A reviewer's confirmation goes to mapping memory, after which the label
is placed deterministically. Off by default; the product works fully without it.

**D9. Corrections are events, never edits.** The computed spread is immutable; overrides,
resolutions and approval are replayed on top and logged. Remapping a row writes reviewer memory and
creates a new run (idempotency key includes the memory version), carrying corrections over and
logging that it did.

**D10. Approval is a gate, not a label.** It is refused while any blocking review item is open. An
assumed unit can only be resolved by a note that confirms the unit.

**D11. Ambiguity is refused, not resolved by guessing.** European grouping ("1.234.567"), and
three-decimal money amounts that could be European thousands ("719.147"), are unreadable review
items. Formulas without a saved result in Excel are not recalculated.

**D12. Evaluation keys are independent of the pipeline.** SEC keys find statement tables by tagged
concepts and map concepts to template lines with their own crosswalk (never the profile's aliases).
Values the key cannot judge (a company-specific tag) are "unjudged", not scored either way. Tuning
looks only at the dev split (by ticker hash); the holdout split is for measurement.

**D13. ROI separates observed, estimated, hypothetical and verified.** Time saved needs at least
three timed sessions in each mode; released capacity is hours, not cash, unless a finance owner
enters a cash-realisation share (default 0%); review time counts against the tool.

**D14. SQLite and files, no services.** A single-user local prototype needs durability and
transactions, not a server. The store's boundary (`store.py`) is where Postgres would go.

**D15. Python for the pipeline, React for the review UI.** The document-processing ecosystem is
Python (lxml, pdfplumber, openpyxl); the reviewer's workspace needs real interactivity (keyboard
grid, evidence panel), which server-rendered pages would make awkward.

## Platform decisions (2026-10-24, afternoon: reconciliation and invoice engines)

**D16. One platform, three engines, a thin shared core.** What is genuinely common (amount parsing and
tolerances, tables with row references, validated YAML overlays, fingerprints, the exception item and who
may resolve it, an append-only audit log, rates and reports) lives in `finops.core`; what a match *is*
stays in each engine. A single generic "matcher" for bank lines and invoice lines would make both worse.
The statement engine was not moved into the new package: it works, it is measured, and moving it would be
risk without user value. It shares the parser, the rates and the report format already.

**D17. Reconciliation matching: components and mutual best, not greedy.** Greedy best-pair-first is the
baseline and is kept as a strategy only for comparison. Candidate pairs are grouped into connected
components; a component with one record per side is a match; equal-sized components match only through
unique, mutual, clearly-better pairs; anything else is proposed as the best overall assignment (exact,
by dynamic programming over at most 12 records) and flagged ambiguous. Measured: on the round-amount
stress set greedy auto-accepted 7 wrong matches (3.0% of 234; re-measured 2026-10-29 on the current code: 3 of 233,
1.3%, likely 0.4-3.7%, `eval/reports/recon-recheck-2026-10-29`, the README's figure) and 18 of 51 pairings that needed a person
(re-measured: 18 of 57, 31.6%);
the component strategy auto-accepted none of either, at a cost of auto recall (93.4% vs 98.1%). No
optimisation solver: the exact assignment is only ever needed on tiny components, so a dependency would
add nothing.

**D18. Sums without a reference are proposals, never automatic.** A bank deposit equal to the sum of two
ledger receipts can be a coincidence (the evaluation plants exactly that). Only a shared reference makes a
one-to-many or many-to-one group automatic. Subset search is exact on integer cents, meet-in-the-middle
for 3 and 4 items, over all candidates in the window (truncating to the 12 nearest dates missed 5 of 9
true batch deposits; see the improvement log).

**D19. Idempotency by content.** Records are identified by the source's id (or a content hash) and carry a
content hash of their normalised fields; a run's key is files + effective configuration + engine version +
number of decisions. The same request returns the same run; a changed record invalidates the decisions
that used it, visibly (`DECISION_INVALIDATED` blocker), instead of silently keeping or dropping them.

**D20. Invoices: rules, not a model.** Header fields and line items on text-layer PDFs are read by label
and position rules with field-level evidence; arithmetic, matching and policy are code. No language model
reads an invoice, so text inside one ("SYSTEM: pre-approved") is inert (there is a test). The measured
weakness is unseen wording (36% of header fields on a layout never seen in development), and the remedy is
configuration (`extra_labels`, `extra_columns`), measured back to 100% on the same set. A local model
now *drafts* such wording for a person to approve (D27); it never runs inside invoice processing.

**D21. Eligibility is the ceiling.** Extraction, arithmetic, matching, policy eligibility and authorization
are separate statuses. The best an invoice can reach is "eligible for approval"; authorization is always
"not authorized here". Nothing pays, approves or edits vendor master data.

**D22. Bank-detail changes: block, mask, separate duties.** A bank account on an invoice that differs from
the trusted vendor master is a blocker; with no trusted baseline the outcome says it cannot be verified.
Account numbers are masked on intake and compared through a keyed HMAC (a plain hash of a 12-digit number
can be reversed by brute force). Resolving needs "verified_independently", a note describing the
call-back, and a person other than the uploader.

**D23. Who may resolve.** Exceptions and decisions need a named reviewer; "system", "model", "ai",
"assistant", "local-user" and similar are refused. A blocker needs a written note. This is the structural
guarantee that a generated explanation can never close an exception.

**D24. Synthetic answer keys, written by the generator.** Each engine's generator decides the truth while
writing the files (which records belong together, which problem each case plants, whether a person must
see it); nothing in a key is computed by the engine being graded. Dev and holdout use different seeds; the
reconciliation stress set repeats round amounts; the invoice "unseen" set uses a layout the extractor was
never developed on. The limitation stays: the same author wrote generator and engine.

**D25. ROI per engine, no double counting.** Each engine's estimate covers its own task (ticking off bank
lines, keying invoices); the same problems are investigated with or without the engine, so only the work
the engine settles counts as released time. Rates are labelled observed-on-synthetic; minutes are
placeholders until timed; no external benchmark is imported because none was verified.

**D26. The CORD receipt dataset is not used.** CORD (NAVER Clova AI; CC BY 4.0 per its GitHub repository, checked
2026-10-24; the public v2 release has 800/100/100 train/validation/test receipts) is scanned Indonesian receipts
annotated for post-OCR parsing: no purchase orders, no goods receipts, no vendor master, and images that
need an OCR engine this build does not have. It cannot measure three-way matching, and receipt
layouts are not invoice layouts. The invoice engine is measured on its own synthetic sets instead; CORD
(or FUNSD, SROIE) would become relevant only with an OCR front end, and their licences would be checked
again at that point.

**D27. A model drafts configuration; it does not process invoices.** The one place a language model earns its
keep here is turning an unknown supplier template into wording configuration: reading "Our Ref." and "Your Ref."
and knowing which is the invoice number is language, not arithmetic. So the model (local, $0) is used offline, on
a few sample invoices, with candidates chosen by rules, values reduced to their shape, answers constrained to a
closed list, and output written as an unreviewed draft file. Measured on a layout created after the method was
frozen: 11 of 12 mappings right, and the one wrong mapping made invoices fail closed rather than pass. Run-time
extraction stays deterministic, so every processed invoice is explainable without the model.

**D28. Partial matches are proposals with an open balance, decided last.** A same-reference pair far apart in
amount is either a partial payment, an overpayment or a keying error; only a person can tell which. Proposing it
(rather than only flagging it) gives the reviewer a one-click decision and keeps the open balance in the totals;
running it after every other layer means a partial can never take a record that a sum of several explains.

**D29. A held invoice reserves what it bills.** Counting only cleared invoices against a PO let a second invoice for the
same goods pass while the first waited for review (found by the red-team review). Every invoice that is not rejected
(and not an open exact duplicate) now reserves its quantity, and any decision re-checks the invoices that came after
it. The cost is that a legitimate second partial invoice may wait while the first is reviewed; that is the safe side.

**D30. Answer keys use the filing's own arithmetic (statements, 2026-10-24 evening).** When two tagged concepts land
on one template line, the key used to add them unless one visibly equalled the sum of the others, so a total and
its main part were counted twice (Walmart's revenue key was about twice its revenue). The filing's calculation
linkbase says which concept adds up into which, so the key keeps the total and drops the part. Three exceptions,
each from a checked case: a balance-sheet total that also adds another template line (cash and short-term
investments, when short-term investments is its own line) keeps the part; the cash-flow statement's opening and
closing cash keep the total, because that statement reconciles cash including restricted cash; and net income
available to common shareholders is a fallback for net income, never preferred to it, because it is net income
less preferred dividends. This is a change to the measurement, not the engine: it was measured on the same engine
output before and after (IMPROVEMENT_LOG #16), and the linkbases are cached beside the filings so the keys can be
rebuilt offline.

**D31. Don't trust the parser's edge cases; test where the libraries differ (2026-10-24 evening).** An outside run
on Linux found that lxml's Linux wheels (libxml2 2.14) stop at the first `</html>` while the Windows wheel (libxml2
2.11) reads on, so the same code dropped a statement on one platform only. Pinning lxml below 6 would have hidden
it until the pin had to go. Instead the reader splits a file into its documents itself, and CI runs a fresh install
on Linux with the newest allowed versions and the oldest allowed lxml. In the same spirit, "hidden" now follows CSS
inheritance for font size rather than treating `font-size:0` as hiding a whole subtree (D1: read only what a person
can see).

## Platform expansion (2026-10-24, night): which capability next

**D32. The next capability is a data-quality gate, chosen from eleven candidates by an audit of the repository.**
The mandate offered eleven candidates (numbered 4 to 14 there). The audit asked what blocks a real company from
using what exists. The answer was in the engines' inputs: the invoice engine loads its vendor master and purchase
orders with no validation at all (`invoice/master.py`). A second row with the same vendor id silently replaces the
first, a PO naming an unknown vendor is accepted, one unreadable number stops the whole load, and nine of the twelve
routing numbers in its own synthetic master fail the ABA checksum unnoticed. Reconciliation validates its two
files, but only for its own purpose. Nothing checks data between systems, and every engine trusts its inputs. So
the gap is a shared capability, not a fourth workflow.

Scores are judgement, 1 (poor) to 5 (strong). They are a structured opinion, not a measurement.

| Candidate | Value | Adds to what exists | Leverage | Measurable | Feasible here | Upkeep | Verdict |
|---|---|---|---|---|---|---|---|
| 4 Data-quality gate | 5 | 5 (nothing validates inputs) | 5 (feeds AP today; reuses the whole core) | 5 (injected faults + independent sets) | 4 | 4 (config only) | **Built** |
| 9 Spreadsheet risk scanner | 4 | 4 | 2 (stands alone) | 5 (synthetic workbooks) | 4 | 4 | Next (see IMPROVEMENT_LOG, gate section) |
| 5 Process mining | 4 | 4 | 2 (own data model) | 3 (few known-answer logs) | 2 | 3 | Later, as its own module |
| 8 Variance commentary | 3 | 3 | 3 (extends spreading) | 3 | 3 | 3 | Later: an extension of engine one, not a product |
| 7 Duplicate merging | 4 | 2 (the gate already flags duplicates for review; merging is the risky half) | 3 | 3 | 3 | 2 (Splink means DuckDB or Spark, plus model tuning) | Partly covered; merging deferred |
| 6 Contract register | 3 | 2 (overlaps the compliance reviewer) | 1 | 2 | 2 | 3 | No: legal interpretation risk, overlap |
| 10 Security questionnaires | 3 | 1 (the archive assistant already answers from sources with checked citations) | 1 | 3 | 3 | 3 | No: overlap |
| 11 Inbox triage | 3 | 1 (existing n8n workflows) | 1 | 2 | 3 | 3 | No: overlap |
| 12 Regulatory monitor | 2 | 2 | 1 | 1 (no ground truth) | 2 | 2 (sources change) | No |
| 13 Counterparty watchlist | 3 | 1 (overlaps the bankruptcy monitor) | 1 | 2 | 2 | 2 | No: overlap |
| 14 Competitor pricing | 2 | 1 (existing n8n competitor-watch work) | 1 | 2 | 2 | 1 (site terms, scraping limits) | No |

Libraries considered for the gate: pandera and Great Expectations (DataFrame validation), and frictionless
(table schemas). None was adopted. They validate a table; they do not hold a record for a named person, replay
that person's decision on the next run, keep bank numbers out of the logs, or decide from the last accepted
version. Those are this gate's real work. Two of them would also bring pandas into a codebase built on Decimal and
`finops.core.tabular`. What the gate needs from a library it already had: rapidfuzz for name similarity, openpyxl
for workbooks. Splink (candidate 7) is the right tool if merging is ever built, and only then.

**D33. The gate flags; it does not fix, merge or guess.** Each choice below follows from "a wrong record loaded is
worse than a record held":
- Rules are a closed set of declarative checks in YAML (require, forbid, pattern, compare, each with a `when`),
  not an expression language. A finance analyst can read every rule, and none can run code.
- Normalisation is recorded change by change, and lossy steps are refused rather than applied. `digits_only` removes
  only spaces and hyphens. Excel's scientific notation (`6.70913E+11`, last digits already lost) is rejected by
  name. An earlier version stripped every non-digit, and an independent test set showed it turning a mangled
  account into a different, valid-looking number.
- Duplicates are flagged for a person, never merged. Two similar names with different tax ids are two companies;
  similar names without one are held. Identical copies of one record load once, because there is nothing to choose.
- A changed bank account, routing number or tax id is held against the last accepted export, whatever the source
  says. While it is held, the last accepted version stays in force, so AP keeps paying the account someone verified.
  The exception: when the held version blocks or deactivates the vendor, the old one is not revived.
- People decide with their name and a reason. Only records held for review can be released; definite errors must be
  corrected, and a correction is checked again by the same rules. Whoever corrected a record cannot release it, the
  same segregation of duties as the invoice engine's bank-change control (D22).
- Opening a spreadsheet must not run anything. Text that starts like a formula is held, and the quarantine report
  writes it as plain text. The cost is measured, not hidden: a real company called "@Home Supply" is held too.
- No AI in the gate. The mandate allowed a model for suggesting mappings and normalising free text. Every mapping
  here is two lines of YAML a person writes once per source, and a model's guess would need the same review. If
  free-text normalisation is ever needed (addresses, say), it belongs in a draft step whose output a person reviews,
  as with invoice wording (D27).

## Spreadsheet risk scanner (2026-10-24, night, second capability)

**D34. The scanner proves a finding from the workbook's own structure, and is quiet otherwise.** Devin asked for
the next ranked capability (D32: candidate 9). The mandate's test was "precise, actionable findings rather than
noisy warnings", so where precision and recall conflict, the choices below take precision:
- Read, never write or calculate. Bytes in memory, two openpyxl reads (formulas, saved values); no Excel, no
  LibreOffice, no formula engine. A calculator would let the scanner check values, but it would mean running a
  workbook's logic, and no free one calculates every Excel function the way Excel does. Saved values are what Excel
  showed; a file without them skips those checks and says so.
- Compare copies in relative form. `=F14*(1+$B$2)` in G14 and `=G14*(1+$B$2)` in H14 are the same formula; one that
  is not is the finding, with the formula its neighbours imply. This is the idea behind Excel's own
  inconsistent-formula flag, applied only inside a run that agrees on both sides, so the edge of a block (actuals
  then forecast, a full-year column, an opening balance) is never compared. One agreeing cell on each side counts
  only for a single odd cell, and never for two totals of the same shape. A column or row that breaks the pattern
  in most of the lines crossing it (a half-year column between quarters, actual interest and tax rows between
  subtotals) is the layout, not a mistake: an anomaly at most. Most, not several: three unrelated mistakes that
  happen to share a column are still three findings.
- Three severities, decided by certainty, not importance: "error" is broken whatever the author meant, "risk" is
  probably wrong, "anomaly" is often deliberate. Anomalies are shown but not counted as findings, and a company can
  move a kind between severities in configuration.
- One finding per mistake. A total row whose every column omits the same item is one problem copied across, as an
  analyst would count it; thirteen findings would be noise.
- Double counting is defined by what amounts are made of: a sum of other cells (only SUM and +) is made of those
  cells; anything else (a growth formula, price times quantity, a single link) is an amount of its own. Two parts of
  one sum that share a part count something twice. A shared input such as a rate never makes two amounts overlap.
- Version comparison aligns rows and columns first, like a text diff, so an inserted row is one non-material change
  rather than a change to every formula below it.
- Reviews carry to the next version by a key built from labels (sheet, row label, column heading, formula in
  relative form), not the address, and lapse when any of them changes. A definite error cannot be dismissed.
- No AI. The mandate allowed a model where it adds measurable value; nothing here is a language problem. A model
  could word the explanations better than the template sentences, but a person can check a template sentence
  against the cell, and a model's sentence would need that same check.

## One uncertainty policy (2026-10-25, overnight)

**D35. Nothing is accepted without a person on a confidence nobody measured.** Each engine used to decide in its own
way: statement mappings carried hand-set confidences (D5's numbers, typed into the code and the profile), reconciliation
auto-accepted whatever rules the profile listed, and the other engines had no confidences at all. The shared policy
(`finops.core.policy`) now says:
- **Every finding has one shape**: blocking or informational, the reason, the evidence, the required action, and the
  rule, check or method that produced it. Each engine has an adapter (`as_findings`, or `from_exception` for the
  shared exception item). "Blocking" means it stops automatic acceptance of what it is about (a statement warning or
  blocker, an invoice exception above info, a held or rejected record, a spreadsheet error or risk); approval itself is
  still stopped only by blockers (D10).
- **Automatic acceptance has three possible bases.** *Calibrated*: the method's measured accuracy, whose 95% Wilson
  lower bound must clear the engine's bar (statements: the old 0.80, and 0.90 for critical lines; reconciliation: 0.98
  precision). *Person*: a named reviewer decided this exact case before (mapping memory). *Derived*: a total of rows
  that each cleared their bar takes their lowest confidence. A method never measured is reviewed: the policy fails
  closed. A model's own stated confidence is never a basis, and a model's suggestion is always reviewed whatever its
  measured accuracy (D8 stands). Deterministic checks are not confidences and are untouched.
- **The lower bound, not the point estimate.** A rule right 1 of 1 times is not a 100% rule. The point estimate would
  have let `catchall:revenue` (1 of 1) settle values alone; the lower bound (21%) does not, and a rule earns automation
  as its outcomes accumulate.
- **Calibration is a script, and records its data.** `scripts/calibrate.py` refits each method from labelled outcomes
  (the SEC dev answer keys for statement mapping, one outcome per mapped row; 30 generated reconciliation sets no
  evaluation uses) and writes `config/calibration/<engine>.json` with the datasets and their versions, the commit and
  the outcome count per source. Reviewer decisions can be added as labelled outcomes (`--outcomes`, JSONL) once there
  are enough.
- **Measured** (IMPROVEMENT_LOG #19, O4, O5): statements on dev, silent errors 60 -> 59, wrong values caught 162 -> 163
  of 222, at the cost of 48 more right values sent to review (median open items per filing 21 -> 24); the holdout,
  measured once: silent errors 55 of 2,139 -> 49 of 2,101, caught 366 -> 372 of 421. Reconciliation: every report
  identical (every configured rule clears 0.98 today); what changes is that a newly configured rule proposes until
  it is measured. The bar of 0.98 was chosen after seeing that the current rules clear it, which is said here rather
  than presented as an independent choice.
- **What would change it**: reviewer decisions in volume (calibrate on the organisation's own outcomes, not the SEC
  dev split), or a bar a credit or audit function sets for itself.

**D36. Remember each company: its approved spreads are evidence, never something to overwrite.** Most filers come back
every year, and last year's approved spread is the best evidence about this year's comparative column
(`spreader.company`, IMPROVEMENT_LOG #20).
- **Identity.** A document belongs to a company through an identifier the uploader gives (any id an organisation uses),
  or, for an SEC filing, the CIK on its cover page (`dei:EntityCentralIndexKey`). That reads one tag for
  identification only; every number still comes from what a person can see (D1).
- **What is kept.** On approval, every value (append-only table `approved_values`) and the mapping of every placed row
  (`company_mappings`, append-only too). Reopening a spread adds a withdrawal; nothing is updated or deleted, and
  database triggers refuse it. A document is never compared with its own approvals.
- **A corrected line confirms nothing behind it.** If the reviewer corrected a line's value before approving, the rows
  feeding that line are not remembered: the correction says they were placed wrong. The first evaluation remembered
  them and three values went silent the next year; with the rule, none did.
- **Reuse is calibrated, not trusted.** The company's mappings come first in the cascade (`memory.company`) with their
  measured accuracy (1,464 of 1,466 rows right on dev, at least 99.5%), under the same policy as every rule (D35).
- **A difference is a question.** Any line that differs from an approved value for the same period beyond rounding gets
  a warning that says what it most likely is: a misread (a power of ten, a flipped sign, another period's or another
  line's approved value), a reclassification (lines that move by equal and opposite amounts) or a restatement (columns
  headed "as restated", "recast", "revised"), or, most often, that it cannot tell. Measured with the keys, "misread" is
  usually right (19 of 20 on dev, 120 of 129 on the holdout); "restatement" is not reliable (3 of 5 on dev, 6 of 16 on
  the holdout); most items say they cannot tell. The cover page is not read for the restatement words: its standard
  "new or revised financial accounting standards" sentence made every filing look restated.
- **What would change it**: reviewer decisions on these items (a calibrated classifier instead of rules), the notes to
  the financial statements (where restatements are explained), and a sign-in so the identity of the approver is
  verified (THREAT_MODEL T38).

**D37. XBRL tags as a second reader: opt-in, a flag and never a vote, and never graded by its own source.** Public
filings tag the printed numbers, and a printed number whose tag agrees is safer than either alone
(`spreader.second_reader`).
- **D1 still holds.** The printed-number reader is the reader. The tags are read only when `SPREADER_XBRL_CHECK=1` (or
  `run_eval.py --xbrl-check`), and only to compare, cell by cell: the magnitude after scaling, and the period. The tag's
  sign is not compared, because it follows the concept's convention rather than what is printed. Opening and closing
  cash, printed in a full-year column and tagged as balances at a date, agree when the date is the column's end or
  start.
- **Disagreement flags; agreement does nothing.** A disagreement is a warning on that value. Agreement is not a basis
  for accepting values alone (D35): that would need calibration against outcomes, and the only outcomes available are
  the answer keys built from these same tags.
- **Measured without the keys, and labelled so** (`scripts/eval_xbrl_check.py`, report `xbrl-check`). The readers agree
  on 96.8% of tagged printed numbers on dev and 91.7% on the holdout. In a random sample of 30 disagreements, checked
  against the printed filings (`eval/xbrl-check/verdicts.json`), the tag was right 29 times; the printed reader once
  (McDonald's tags its share count without a scale). The sample is clustered: 8 filings, Deere alone 11. The marginal
  value is small on these filings: all 30 sampled values had already been sent to review by the tag-blind engine, and
  of 646 disagreements only 24 were on values it had not flagged (19 of them Home Depot's "Fiscal 2023" columns dated a
  year early, a silent error worth fixing in the reader).
- **Why not more.** Tags exist only for SEC filers' own filings; a borrower's PDF or management accounts have none,
  and the product must work the same without them. The mode is an extra check for public filers, not a substitute for
  reading.
- **What would change it**: independent outcomes (reviewer decisions on flagged values) to calibrate agreement as
  evidence; then agreement could become a basis for automation on SEC filings, measured like any other method.

**D38. Banks, insurers and IFRS are overlays that add lines, never remove them.** A large client base includes banks,
insurers and IFRS reporters on day one. Each is a configuration overlay on the commercial template
(`config/profiles/us-bank.yaml`, `us-insurer.yaml`, `ifrs-commercial.yaml`), with one engine change: an overlay may add
lines (`add_lines`) but not redefine or delete a template line, so a bank's spread still has every commercial line
(empty where a bank prints nothing) and stays comparable. Industry identities are checks in the overlay (net interest
income; loans net of the allowance; revenue minus claims and expenses). New lines are mapped by the same calibrated
rules (D35); a catch-all on a new line has no measured accuracy yet, so its rows are reviewed.
- **Measured honestly as a smoke test**, not a rate: three filings per overlay, the wording written from the first and
  hand-checked on the other two (`eval/coverage/checks.json`). Banks: every value checked on the two unseen banks was
  right (19 of 19), one bank's net income missing. Insurers: the unseen insurers expose the limit of wording written
  from one company (Allstate: half the key lines missing; Progressive: no consolidated statements in the document).
  IFRS: BP's 7 checked values right, revenue missing; Novartis placed almost nothing.
- **A general flaw found on the way and fixed:** a parent-company-only statement (SEC Schedule I/II) was spread as if it
  were consolidated when it was the only one in the document. It is now a blocker (IMPROVEMENT_LOG #23).
- **Not done: currencies.** Unit statements in euros or "$ million" are not recognised; the unit is assumed and
  flagged as a blocker, never guessed. Recognising them is engine work (the unit patterns are code, not configuration).
- **What would change it**: a few dozen filings per industry with answer keys (the SEC tags exist for banks and
  insurers too), so these overlays can be measured like the commercial template; and wording grown from reviewer
  memory across many borrowers rather than one source filing.

## Units, and learning from reviewers (2026-10-25, day)

**D39. A statement's unit is decided from evidence, through the uncertainty policy, at a bar of 80%.** A unit read
wrong by a factor of 1,000 makes every value in the statement wrong, so where the unit came from is a rule like any
mapping rule, measured and calibrated (`spreader/units.py`, `config/calibration/units.json`):
`scale.table` (a unit line at the table, in any wording), `scale.document` (a unit stated once for the whole
document, used only when every such sentence agrees), `scale.sibling` (the other statements' printed unit), and
`scale.none` (nothing found). A unit is accepted without a person only if its rule's 95% Wilson lower bound clears
80% (Devin's bar, 2026-10-25); otherwise the statement keeps its best guess and a blocking item shows the guess, the
evidence and the rule's record. `scale.none` is never accepted alone, however it measures.
- **Truth** is the filers' inline XBRL: each tagged money cell's value against what was read, per statement
  (`scripts/eval_units.py`). The fallback rules rarely fire for real, so each is also asked of every statement that
  prints its own unit, as if that line were hidden; those outcomes count **once per filing** (statements of one filing
  share their unit, so counting them separately would overstate the evidence). Dev: unit line at the table 188 of
  188; others' unit 68 of 68 filings or statements (at least 94.7%: trusted); document-wide sentence 8 of 8 filings
  (at least 67.6%: below the bar, so flagged with its guess until it has more evidence).
- **Holdout, once:** 157 of 157 table units right; Deere's 6 statements (no unit line at any statement) now carry
  "millions" from its notes, all right, still flagged; no wrong unit unflagged.
- **Wordings are pooled within a rule.** "(In thousands)", "$ in millions", "000s omitted" and "(In U.S. dollars)"
  are all a unit printed at the table: one rule. A first version gave "(In U.S. dollars)" a rule of its own; no dev
  filing prints it, so it had no measurement, failed closed, and sent 15% more of the synthetic corpus's values to
  review (6.2% -> 21.1%) for statements that state their unit plainly. Pooled, the synthetic review rate is back
  (`syn-units`); no SEC statement used that wording, so the SEC figures are unchanged.
- **Currency** is recorded, not converted: named in the unit line or headings ("EUR millions"), else a "$" in the cells
  (read as USD; every measured document is a US filing). A non-USD currency is a warning, statements in different
  currencies a blocker. A conversion needs a rate source and a rate date a person chooses, so none is made.

**D40. Every reviewer decision that judges a rule is written to an outcomes folder that calibration reads.** One JSON
line per outcome (`finops/core/outcomes.py`): engine, rule, right or wrong, how it was decided, who, when, and refs back
to the run. Default folder `var/outcomes/`, or `FINOPS_OUTCOMES_DIR`: connecting an organisation is pointing that at a
folder its own pipeline collects, and the line format is the contract. `scripts/calibrate.py --outcomes-dir` and
`scripts/eval_units.py --calibrate --outcomes-dir` refit on it alongside the answer keys, reporting outcomes per source.
- **Statements:** at approval, every row the reviewer left alone is right for its rule; a remapped or excluded row is
  wrong for the rule that placed it; rows on corrected lines are not judged (reading or mapping may be at fault); a
  statement's unit is wrong if a value in it was corrected by a power of ten. Rows placed by the reviewer's own memory
  are not counted (they would only confirm the reviewer to themself).
- **Reconciliation:** accepts and rejects are recorded but **not fitted on**: nothing confirms the automatic matches
  nobody undid, so the feed would only ever lower a rule. It becomes usable once a reconciliation has a sign-off.
- **Weak evidence is labelled:** approval without a change is weaker than a correction (a busy reviewer may approve
  what they did not check); each outcome says how it was decided and the calibration file lists sources.
- **Rebuildable:** the folder is written as decisions happen and never stops one; `scripts/export_outcomes.py` rebuilds
  the statement outcomes from the store's append-only events.

**D41. Bank and insurer answer keys come from the tags through an industry crosswalk overlay, independent of the
profiles' wording.** D38's "what would change it", done: 21 banks' and 24 insurers' latest 10-Ks (none of the six
smoke-test filers), downloaded by `scripts/fetch_industry.py` with their calculation links and split by ticker hash.
The answer key reads the concepts the filer tagged, not the printed labels, so it is as independent of the overlays as
the commercial keys are of the template. The commercial crosswalk is not enough: it reads a bank's
`InterestExpense` as non-operating interest expense and the revenue concept (which banks tag on one component,
service charges) as revenue. So `ixbrl_truth.INDUSTRY_CROSSWALK` adds, per profile id, concepts for the industry
lines and sets to "unjudged" the base meanings that are wrong for the industry; with any other profile nothing
changes (six commercial keys rebuilt byte for byte).
- **Tuned on dev only; holdout measured once.** Dev filings shaped the crosswalk and the overlay wording; the holdouts
  were measured once at the end (B5). Results, with 95% Wilson intervals: banks dev silent error rate 7.5% -> 4.8%
  (31 of 645), holdout 6.2% (46 of 740; 4.7-8.2%); insurers dev 2.4% -> 2.6% (15 of 577), holdout 7.8% (58 of 744;
  6.1-9.9%). Holdout is worse than dev for both: wording grown from ten filings does not yet generalise, and the
  holdout figure is the one to quote.
- **Re-measured 2026-10-26 on the merged code** (commit 957686e, `eval/reports/stmt-<industry>-<split>-merged`), the
  figures the README quotes: banks dev 4.2% (31 of 737; 3.0-5.9%), holdout 5.9% (46 of 782; 4.4-7.8%); insurers dev
  3.1% (20 of 636; 2.0-4.8%), holdout 7.8% (58 of 744; 6.1-9.9%). The same wrong values, out of more values accepted
  alone. The figures above are the first measurement, kept as it was made.
- **What the keys cannot see.** Three dev banks give nothing to grade (statements in an exhibit, or no table the reader
  accepts); a combined income and comprehensive income statement is never a candidate (B4, engine-wide).
- **What would change it**: the B4 detection change measured on the commercial sets; more filings per industry so a
  tuning round can use a fresh dev half; and the holdout's largest silent groups (an insurer's common stock and APIC,
  investing cash flows) worked on with a new holdout, since this one has now been seen.

**D42. Scanned PDFs are read by local OCR when an optional extra is installed, through the same reader as a text PDF,
and every number the recogniser was unsure of goes to review.** `pip install -e .[ocr]` adds rapidocr-onnxruntime
1.4.4 (PP-OCRv4 models in ONNX, run on the CPU; about 210 MB with onnxruntime, opencv-python, numpy and shapely; no
system program, no network, no paid service). Without it a PDF with no text layer is refused, now with how to install
it. With it (`spreader/ingest/ocr.py`):
- **Same reader.** Each page is rendered at 200 dpi (a common office-scanner setting) and recognised into words with
  boxes in PDF points, with the keys the text-layer reader uses, so lines, cells, wrapped labels, statements, units,
  periods, review and the evidence box on the page image are the same code. A document warning says it was read by
  OCR. Scans of more than 60 pages are refused (`SPREADER_OCR_MAX_PAGES`): reading costs seconds per page.
- **Fail closed on digits.** Every token carries the recogniser's confidence (`SourceRef.ocr_confidence`, lowest word
  in the cell); review raises an "unreadable" item on any value read below 90% (`SPREADER_OCR_MIN_CONFIDENCE`), so it
  is never accepted alone. Numbers are never edited: a cell that does not read as a clean amount stays text and the
  value is missing and flagged, not guessed. A recogniser failure on a page is a refusal, not an empty spread.
- **Text repairs, letters only.** The recogniser drops spaces in tight text ("Researchanddevelopment"): a run of
  letters is split only when known words cover it (vocabulary: the template profiles plus statement and date words),
  with at most one unknown stretch (a company name) in a long run. A month glued to its day, a comma or bracket glued
  to the next word, and a lone "S" whose next word on the line is an amount (the "$") are repaired.
- **Deskew.** The recogniser's boxes come back square on a tilted scan, so the tilt is measured on the image (the
  angle within 2 degrees with the sharpest horizontal ink profile; blank pages and marginal gains left alone) and the
  page rotated straight before reading.
- **Measured on scans made from the dev filings** (`scripts/make_scans.py`): each printed 10-K cut to its statement
  pages plus two on each side (33 packages; 7 filings had no statement pages found by the text reader), as a 200 dpi
  grey scan with noise and JPEG, and the same tilted 0.3 to 0.8 degrees. Tickers split by hash: settings were changed
  only while looking at the tune half (15); the check half (18) was measured once at the end. Check half, silent error
  rate (wrong values accepted alone): text layer 2.4% (38 of 1,589), clean scans 5.2% (66 of 1,281), tilted 4.2% (54 of
  1,292). On both halves none of the silent errors OCR added is a misread digit; they are table structure (a row
  counted twice, debt rows confused, a small common-stock line lost), plus label-matched rows the scorer cannot place
  on a scan (it finds a PDF's company-specific rows by printed label). The scorer was not changed.
- **Decided 2026-10-26 (Devin): every value read from a scan goes to a person** until OCR has been measured on real
  scans (`ocr.REVIEW_ALL`, on by default; `SPREADER_OCR_REVIEW_ALL=0` restores the 90% confidence flag only). On the
  check half this took the silently wrong values from 66 to 0 (clean scans) and 54 to 0 (tilted), with the share
  right unchanged (77.4%, 79.8%); the cost is that an analyst checks nearly every value of a scanned statement (only
  values the pipeline calculated, 34 and 38, are still accepted alone). Turning it off needs an outcome-based
  calibration (D35/D40) on real scans.

## Production readiness (2026-10-28, night)

**D43. Identity is established by the server: OpenID Connect for organisations, a labelled development mode for one
machine, role-based permissions, separation of duties checked where the action happens.**
- **Problem.** The reviewer's name was the X-Actor header, typed into the app. Anyone could act as anyone, so every
  "second person" control (bank-detail verification, record release) and every audit entry rested on a typed name.
- **Choice.** Every /api route needs a signed-in principal and the route's permission (`spreader/auth_api.py`,
  `ROUTE_PERMISSIONS`); a route missing from the table is refused, so new routes start closed. Routes whose permission
  depends on the action check again in the handler (a statement action by type, an invoice resolution that verifies
  bank details, a data-quality release). The header is ignored; the actor is the server's principal.
- **Why OIDC.** It is the standard every enterprise identity provider speaks (Entra ID, Okta, Auth0, Keycloak, Google).
  The provider is configuration (`config/finops/auth/*.yaml`: issuer, client id, which claim holds roles, how the
  organisation's groups map to app roles, required tenant claims); two example organisations are included. Browser
  sign-in is the authorization-code flow with PKCE, a single-use state and a nonce, and a server-side session
  (HttpOnly, SameSite=Lax cookie; only its hash is stored; idle and absolute expiry; sign-out revokes). API clients
  send bearer tokens. Token checks use PyJWT (signature against the provider's published keys, issuer, audience,
  expiry, not-before, nonce, tenant; asymmetric algorithms only). The flow's few HTTP steps are ours; all
  cryptography and token parsing is PyJWT's and `cryptography`'s.
- **Considered.** Authlib (a full OAuth client): more than the flow needs and its Starlette integration wants signed
  cookie sessions as well. A reverse proxy doing sign-in (oauth2-proxy) and passing a header: simpler code, but the
  app would again trust a header, and only the proxy's configuration would stand between a request and an approval.
  A home-made username and password: a new credential store to protect, and the reason SSO exists.
- **Roles and permissions.** Permissions are a fixed list in code (`view, upload, edit, review, approve, export,
  audit, admin`); roles grant them in configuration (`roles-base.yaml`): viewer, preparer, reviewer, approver,
  auditor, admin. No base role both approves and administers, or approves and uploads. A user whose provider groups
  map to no role can do nothing.
- **Separation of duties** (`separation_of_duties` in the configuration; on by default until D51 turned it off): a statement spread is approved
  by someone other than whoever uploaded the document and anyone who corrected or remapped its values (read from the
  audit log). The existing second-person rules (bank details, released records) now compare verified identities.
- **Development mode** keeps the prototype usable on one machine: named test users with single roles. It refuses
  FINOPS_ENV=production and non-local host names, labels every response and the app, prefixes audit entries `dev:`,
  and its sessions are worthless once a provider is configured.
- **Scope and limits.** One organisation per deployment: every signed-in user with `view` sees all of that
  organisation's records (no per-record ownership yet). Roles are read at sign-in; a role removed at the provider takes
  effect at the next sign-in (sessions last at most 8 hours by default). Tested end to end with an in-process test
  provider (47 tests in `tests/test_identity.py` then; 49 since D51); **no live provider has been configured or tested**, so this is
  "implemented, awaiting validation", not production-ready SSO. The approval separation check runs just before the
  approval's transaction, not inside it; the only race is one user correcting and approving in two simultaneous
  requests, and a correction after approval is refused anyway.

**D44. The statement engine's audit log is append-only and hash-chained, like the platform's.**
- **Problem found.** The README called the statement audit log append-only, but the `events` table had no guard and
  no chain: any code path or tool could rewrite it. The platform engines' log (finops.core.audit) already had both.
- **Choice.** Schema 4: `events` gains `prev_hash` and `hash` (SHA-256 over the previous hash and the event's fields),
  and triggers refuse UPDATE and DELETE. Migration chains existing events as they are (`meta.chain_legacy_events`
  records how many): later edits to them are detected, earlier ones cannot be. `/api/audit/verify` (auditor) checks
  both logs.
- **Limit, stated plainly.** A hash chain detects a partial edit. Whoever controls the database file can rebuild the
  whole chain; detecting that needs the latest hash (`Store.chain_head()`) copied somewhere they cannot write
  (THREAT_MODEL T41). Not done yet.

**D45. Uploaded files are encrypted at rest by the app; the databases rely on volume encryption for now.**
- **Problem.** Every upload (statements, bank exports, invoices, master data, workbooks) sat in the data folder as a
  plain file: a copied folder or a stolen disk exposed them all.
- **Choice.** One small module (`finops/core/vault.py`) that every engine's file reads and writes go through:
  AES-256-GCM from the `cryptography` library, a random nonce per write, the file name bound in as associated data
  (a file swapped under another name does not decrypt), atomic writes. Keys come from `FINOPS_DATA_KEY_FILE`, a file
  outside the data folder (a key inside it is refused), one base64 key per line: the first encrypts, all decrypt, so
  `spreader vault migrate` rotates keys and encrypts files stored before. With `FINOPS_ENV=production` and no key, the
  app refuses to start. Keys are never printed (not in `repr`, logs or responses).
- **Not chosen now.** SQLCipher for the databases: it needs a native SQLite build on every platform and a different
  driver; the databases' content (spreads, notes, results) is covered by volume encryption in a deployment, which is
  also what protects backups of the folder. Field-level encryption of database columns: it would touch every query.
  Both are recorded as gaps in DATA_LIFECYCLE.md rather than claimed.
- **Cost.** Encryption adds microseconds per file; no new dependency (`cryptography` was already installed through
  pdfminer and is now also required by PyJWT).

**D46. Retention is configured per organisation, erasure removes a unit's content and keeps a minimal record, and
legal holds win.**
- **Problem.** Documents were kept until someone deleted files by hand (THREAT_MODEL T12); deleting the upload would
  have left the spread, the notes, company memory and the audit payloads behind, and nothing could stop a deletion
  that a legal hold forbids.
- **Choice** (`finops/core/retention.py`, `spreader retention ...`, `/api/admin/...` for administrators). The unit of
  deletion is what a person works on: a statement document, an invoice, a reconciliation workspace, a data-quality
  dataset, a workbook model. Erasure removes its files (unless a live unit uses the same bytes), extracted values,
  spreads, results, review notes, decisions, company memory and reviewer outcomes, and replaces its audit payloads with
  `{"erased": true}`. Kind, actor, time and hashes stay: the record that the work and the erasure happened.
- **Audit chains stay verifiable.** Both logs now chain a digest of each payload rather than the payload, so an erased
  payload leaves the chain intact while every other field stays covered. The append-only triggers allow exactly one
  change: an erased unit's payload becoming the erasure marker. Anything else (another field, another unit's payload,
  deleting an erasure record or a legal hold) is refused, and done around the triggers it is detected by verification.
- **Policy.** No universal period: the default deletes nothing automatically; an organisation sets days per engine
  (an example overlay uses about seven years). Every step is idempotent; an erasure is recorded as started before
  anything is removed and completed after, so an interrupted one is listed and finishes when run again.
- **Limits.** Platform audit events written before this change chain their payload directly and cannot be erased
  (reported, not hidden). The model cache and reviewer mapping memory are not erased with a document. Re-applying
  erasures after restoring an older backup is manual. Erasure needs one administrator; a second-person rule for
  erasure is a configuration to add when an organisation asks for it.

**D47. Several people at once: SQLite stays, actions merge when they do not collide, approvals refuse a stale
screen; backups are consistent snapshots with an audit anchor.**
- **Found.** The statement engine refused any action if the spread's review state changed while the action was being
  computed: no lost updates, but in a local load check (4 reviewers correcting one spread while 8 people read it)
  34 of 100 corrections were refused although they touched different cells. And nothing stopped someone approving a
  spread that had changed since they opened it.
- **Choice.** An action whose target nobody else touched is applied to the latest state (retried with a short
  jittered wait); an action on a value, item or approval someone else changed is refused, never overwritten. Every run
  shows a `version` (a fingerprint of its review state); approving or reopening with an `expected_version` that is
  no longer current is a 409 ("changed since you opened it"); the web app sends it. Separation of duties is checked
  inside the approval's transaction. Same load check afterwards, three runs: 100 of 100 corrections applied each
  time; worst run's 95th percentile 779 ms for a correction, 371 ms for a read, slowest correction 2.6 s
  (`scripts/load_check.py`, in-process, this machine).
- **Why not a server database now.** One SQLite file in WAL mode with immediate write transactions gives
  serialisable writes, foreign keys, unique constraints and an online backup API, with nothing to run. It fits one
  application server and a team-sized number of reviewers. Several application servers sharing data need a server
  database (PostgreSQL): the stores use plain SQL behind two small classes, but that move, its migrations and its
  tests are not done and nothing here claims them.
- **Backups.** `spreader backup backup <folder>` takes both databases through SQLite's online backup API (a consistent
  snapshot while the app runs) and copies stored files as stored (encrypted; the key is never copied), with a
  manifest of hashes and both chains' heads; `verify-backup` checks it without changing it. Restore is copying the
  folder back and verifying.
- **Anchors** (`spreader backup anchor <file>`, `check-anchor`): the latest event id and hash of both chains, kept
  where the database's owner cannot write. A chain rebuilt from an earlier point verifies on its own but cannot keep
  an anchored hash; the test rebuilds one and the anchor catches it. This narrows T41 to "changes after the last
  anchor"; how often to anchor, and where, is the organisation's choice.
- **Tenancy.** One organisation per deployment (D43); isolation between organisations is separate deployments and
  data folders, not rows in one database.

**D48. A model's placement blocks approval until a person confirms it; malformed model output is no answer.**
- **Found.** A row the local model placed raised a review *warning*, so a spread could be approved without anyone
  confirming the model's choice; D8 said every suggestion is reviewed, the code only noted it. And a model reply
  that was valid JSON but not an object (a list, a number) crashed the whole run instead of counting as no answer,
  and was cached.
- **Choice.** Model placements are now *blocking* review items: resolving one is the confirmation. Replies that are
  not an object with a string line are counted as errors, never cached, and the row is left unplaced and reported.
  The model is off by default, so the default results and the release gate are unchanged.
- **Inventory and risk register** for every model (mapping, invoice wording drafter, OCR) in MODEL_RISK.md, with the
  existing measurements (IMPROVEMENT_LOG #9, #14; D27; D42) and the failure tests in `tests/test_model_governance.py`.
- **Needs Devin's review**: this tightens a financial control (more blocking items when the model is on). Revert by
  restoring the warning severity in `review.py`; the test will then fail, by design.

**D49. The analyst pilot is a protocol plus guards, and its report refuses to conclude early.**
- **Gap.** The app could time by-hand and assisted sessions, but nothing stopped one analyst timing the same document
  both ways (the second pass is faster for reasons that have nothing to do with the tool), and nothing recorded how
  hard a document was or how experienced the analyst.
- **Choice.** PILOT_PROTOCOL.md: two comparable document sets, at least two analysts in a crossover, difficulty rated
  before the study, active time only, an independent quality check against answer keys or a second analyst, and a
  rubric. The app now refuses a second timing of one document by the same person, and records difficulty and
  experience (schema 5). `scripts/pilot_report.py` reports observed medians with ranges and the quality figures side
  by side, says PENDING until both arms have three finished sessions, and computes no money.
- **Status.** No analyst session has been run; nothing here is evidence of time saved.

**D50. Industry profiles declare which corporate checks and ratios do not apply; an organisation is one checked file.**
- **Found.** The bank and insurer overlays inherited every corporate check and ratio. The checks were harmless (all
  of them skipped for missing inputs on every dev filing), but some ratios were computed and shown: on the bank dev
  filings the previous profile reported debt-to-equity for 16 filing-periods, free cash flow for 15 and a debt total
  for 8, none of which means for a bank what it means for a company; on the insurer dev filings, days sales
  outstanding for 2 (`scripts/check_not_applicable.py`).
- **Choice.** A profile overlay may declare `not_applicable: {checks: {id: reason}, ratios: {id: reason}}`. Those stop
  running, the profile lists them with the reason (`/api/profile`), an unknown id or an empty reason is refused, and
  everything not declared stays exactly the base definition (tested). Lines are never removed, so spreads stay
  comparable. Bank: 8 checks, 14 ratios; insurer: 8 checks, 11 ratios, each with its reason in the YAML.
- **Measured.** Bank and insurer dev splits before and after: identical values right (840 of 1,026; 708 of 1,121),
  silent errors (31 of 737; 20 of 636), omissions and review load. The holdout halves were not re-measured: nothing
  that is scored changed.
- **Organisations.** `config/organisations/*.env` names an organisation's sign-in, statement profile, retention
  policy and payables policy; `spreader serve --org <file>` validates every named file with the engine's own loader
  before starting, refuses secrets in the file, unknown settings and a sign-in file for another organisation. Two
  examples differ in every setting (a bank on Entra ID with strict three-way matching and seven-year retention; an
  insurer on Okta with the defaults) plus the local demo.
- **Not done.** IFRS stays a smoke-tested overlay; no IFRS answer keys were built tonight (the template's IFRS
  presentation by nature, not function, needs its own checks before any accuracy claim).

## Who signs off (2026-10-28, day)

**D51. One analyst corrects and approves their own spread by default; two-person sign-off is a setting.**
- **Decided by Devin.** The mid-size companies this is aimed at pay analysts to spread and check documents well; a
  second analyst re-checking each one is not part of their flow. When an analyst submits, it goes through.
- **The flow.** The platform prepares the spread: it reads, standardises and checks the document and flags what it
  is unsure of. The analyst fixes the flagged items and approves. Their corrections and approval are recorded under
  their name, which is what the outcomes log and future golden sets learn from.
- **Choice.** A new `analyst` role holds `view, upload, edit, review, approve, export` (`roles-base.yaml`), and both
  `separation_of_duties` rules are off by default (`identity.py`, `roles-base.yaml`). The development sign-in has an
  analyst user (`ana`). Administering still never comes with approving.
- **Kept for later.** A larger organisation that wants maker-checker turns both rules on in its own sign-in file and
  uses preparer / reviewer / approver instead of analyst; `example-entra-id.yaml` is that setup, `example-okta.yaml`
  the one-analyst default. The test suite runs the strict setup so the rules stay tested
  (`tests/fixtures/auth-test.yaml`), and `test_by_default_one_analyst_uploads_corrects_and_approves_their_own_spread`
  checks the shipped default (it fails on the D43 default).
- **Unchanged.** D48: a value the model placed still needs a person's confirmation before approval, while the model
  learns. The payables and data-quality second-person checks (changed bank details, released records) are fraud
  controls on payments and master data, not on spreading, and stay.
- **Sign-in stays provider-neutral.** No identity provider is chosen. The code speaks OpenID Connect, which most
  providers support; Okta and Entra appear only in example files. A provider that only speaks SAML would need an
  adapter in front of the same roles.
- **Planned (Devin).** During a learning period before the model is relied on, run it alongside the analysts and
  record every case it would have flagged that the analyst let through. A reviewer later decides who was right and
  why, and those decisions teach the model the nuanced cases. Step 1 is D52.

## The model's learning period (2026-10-29)

**D52. In a learning period the model takes no part in spreading and gives a hidden second opinion on every row.**
- **Why (Devin).** Before the model is relied on, it should be compared with the analysts on real work: every row
  where it would have placed a line differently from what the analyst approved goes to a reviewer, who decides who
  was right and why. This is step 1 of 5: recording the opinions. Steps 2 to 5 (the disagreement list at approval,
  the review page, turning decisions into golden sets, memory and training examples, and the go-live report) follow.
- **Choice.** `SPREADER_MODEL_ROLE` is `live` (the default, the D48 cascade step) or `shadow`. In `shadow` the model
  is not in the cascade: runs record model `none`, keep the same idempotency key and produce the same spread as with
  no model. After a run succeeds, one background thread asks the model, independently of the rules, where each
  labelled row belongs (`spreader/shadow.py`, `LocalModelMapper.ask`: a line id, `none`, or no answer) and stores the
  answer next to the platform's placement and rule in `shadow_opinions` (schema 6), with an outcome (agree, disagree,
  no answer). One opinion per run and model. `spreader shadow` records opinions for runs spread earlier.
- **Kept from the analyst.** Opinions are never in a run payload, the document list or the run's history (the audit
  log keeps a count-only entry under `system:shadow-model`). An analyst who saw where the model disagreed would be
  anchored by it, and the comparison would measure nothing.
- **Never in the way.** The analyst does not wait for it, and a model failure or crash leaves the run untouched (the
  failure is logged). It sees what the cascade model sees: labels and section headers, never numbers. Erasing a
  document erases its opinions (D46).
- **Scope.** The model judges placement only, not values: wrong numbers stay the checks' job. The comparison here is
  with the platform's own placement; the comparison with what the analyst approved is step 2.
- **Found.** The cascade docstring and MODEL_RISK.md say a confirmed model placement goes to mapping memory. Only a
  remap or exclusion does; resolving the model's review item does not. To be fixed with step 4.
- **Tests.** `tests/test_shadow.py` (11): the spread is identical with and without it, every labelled row gets an
  opinion next to the platform's, failures and crashes leave the run untouched, one opinion per run, analysts never
  see it through the API, erasure removes it, "none" is told apart from no answer, the backfill asks once.

**D53. At approval, every row where the model would have placed the line differently becomes a disagreement for a
senior to rule on; without a ruling in 14 days, the analyst's answer stands.**
- **Decided by Devin.**
  1. A senior, with more years of experience, rules on each disagreement and has the final word.
  2. When the senior sides with the model, the model learns the senior's answer. If no senior rules in time, the
     analyst's answer stands; a wrong one is corrected over time by other analysts.
  3. The model checks every document by default; a share is a company setting, depending on what the company will
     spend to teach the model.
  4. The model goes live when seniors side with it at least as often as with the analysts, with enough rulings and a
     margin (z = 1.96) so it is not luck. A company may go live earlier with stricter confidence settings, so more
     goes to analysts and only routine work is automated; for the best accuracy it waits until the model does better
     than associate-level analysts. The pass mark is the company's call.
- **Choice (step 2 of 5).** When a run is approved, each of its opinions marked `disagree` becomes a row in
  `disagreements` (schema 7): the label, the analyst's line (the approved placement, `none` when the row was left off),
  the rule behind it, the model's line, who approved and when, and a deadline. The comparison is with the approved
  run's own placement, which already includes the analyst's remaps and exclusions. If the opinion arrives after the
  approval (it runs in the background), the comparison happens then. Reopening withdraws the run's open disagreements
  (a ruling already made stays); approving again opens them with the new approver and deadline. Rows where the model
  agreed or gave no answer are not disagreements.
- **Settings.** `SPREADER_SHADOW_REVIEW_DAYS` (default 14) and `SPREADER_SHADOW_SHARE` (default 1, every document;
  the sample is decided by the document's id, so all runs of a document are in or out together). Nonsense values are
  refused.
- **Deadline.** Listing the disagreements first settles the overdue ones: status `analyst_stands`, verdict `analyst`,
  recorded under `system:review-deadline` with a count-only audit entry. `spreader disagreements` lists them.
- **Kept from analysts.** No API route serves them; their audit entries are hidden from the run's history, like the
  opinions (D52).
- **Next (step 3).** The senior's page and ruling: a permission of its own; verdict analyst, model or neither with
  the correct line, a reason and a note; when the senior sides with the model, the approved spread is marked
  "corrected after review" and the analyst is told (Devin, Oct 29; a setting, on by default). The ruling columns
  already exist in `disagreements`.
- **Tests.** `tests/test_disagreements.py` (17; a nonsense setting stops the start rather than failing each upload):
  every differing row and only those, a late opinion still compared,
  reopen and re-approve, the deadline (not a second early), settings refused when nonsensical, the defaults, the
  sample's share and stability, hidden from analysts, erased with the document, the command.

**D54. A senior rules on each disagreement without knowing which answer is the model's; a wrong approved line shows
"corrected after review" to its analyst.**
- **Who (Devin).** A senior, with more years of experience, has the final word. A new permission, `adjudicate`, and a
  role, `senior` (`view, adjudicate, export`); a senior who also spreads holds both roles. Development sign-in has
  `sam` (senior).
- **The ruling.** On the page *Model disagreements* (`/disagreements`, shown only with `adjudicate`; API
  `GET /api/disagreements`, `POST /api/disagreements/<id>/rule`), the senior picks answer A, answer B, or neither and
  the correct line, a reason from a closed list (so reasons can be counted) and a note. A ruling is final. A ruling
  after the deadline replaces the analyst-stands default. Nobody rules on a spread they approved themselves.
- **Blind by default.** The two answers are shown as A and B, in an order fixed per disagreement and unrelated to whose
  each is, and the approver's name is hidden, until the senior has ruled. A senior who knows which answer is the
  model's can lean towards or against it; the go-live measure (D53, Devin's point 4) would then measure the senior's
  view of the model rather than the model. `SPREADER_BLIND_RULING=0` shows them. Not decided by Devin: chosen here and
  raised with him. Limit: the page does not link to the run while ruling blind, but a senior who also has `view` can
  still open the run and see the approved placement. Blind ruling keeps the source out of view; it cannot stop a
  senior who goes looking.
- **Corrected after review (Devin).** When the senior rules the approved line wrong (verdict model or neither), the
  run page shows the analyst which line, the approved and the correct line, the note and who ruled, and the document
  list marks the document. It shows while the run is approved and clears when the analyst reopens the spread to fix
  it. No email or message is sent: the analyst sees it in the app. `SPREADER_FLAG_CORRECTED=0` turns it off. No
  model id reaches the analyst.
- **Audit.** Each ruling is an audit entry under the senior (`ruling`: the disagreement, verdict, reason, whether it
  was late), hidden from the run's history like the opinions.
- **Not yet (step 4).** The model does not learn from rulings yet: that is the next step (memory, golden sets,
  training examples). The ruling's verdict, correct line, reason and note are what it will learn from.
- **Tests.** `tests/test_rulings.py` (14): only seniors, blind until ruled, A is not always the analyst's, choice to
  verdict, neither and its line, a reason and a note required, final, nothing to rule on after a reopen, no ruling on
  one's own approval, a late ruling, corrected after review until reopened, both switches, the audit chain. Checked in
  the browser: a senior ruled on the page, the analyst then saw the notice on the run and the mark in the list, and
  the analyst's menu has no senior page.

**D55. A senior's ruling teaches memory, calibration and the model's prompt, becomes a golden case and a training
example, and the go-live report says when the model is ready.**
- **Asked by Devin.** "The AI should always learn from the answer the senior executive chose"; if nobody rules,
  trust the analyst and adjust from there; go live once seniors side with the model at least as often as with the
  analysts (D53). Built in `spreader/teaching.py`.
- **Memory.** A ruling writes the correct line (or "left off") for the label under its section to reviewer memory,
  as a remap does, so the next document places it that way without the model. If the document belongs to a company,
  the correction also goes into the company's memory, which is consulted before reviewer memory: without it, the
  company's own wrong approval would keep winning for that company (found while designing this; tested). A later
  reopen of the approval does not undo it (tested). Memory is not erased with a document (a label, not a value), as
  for remaps (DATA_LIFECYCLE.md).
- **Calibration.** Each ruling records whether the rule behind the approved line was right and whether the model was
  (method `model.shadow`, declared never-auto in `scripts/calibrate.py`, so measuring the model can never let one of
  its placements skip a person, D48).
- **The gap from D52 is closed.** Confirming a model placement (resolving its review item) now writes memory, so the
  label is placed by memory next time. Checked on the previous code: no memory was written.
- **Examples in the prompt.** Up to three earlier decisions on labels that read alike (rapidfuzz token-set ratio at
  least 0.8, same statement, never from the same document) are shown to the model, senior rulings before
  analyst-stands defaults, quoted and cut short, marked as data. The answer stays a choice from the closed list. A
  live model's runs include the example set's version in their idempotency key, so a new ruling cannot be hidden
  behind an old run; a shadow model's examples never touch a run.
- **Measured** (`scripts/measure_ruling_examples.py`, one run each, Qwen3-4B on the RTX 3060 Ti, SEC dev split): the
  model was asked about the 976 rows of 16 filings that the answer keys can judge, after 91 rulings were simulated
  from the keys on the model's mistakes in the other 17 filings. Without examples 882 of 976 were right (90.4%; 95%
  interval 88.4% to 92.1%). With examples matched by token-set similarity: 906 (92.8%; 91.0% to 94.3%), 27 rows
  fixed and 3 broken; all 3 were a short ruled label matching a longer one that contained its words. With whole-label
  matching (token-sort, now the default): also 906, 24 fixed and none broken (exact McNemar p = 1.2e-7), examples
  shown on 129 rows instead of 326 (`eval/reports/ruling-examples-*-2026-10-29.json`). The rulings were simulated
  from answer keys on public filings, and rows no rule placed cannot be judged by these keys: this measures the
  mechanism, not a lender's result.
- **Weaker evidence stays weaker.** A disagreement no senior ruled on in time is a training example marked
  `analyst_default` with weight 0.5 and a prompt example after the senior rulings, never memory, never a golden case,
  never in the go-live measure.
- **Export.** `spreader learning export` writes `golden-placements.jsonl` (senior rulings: the label, the correct
  line, the verdict, the reason and note), `training.jsonl` (chat-format examples with the plain prompt, without
  examples, and the correct answer) and `manifest.json` with each file's SHA-256. The files hold document labels and
  are not erased with the documents. Found by a test: written as text on Windows the files got CRLF line ends and the
  digests no longer matched; now written as bytes.
- **Go-live report** (`spreader learning report`, `GET /api/learning/report` for seniors, a panel on the senior's
  page). Per model: seniors' verdicts between the analyst and the model, the model's share with a Wilson interval
  (z = 1.96), and the verdict: not enough rulings, not yet, as good (lower bound at least 0.5 minus the margin) or
  better (lower bound above 0.5). Settings `SPREADER_GOLIVE_MIN_RULINGS` (default 100) and `SPREADER_GOLIVE_MARGIN`
  (default 0.05) are the company's; both defaults are chosen here, not by Devin. Also: how often the model agreed with
  the analyst on approved spreads, reasons, rulings per senior, and labels ruled two different ways (the latest is the
  one remembered). Limits stated in the report: agreement is not correctness (both can be wrong), defaults are left
  out, and the model judges placement, not values.
- **Red team** (`tests/test_learning_redteam.py`): two seniors ruling at the same moment leave one ruling, one memory
  row and one outcome; a reopen keeps the lesson; a new ruling is an example at once (the example cache follows the
  ruling count); nonsense settings stop the start; the senior's page lists everything open but only the latest 200
  rulings (it returned the whole history before).
- **Not done.** Retraining the model itself: `training.jsonl` is ready for it, but no model has been trained.

## Real workbooks (2026-10-29)

**D56. Three ways the SEC's real workbooks were read wrong, fixed in general rules: a unit the label states, a row that
totals the others on its line, and a money unit that follows a share unit.**
- **Found.** Devin asked for real samples; the SEC publishes a `Financial_Report.xlsx` with each filing. The nine of
  the prior-year 10-Ks in the evaluation set (downloaded 2026-10-29 to `var/real-samples`, git-ignored, with URLs and
  SHA-256 in its manifest) were spread and scored against the prior-year answer keys, next to the same filings' HTML:
  workbooks 1,027 of 1,288 right (79.7%) and 30 of 831 values accepted alone wrong (3.6%); the HTML 1,071 of 1,287 and
  11 of 745 (1.5%). Of the 30, six were the workbook's own, below; the rest were the same value as the HTML's (nine sent
  to review there only because its period dates were assumed), shared mapping or sign issues, or the answer key
  (Disney's 2022 diluted EPS is keyed as 3.47, the continuing and total figures added). Those are not fixed here.
- **1. A stated unit decides first** (`structure._unit`). The SEC writes "Common stock, shares issued (in shares)"
  among money rows; "issued" is not a share word, so the row was money and its count was added to common stock
  (Apple: 15.2 trillion instead of 83 billion). A label stating "(in shares)", "(shares)" or "(in dollars per share)"
  now sets the unit before any word does.
- **2. A row that equals the sum of the others on its line is their total** (`spread._total_of_the_others`). The SEC's
  income sheet is followed by its breakdown ("Service: Revenues", "Product: Revenues") with no indentation, so all three
  rows were added onto revenue (Disney: twice its revenue). When several rows land on one line and one equals the sum of
  the others in every period they share (to printed rounding, at least one period non-zero), it is taken alone and the
  provenance says so; a figure printed twice is the same case.
- **3. "$ in Millions" after "shares in Thousands"** (`detect.detect_scale`). The SEC's title "USD ($) shares in
  Thousands, $ in Millions" lost its money unit: any unit within 45 characters after "share" was taken as a share unit.
  A unit that names its currency ("$ in Millions") is now money whatever precedes it, and the share unit is looked for
  before it too. A first version split the clause at commas instead and turned Apple's 10-K HTML from 146 of 146 right
  to 58 ("number of shares, which are reflected in thousands" became the money unit); caught on the real filing,
  replaced, and Apple's heading is now in the tests.
- **Measured.** Workbooks: 1,053 of 1,288 right (81.8%), 24 of 861 accepted alone wrong (2.8%; 1.9-4.1%); all 24 are
  the shared or key issues above. HTML of the same filings: 1,074 right, 11 of 757 (1.5%). SEC dev, last commit
  against this one: 3,612 -> 3,618 of 4,428 right, silent errors 59 of 2,521 -> 59 of 2,538; holdout unchanged (3,241
  of 3,972, 32 of 2,154); release gate passed (`eval/reports/stmt-<split>-before-workbook-fixes.json`,
  `stmt-<split>-workbook-fixes.*`, `real-workbooks-2026-10-29.json`).
- **Tests.** `tests/test_workbook_layouts.py` (5): the breakdown under a statement, share rows that say so, stated
  units before label words, the total rule's edges (a period that disagrees, independent rows, zeros, rounding), the
  SEC title and Apple's heading. Checked on the previous code: revenue 182,722 million, common stock 15,200,062, no
  money unit from the title.
- **Not done.** The scans Devin approved (Internet Archive) ran through OCR but have no answer keys, so they are not
  scored; the vendor list is downloaded but not yet used.

**D57. Four errors shared by workbooks and HTML, traced to their causes: three in the answer keys, the rest in the
platform; fixing them exposed two more hidden error sources and a regression from D56, all fixed.**
- **Asked by Devin**: investigate Disney's tax sign, Amazon's other operating expense sign, Hasbro's selling costs and
  Disney's 2022 EPS, the errors D56 left. Then: no error the platform cannot track.
- **The keys** (`evaluation/ixbrl_truth.py`). Tax took the printed sign, so a filer printing its expense in parentheses
  was keyed with a negative expense; it now takes the tagged value, like cost lines (expense positive, benefit
  negative). On a cost line a concept whose positive is income (`OtherOperatingIncomeExpenseNet`,
  `GainLossOnDispositionOfAssets`) is negated: Amazon's 763 expense was keyed -763. Per-share figures and share counts
  are never added: Disney's 1.75 and 1.72 were keyed 3.47; the total measure wins over continuing operations.
  `AdvertisingExpense` printed as its own line is a selling cost, as `MarketingAndAdvertisingExpense` already was. Keys
  rebuilt: 56 of 8,754 commercial values changed (tax 30, other operating 18, SG&A 6, EPS 2), 18 of 2,702 insurer values,
  no bank values; 34 key files, every other key byte for byte the same; six manifests rewritten.
- **The platform's tax sign** (`spread._settle_tax_sign`). A lone tax line in parentheses was read as a benefit. With
  the keys right, this showed on Amazon, Netflix, Qualcomm, Union Pacific, YETI, Etsy, AXIS, Globe Life and W. R. Berkley.
  Now the statement's arithmetic decides: when pre-tax income - tax (+ discontinued operations) = net income only with
  the tax negated, it is negated and the provenance says why; when both or neither fit (equity income after tax:
  Amazon, AXIS), nothing changes and the checks speak.
- **Wording.** "Selling, distribution and administration" (Hasbro) is SG&A; "Net income before noncontrolling interests"
  is net income and "Net income to common stockholders" the company's share (W. R. Berkley: without the second, the
  first made its company share silently wrong three times).
- **Two hidden error sources.** D56 counted a figure printed twice once. On Hancock Whitney's 10-K that made the parent
  company's own cash-flow statement, chosen over the consolidated one, add up, and six wrong values a year went out
  without review where the double count had failed a check before (bank holdout silent errors 46 -> 52, found by
  measuring every set, which D56's check had not done). Parent-only statements are now known by their rows
  ("dividends received from subsidiaries", "equity in undistributed earnings of subsidiaries") as well as their
  heading, lose to any consolidated candidate, and raise the parent-only blocker when chosen alone. The consolidated
  statement then showed "Increase in cash surrender value of life insurance contracts" placed on the net change in cash
  by "increase in cash*"; without "net", those labels must now say which cash.
- **Measured** against the last commit (8a7c63d) on every SEC-based set, new keys after: values right / accepted alone
  wrong: SEC dev 3,618 -> 3,629, 59 of 2,538 -> 51 of 2,548; SEC holdout 3,241 -> 3,247, 32 of 2,154 -> 29 of 2,167;
  banks dev 840 -> 846, 31 -> 31; banks holdout 831 -> 856, 52 -> 35; insurers dev 708 -> 720, 20 -> 20; insurers
  holdout 867 -> 924, 58 -> 50. Release gate passed. Scored with the same spreads, the key fix alone moved the
  commercial silent errors from 100 to 80 of about 4,710 and the insurers' from 84 to 78 (`eval/reports/key-fix-d57-*`).
- **Not done, and the next step.** Silent omissions rose on the holdouts (banks 137 -> 177, insurers 116 -> 160 of their
  values): avoiding parent-only statements leaves some consolidated ones incomplete (Hancock Whitney's cash flow is
  split across tables). A blank is safer than a wrong number, but a value missing without a flag is still an error
  nobody is told about: every expected line and period should be flagged when missing. That, and accepting alone only
  values an independent check confirms, are the route to Devin's target of under 0.2% silent errors.
- **Tests.** `tests/test_answer_key_signs.py` (5), `tests/test_tax_sign.py` (5), `tests/test_parent_only.py` (3).
  Checked on the previous code: 10 of the 13 fail; the other three guard behaviour that was already right.

**D58. Printed subtotals no longer set aside while a template total stays blank: the template's own totals under
unknown wordings are placed, and one still set aside goes to a person.**
- **Asked by Devin**: flag every missing value, toward under 0.2% silent errors (D57's next step).
- **Traced first** (dev sets only, holdout untouched). Of the 259 silent blanks on the three dev sets, 126 were numbers
  not printed in the chosen table (mostly lines the key adds up from several rows), 46 rows placed on a neighbouring
  line, 51 rows inside a placed total, 6 rows left unplaced and 30 rows set aside. A blanket "flag every blank line" rule was simulated: a
  skipped check per missing input would have caught 68 of the 259 for 599 review items, 410 of them pointing at nothing
  the key has; flagging every blank critical line, 52 for 621 items. Neither was built: a reviewer drowned in false
  alarms stops reading them.
- **The set-aside rows.** 42 printed subtotals were left out as "a subtotal of rows placed on other lines"
  (`structure.cross_line_subtotal`); 13 of them hid 32 blank values. They were the template's own totals under
  wordings no alias knew: "Earnings/(loss) from operations" and "... before income taxes" (Boeing), "Cash provided by
  operations" and "Cash and equivalents increase (decrease)" (McDonald's), "Net income before allocation to
  noncontrolling interests" (Pfizer), "Total liabilities, noncontrolling interests and shareholders' equity" (Hasbro),
  "Total revenue, net of interest expense" (Bank of America); and parent-equity totals named after the company
  ("Total AIG shareholders' equity", "FHN shareholders' equity"). The wordings are aliases now; the company-named
  equity total is recognised by its shape (`mapping._own_equity_total`, rule `structure.own_equity_total`: a total
  ending in "stockholders'/shareholders' equity" that names no liabilities, noncontrolling interests, preferred stock
  or "and"). That rule has no measured accuracy yet, so its placements go to review.
- **The safety net** (`review.py`). A subtotal still set aside while a critical total of its statement (a result, an
  equity total, a total_* line or a cash-flow total; current assets and liabilities excepted, since unclassified
  balance sheets print none) is blank in its columns raises a warning naming the blank lines (`set_aside:` items). A wider
  version (any blank critical line) fired 18 times in 53 dev documents after the alias fixes; mean review items per document rose by 0.4 to
  0.7 on every set, including the new rule's placements.
- **Measured** against the last commit (5d00382), values right / accepted alone wrong / blank with no flag:
  SEC dev 3,629 -> 3,664, 51 of 2,548 -> 49 of 2,541, 102 -> 78; SEC holdout 3,247 -> 3,249, 29 -> 29 of 2,167,
  83 -> 67; banks dev 846 -> 853, 31 -> 31, 68 -> 61; banks holdout 856 -> 856, 35 -> 35, 177 -> 174; insurers dev
  720 -> 725, 20 of 666 -> 20 of 664, 89 -> 82; insurers holdout 924 -> 924, 50 -> 50, 160 -> 154. No value newly
  wrong without review on any set (Hasbro's total equity, silently wrong before, is now caught). Release gate passed,
  28 of 28 manifests match.
- **Not done.** The bank and insurer holdouts barely moved: their blanks are mostly rows placed on a neighbouring line
  and lines the key builds from several rows, which need their own fixes. The silent error rate did not move; under
  0.2% needs values accepted alone only when an independent check confirms them.
- **Tests.** `tests/test_set_aside_subtotals.py` (16). Checked on the previous code: 11 fail; the other five guard
  behaviour that was already right (other equity totals not taken as the parent's; no item when nothing is blank).
