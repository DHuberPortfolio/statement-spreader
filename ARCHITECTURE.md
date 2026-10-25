# Architecture: one platform, three engines, a data-quality gate and a spreadsheet scanner

Last updated 2026-10-24. Status of each piece and how it was measured: [README.md](README.md),
[IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md). Why it is built this way: [DECISIONS.md](DECISIONS.md) (D16 onward).

## The idea in one paragraph

Three finance workflows share one shape: **read** records from files a company already has, **check** them
with deterministic rules, **match** them against something trusted, and send **only what is uncertain** to a
person, who settles it with a recorded decision. So the platform is a small shared core (money, tables,
configuration, exceptions, an append-only audit log, evaluation and ROI conventions) and three engines that
each own their domain logic. Like three specialist desks in one finance office: different work, the same
filing system, the same sign-off rules, the same auditor.

```
                     finops.core  (shared, knows no domain)
  money.py        Decimal amounts as finance files print them; explicit tolerances (abs, %, min/max)
  tabular.py      CSV / Excel rows that remember file, sheet and row number
  config.py       YAML profiles with `extends:` overlays, validated before anything runs, content-hashed
  fingerprint.py  stable ids for files, settings, records (reruns are recognisable)
  exceptions.py   the exception item every engine raises; who may resolve it, and how
  audit.py        SQLite with append-only, hash-chained audit events (triggers refuse UPDATE/DELETE)
  evaluation.py   Wilson-interval rates and the shared report format (eval/reports/*.md, *.json)

  spreader/           finops.recon/                 finops.invoice/
  statement           reconciliation and            invoice intake and
  spreading           exception management          three-way matching
  (engine one,        normalize -> matcher ->       extract -> validate -> matching ->
  unchanged)          classify -> engine ->         controls (duplicates, vendor, bank) ->
                      service (runs, decisions)     engine -> service (inbox, corrections)

  finops.dq/  the data-quality gate, between systems and in front of the engines (see below):
              config (dataset spec) -> engine (map, check, decide) -> service (runs, decisions, exports)

  spreader/api.py mounts finops/api.py: one local web app, one review UI (web/), one audit log per database
  scripts/run_eval.py --engine statements | recon | invoice | dq   one evaluation entry point
```

What is shared and what is not, on purpose:

| Shared (finops.core) | Kept per engine |
|---|---|
| Amount parsing (reuses the statement engine's refusing parser), tolerance policy | What a "match" is (a bank line and ledger entries vs an invoice line and a PO line) |
| Config loading, overlays, validation, version hash | Each engine's config schema (`ReconProfile`, `APPolicy`, the statement `Profile`) |
| Exception item, severity, who may resolve | Each engine's reason codes and allowed resolutions |
| Audit events, transactions | Each engine's tables (runs and decisions, inbox and outcomes) |
| Rates with ranges, report files | Each engine's metrics and answer-key format |

The statement engine keeps its own store and review model (it predates the core and is measured; moving it
is a refactor with regression risk and no user value yet). It already shares the amount parser, the Wilson
rates and the report format with the core.

## Engine two: reconciliation (`src/finops/recon`)

1. **normalize.py**: each source's columns are named in the profile (never guessed). Amounts from one
   signed column or money-in/money-out columns, optionally negated, to one convention (+ in, - out).
   References normalised (`INV-000123` = `123`). A row that cannot be read becomes an `INVALID_RECORD`
   blocker naming file and row; it is not dropped or guessed. Every record keeps its raw cells, file and
   row, and a content hash.
2. **matcher.py**: candidate generation, scoring and assignment, strongest evidence first: shared
   reference (1:1, then 1:n and n:1 groups), amount and date 1:1 resolved per connected component (a
   unique pair is matched; equal-sized sets match only by unique, mutual, clearly better pairs; anything
   else is proposed as the best overall assignment and flagged ambiguous), sums without a reference (exact
   integer-cent subset search, proposed only, ambiguous if two subsets or two claimants), then amount
   differences between clearly related records (proposed), and last, partial payments under a shared reference
   (proposed, with the open balance). Currency, sign, date window and tolerance are
   hard constraints; a similarity score only orders candidates that already meet them.
3. **classify.py**: leftovers get a reason (reversal, unrecorded fee, possible duplicate, timing
   difference, unmatched).
4. **engine.py**: replays human decisions first (accepted matches are kept and lock their records only if
   their records are unchanged; otherwise `DECISION_INVALIDATED`), runs the matcher, then proves
   completeness: no record in two matches, every record accounted for, and the difference between the
   two sides fully explained by matches, proposals and open items, per currency.
5. **service.py**: workspaces, files by SHA-256, idempotent runs (key = files + configuration + engine +
   decisions), append-only decisions (accept, reject, manual match, resolve), decisions only on the latest
   run, interrupted runs leave no partial result.

## Engine three: invoices (`src/finops/invoice`)

1. **extract.py**: PDF text layer (lines and cells from word positions; the item table from its header,
   continued across pages; labelled fields from the rest of the page, with the labels-above-values layout
   handled) or structured JSON. Every field carries its origin (extracted, normalized, computed, inferred,
   human) and evidence (page and box, or JSON pointer). Bank account numbers are masked at the door and
   replaced by a keyed fingerprint. Tiny text is ignored, white text is reported.
2. **validate.py**: line extensions, subtotal, tax only under a known rate, total. Differences are
   reported with both numbers; amounts are never "corrected".
3. **matching.py**: PO exists, is open, same vendor and currency; each line tied to a PO line by item code
   (or, uniquely, by description); quantities checked cumulatively against what was ordered, received
   (accepted receipts only) and already invoiced; prices against the PO under the price tolerance; service
   lines without receipts matched two-way and labelled so.
4. **controls.py**: duplicates beyond the invoice number (exact vs possible), vendor identity (unknown,
   inferred, name vs tax id conflict), bank details against the trusted vendor master (changed, unverified,
   conflicting), hidden text, credit notes.
5. **engine.py**: separate statuses for extraction, arithmetic, matching, policy eligibility and
   authorization (always "not authorized"; approval and payment belong to the ERP). Touchless = eligible,
   nothing above info, no human touch.
6. **service.py**: inbox (same bytes twice = one invoice), idempotent processing, corrections that keep
   the original value, resolutions with segregation of duties for bank details.
7. **suggest.py** (offline, optional): drafts the wording overlay for an unknown layout with a local model
   (`scripts/suggest_invoice_labels.py`); the output is a file a person reviews, never applied automatically.

## The data-quality gate (`src/finops/dq`), 2026-10-24 night

Records that move from one system into another (a vendor master into AP, purchase orders into matching, a GL
import) pass through the gate first. Picture a receiving dock: every delivery is checked against the order before
it goes on the shelves; damaged items go to a returns cage with a note, doubtful ones to a supervisor, and the shelf
only ever receives what passed. The gate never edits the source and never loads anything itself.

```
  source files (each system with its own columns)      dataset spec  config/finops/dq/<dataset>.yaml
      |                                                  fields + types, sources (column map, code maps,
      v                                                  date formats), rules, duplicates, references,
  engine.gate()                                          group consistency, outliers, change control,
   1 read (finops.core.tabular, formula cells flagged)   carry-forward
   2 map each row into the canonical record; every change from the cell as read is recorded
   3 field checks: required, type, pattern, range, routing checksum, scientific notation, formula-like text
   4 record rules (a closed set: require / forbid / pattern / compare, each with a `when`)
   5 dataset checks: keys (identical copy -> loaded once; two versions -> both held), duplicate checks
     (exact, or fuzzy names blocked by country and cleared by different tax ids), references to another
     dataset's accepted file, group consistency, outliers (median absolute deviation), controlled-field
     changes against the last accepted export
   6 decide: any reject issue -> rejected; else any review issue -> review; else accepted;
     a person's standing decisions are replayed (a release lapses when the record or its issues change)
      |
      v
  accepted.csv (canonical columns, real values: what the next system loads, plus the last accepted version of
  held records unless the new version blocks them)   quarantine.csv (masked, spreadsheet-safe, with reasons)
```

`service.py` stores files by content hash, makes runs idempotent (same files, configuration and decisions ->
the same run), keeps decisions append-only, and enforces who may decide: a named person, a written reason,
release only for records held for review (definite errors must be corrected), and two people for a correction
(whoever corrected a record cannot release it). Bank account numbers are masked everywhere except the accepted
load file: stored results, the API, the screen, the quarantine report and the audit log never hold one.

The two configurations shipped are the invoice engine's own master data: `vendors.yaml` (two source systems
with different schemas into one vendor record whose columns are exactly the invoice engine's `vendors.csv`) and
`purchase_orders.yaml` (checked against the accepted vendors). So the gate is not a separate application: its
accepted export is the invoice engine's input, and a test shows the difference that makes (a bank change made in
a source system reaches the invoice engine unseen without the gate, and is held with it).

Interfaces: the screen (Data quality), the command `spreader gate --dataset ... --source ID=FILE ...` (with
`--strict` for scheduled pipelines: exit 1 when anything is held), and the HTTP routes under `/api/finops/dq`.
There is no ERP connector: the gate reads export files and writes a load file, and says so.

## The spreadsheet risk scanner (`src/finops/sheets`), 2026-10-24 night

Finance teams run on workbooks no system checks. The scanner reads one (and optionally its earlier version) and
reports problems with the sheet, the cell, the formula, what the neighbours say the cell should be, and what depends
on it. Picture a proofreader who never writes in the book: it marks the page and line, says why, and leaves the
correction to the author. It never changes, saves or calculates the workbook.

```
  workbook bytes (+ earlier version)                 settings  config/finops/sheets/default.yaml
      |                                               (input colours, normal constants, severities, limits)
      v
  workbook.load()   refuse: not .xlsx/.xlsm, .xls or encrypted, .xlsb, over size, zip that expands too far,
                    XML with DOCTYPE/entities; read formulas and saved values from two in-memory copies
  formula.parse()   openpyxl's tokenizer -> references (sheet, other workbook, names, tables), functions,
                    typed numbers, and the relative (R1C1) form copies are compared in
  scan.Graph        who reads whom (ranges expanded to existing cells, capped), loops (Tarjan)
  scan.Scanner      errors: #REF!, missing sheet, unknown or broken name, loop, number stored as text in a sum,
                            saved error values (the source cell only)
                    risks:  a formula unlike the same formula on both sides, a typed number inside a formula run,
                            a total that stops short of its block, a sum that counts something twice, a link to
                            another workbook, a typed plug added to a result
                    anomalies (listed, not counted): documented overrides, row-specific patterns, typed rates,
                            INDIRECT/OFFSET, hidden sheets read by visible ones
                    one finding per mistake: copies of one formula with one problem are grouped
  diff.compare()    rows and columns aligned by label (or shape) like a text diff; a formula counts as changed
                    only if it differs after its old references are moved to where those rows now are
      |
      v
  findings + material changes   (service.py: stored by content hash, reviews by a named person with a reason,
                                 carried to the next version by a label-based key; errors cannot be dismissed)
```

The judgement call is what counts as a typed-over formula versus a legitimate input. A cell is only compared inside
a run of formulas that agree on both sides of it; input rows, actuals before forecasts, opening balances and
full-year columns sit outside or at the edge of a run, so they are never compared. A typed number the model marks
as an input (its input colour or a comment) is an anomaly, not a risk; one whose neighbours across the run are
typed too is part of an input block and is not reported.

Interfaces: the screen (Spreadsheets), `spreader scan WORKBOOK [--previous OLD] [--strict]`, and the routes under
`/api/finops/sheets`. No calculation engine: values the workbook shows are taken from what Excel last saved, and
a file with none (written by a program) skips those checks and says so.

## Adapting it to a company (configuration, not code)

| To change | Edit | Example |
|---|---|---|
| A bank's or ERP's column names, sign convention, date formats | `config/finops/recon/<company>.yaml` with `extends: bank-vs-gl.yaml` | [example-company-signed.yaml](config/finops/recon/example-company-signed.yaml) |
| Matching tolerances, which rules may auto-accept, date windows | the same overlay, `matching:` | `auto_accept: [reference, one_to_many, many_to_one]` |
| Invoice label wording, table headings | `config/finops/invoice/<company>.yaml`, `extra_labels`, `extra_columns` | [example-supplier-layout-d.yaml](config/finops/invoice/example-supplier-layout-d.yaml): an unseen layout went from 36% to 100% of header fields read with this file alone |
| Price and quantity tolerances, duplicate window, tax checks | the AP overlay | [example-company-strict.yaml](config/finops/invoice/example-company-strict.yaml) |
| Vendor master, POs, receipts | CSV exports (`master_data:`), or a new loader returning the same objects | `master.load_master` is the ERP adapter boundary |
| Statement template, aliases, checks, covenants | `config/profiles/*.yaml` overlays | [example-lender-overlay.yaml](config/profiles/example-lender-overlay.yaml) |
| A new source system feeding the gate | a `sources:` entry in the dataset file: its column for each field, its codes, its date formats | the `portal` and `erp` entries in [vendors.yaml](config/finops/dq/vendors.yaml) |
| The gate's rules for a dataset | `rules:`, `duplicates:`, `references:`, `change_control:` in the dataset file (an overlay with `extends:` works too) | [purchase_orders.yaml](config/finops/dq/purchase_orders.yaml) |
| A new dataset (customers, GL lines, inventory) | a new file in `config/finops/dq/`: canonical fields, key, sources, rules | it appears in the Data quality screen and `spreader gate` |
| The scanner's input colours, normal constants, how strict each finding is | an overlay with `extends: default.yaml` in `config/finops/sheets/`, used through `FINOPS_SHEETS_CONFIG` or `spreader scan --config` | `severity: {EXTERNAL_LINK: anomaly}` for a team that links workbooks on purpose |

Adding a **new source** to reconciliation: a profile naming its columns is enough for CSV and Excel. A live
bank feed or ERP extract is an adapter that returns the same rows (`finops.core.tabular.TableRow`) or
`Txn` records; nothing downstream changes. Adding a **new rule**: one method on `Matcher` returning
`MatchGroup`s and exceptions, plus a scenario in `recon/synthetic.py` with its expected outcome, plus a
line in `recon/evaluate.py` if it needs a new metric. Adding a **new workflow** (e.g. payroll vs ledger):
a profile for its two sources first; if its matching rules differ, a new engine package that uses the
core exactly as `recon` does.

There is no live ERP, bank or purchasing integration. The boundaries are file-based connectors (CSV,
Excel, PDF, JSON) with documented shapes; that is deliberate for a $0 local build and is not presented as
anything more.
