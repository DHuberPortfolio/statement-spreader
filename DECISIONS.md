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
stress set greedy auto-accepted 7 wrong matches (3.0% of 234) and 18 of 51 pairings that needed a person;
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
