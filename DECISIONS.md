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
