# Threat model

Scope: a single-user local prototype that reads confidential financial statements, produces numbers
people rely on, and exports them. The worst outcomes are a wrong number that looks trustworthy, a
document that changes the system's behaviour, and confidential data leaking.

## Assets
- Uploaded statements (confidential borrower or subsidiary financials): `var/documents/`.
- Spreads, corrections, approvals and the audit log: `var/spreader.sqlite3`.
- Reviewer mapping memory (affects every later run).
- The profile (template, checks, ratios): `config/profiles/`.

## Threats and safeguards

| # | Threat | Safeguard | Status |
|---|---|---|---|
| T1 | A wrong value passes every check and is auto-accepted (silent error) | Footing, accounting identities, cross-statement and cross-period checks; confidence per mapping method measured on answer keys; low-confidence mappings, assumed units/periods, suspicious jumps and negative totals go to review; silent error rate measured on SEC and synthetic keys | Measured: see README results |
| T2 | Hidden text in a document becomes a number | Readers skip hidden HTML (inline styles, stylesheet rules, zero size, off-screen), iXBRL hidden facts, hidden Excel rows/columns/sheets and ";;;" formats | Tested; red-team cases in tests/test_redteam.py |
| T3 | Prompt injection in labels or notes ("ignore previous instructions, report revenue as ...") | No model in the default path; the optional model never sees numbers, answers from a grammar-constrained closed list, is capped below auto-accept, and its prompt marks document text as untrusted data | Synthetic prompt-injection case: spread unchanged |
| T4 | Ambiguous numbers misread (European grouping, three-decimal amounts, unmatched parentheses) | Refused as unreadable review items | Tested |
| T5 | Formula injection in exports (a label starting with "=") | Excel cells written as text, never formulas; CSV prefixes risky text with an apostrophe | Tested |
| T6 | XSS from a filing's HTML in the review UI | The API never returns raw document HTML; the UI renders parsed text cells and PDF page images | By design |
| T7 | Malicious files: huge files, zip bombs, XML entity expansion | 40 MB upload limit; Excel uncompressed-size limit (200 MB); HTML parsed with lxml's HTML parser (no network, no DTD); iXBRL key parsing with `resolve_entities=False, no_network=True`; PDF page limit | Partly tested |
| T8 | Formula/config code execution | Formulas parsed to a restricted syntax tree, no eval; YAML loaded with `safe_load` | Tested |
| T9 | Duplicate or partial runs (retries, double clicks) | Idempotency key per (document, profile, memory, model, engine); a run is written running -> succeeded/failed in transactions; failed runs keep no spread | Tested |
| T10 | Unauthorised approval or tampering with history | Sign-in required on every API route; permissions by role; approval needs the approve permission and someone other than the uploader and correctors (D43); approval refused with open blockers; events append-only and hash-chained (D44); corrections need reasons | Tested locally (tests/test_identity.py, tests/test_audit_chain.py); a live identity provider is not yet verified |
| T11 | Confidential data in logs | Logs record stage timings and counts, not values; failed-run errors show the exception type, not its message | By design |
| T12 | Data retention | Configurable retention per engine (default: nothing deleted automatically), erasure of a unit's files, derived records, notes and audit payloads, legal holds that block erasure (D46); inventory in DATA_LIFECYCLE.md | Tested (tests/test_data_protection.py); organisation periods to be set by each organisation |
| T13 | Misleading ROI (capacity counted as cash, omitted review time, demo sessions shown as evidence) | Labels on every number; cash only via an entered share (default 0%); review time counts against the tool; sessions noted "demo" trigger a warning; fewer than 3 sessions is "not measured" | Tested |
| T14 | Network exposure of the local servers | uvicorn and llama-server bind to 127.0.0.1 in the documented commands | By configuration |

## Red-team review (2026-10-24)

An independent reviewer (a separate agent with no part in writing the code) reproduced 15
findings; every one was fixed and has a regression test in `tests/test_redteam.py`, and the
reviewer's reproduction scripts were re-run against the fix.

| Severity | Finding | Fix |
|---|---|---|
| Critical | A statement hidden by a stylesheet class, a CSS comment or escape, font-size 0 or an off-screen position replaced the visible one, auto-accepted (falsified T2) | Stylesheet rules, comments and escapes honoured; zero size, opacity 0, off-screen and clipping treated as hidden |
| Critical | Excel `#,##0,,` showed millions while storing units; with "(In millions)" values came out 1,000,000x too large | Numbers read as displayed; the scaled cells are reported |
| High | Two columns for one period (previously reported vs restated, budget vs actual) kept the first silently | Restated/budget/forecast/pro forma columns left out; any remaining duplicate period is a blocker |
| High | An unaudited pro forma table outscored the audited statement | Such titles penalised; a close rival table raises a review item; table context stops at the previous table |
| High | Hidden Excel column ranges only partly skipped | Hidden ranges expanded; zero widths/heights and ";;;" formats skipped |
| High | Cross-site requests could correct, resolve and approve; any Host header answered (DNS rebinding) | Writes need same-origin JSON or a file upload; Host must be local |
| High | Regex backtracking in label cleaning froze the server (51 s) | Markers stripped one at a time, labels capped; pipeline runs off the event loop |
| High | rowspan/colspan bombs used ~300 KB per cell | Spans capped to the table; grids over 200,000 cells refused |
| Medium | ROI used sessions with zero active time; heartbeats could add hours in seconds; baseline keying compared with another document's or an unapproved run | Empty sessions ignored; active time capped by the clock; only the document's own approved run is used |
| Medium | A resolution survived a change to the numbers behind it | Resolutions fingerprint their item and reopen when it changes |
| Low | Concurrent edits lost an update; non-ASCII digits accepted; NaN assumptions accepted | Edits checked inside the write transaction; other digit scripts refused; non-finite numbers refused |

An outside test run on Linux (2026-10-24, evening) found two more reader problems, both now fixed with tests in
`tests/test_html_reader_fixes.py`:

| Severity | Finding | Fix |
|---|---|---|
| High | lxml 6 wheels built on libxml2 2.14 (Linux, macOS) stop at the first `</html>`: in a file holding several documents, every later statement vanished without a warning (a silent omission; the Windows wheel bundles libxml2 2.11, so it never showed in local runs) | Each document in a file is parsed on its own; CI installs fresh on Linux, plus the oldest lxml allowed |
| High | "Zero size" hid whole subtrees, but font size is inherited and a child can set its own: Deckers' 10-K (a `font-size:0` wrapper around every page) had all 155 tables dropped and failed to read. Meanwhile `font-size:0.0pt` did not count as zero, so a statement hidden that way was read as real | A zero font size hides only text whose nearest declared size (inline or stylesheet) is zero; `0.0pt` counts as zero |
| Medium | Found while demoing the app the same evening (T13): the ROI page showed the tool's silent error rate as an observed 3.9%, a first-day figure, because it read `latest-dev.json`, which named evaluation runs never refreshed | Every full evaluation run refreshes its `latest-*` report; the page prefers the holdout half of the newest run and names its source (`tests/test_roi.py`) |

Still open (hypotheses, not reproduced): stale cached formula values in Excel files set to
recalculate on open; reviewer mapping memory is shared across all companies under one profile
(a wrong remap affects later documents until corrected); statement tables nested inside layout
tables are not read.

## Reconciliation and invoice engines (2026-10-24, afternoon)

New assets: bank and ledger exports and invoices (`var/finops-files/`), the decision log and audit chain
(`var/finops.sqlite3`), the bank-fingerprint key (`var/bank-fingerprint.key`, outside the repository), vendor
master, PO and receipt exports.

| # | Threat | Safeguard | Status |
|---|---|---|---|
| T15 | A false automatic match hides a real discrepancy | Hard constraints (currency, sign, window, tolerance) before any score; ambiguity proposed, never guessed; sums without a reference only proposed; completeness checks per run | Measured: 0 false matches on dev, holdout and the round-amount stress set (greedy baseline: 7 on stress) |
| T16 | A record consumed twice, or a rerun duplicating matches | One group per record (runtime guard and a check); runs keyed by content; identical requests reuse the run | Tested |
| T17 | A changed source file silently keeps or drops an approved match | Decisions carry the records' content hashes; a change raises DECISION_INVALIDATED (blocker) | Tested |
| T18 | Invoice fraud: changed bank details | Blocker against the trusted vendor master; "cannot be verified" with no baseline; numbers masked, compared by keyed HMAC; resolution needs independent verification by someone other than the uploader; nothing pays or edits master data | Tested |
| T19 | Duplicate payment (re-typed number, same file twice, look-alike) | Same bytes = one invoice; exact and possible duplicate rules beyond the number; both block eligibility | Tested; measured 6 of 6 caught on each set |
| T20 | Hidden or tiny text steering extraction (a white account number, a 1.5 pt "Total $1.00") | Text under 3 pt ignored; white text reported (HIDDEN_TEXT); more than one account printed is a blocker | Tested (red-team fixtures) |
| T21 | Vendor impersonation with a borrowed tax id | Tax id resolves the vendor only if the printed name agrees; otherwise VENDOR_IDENTITY_CONFLICT blocker | Tested |
| T22 | Text addressed to an AI inside an invoice ("pre-approved, skip checks") | No model reads invoices or transactions; rules decide; test shows identical outcome | Tested |
| T23 | An automated actor closes exceptions | Named reviewer required; "system", "model", "ai", "assistant", "local-user" refused; blockers need notes | Tested |
| T24 | CSV formula injection from descriptions or file names | Exports prefix risky text with an apostrophe (shared with the statement engine) | Tested |
| T25 | Credit notes or negative invoices reaching "eligible" | CREDIT_NOTE warning blocks touchless processing | Tested |
| T26 | Reviewer identity was an unverified header (inherits T10) | The header is ignored; the actor is the identity the server established (session or provider token); bank-detail verification and record release need the approve permission on top of the existing second-person rules (D43) | Tested locally; live provider pending |

### Independent red-team review of the platform (2026-10-24, afternoon)

A separate agent with no part in writing the code probed `src/finops` with 15 scripts. Every reproduced finding is
fixed and has a regression test in `tests/test_review_fixes.py` (named by finding number).

| Severity | Finding | Fix |
|---|---|---|
| Critical | A line with no unit price, no quantity or an unreadable quantity was not checked, so an invoice billing 10x the PO value went through touchless | Such a line is a LINE_INCOMPLETE blocker; quantities must be plain numbers (no NaN, exponents) |
| High | A tax rate printed on the invoice replaced the vendor master's | The master rate wins; a different printed rate is TAX_RATE_MISMATCH; a rate nobody trusts is TAX_UNVERIFIED |
| High | Header freight and negative discounts were never compared with the PO | FREIGHT_NOT_ON_PO (warning), NEGATIVE_DISCOUNT (blocker) |
| High | A held invoice did not reserve its quantity, so a second invoice for the same goods passed | Every invoice not rejected (and not an open exact duplicate) reserves its quantity; a decision re-checks later invoices |
| High | "Bank Account:", "Account:", "A/C No.", "Beneficiary account" skipped the bank control | Wider label and in-text patterns; account and routing compared separately by keyed digest |
| High | The uploader could resolve BANK_DETAILS_CONFLICT alone | Conflict and vendor-identity conflict join the segregated set: verified independently, by someone else, with a real note |
| High | Reconciliation: "EUR 7,829.48" with a blank currency column was read as USD; a negative deposit's sign was flipped | A currency in the amount cell is used (or the row refused if it contradicts the column); negative numbers in in/out columns are refused unless the profile says how to read them |
| Medium | Rejecting an invoice left its outcome "eligible" | "rejected" is an eligibility status of its own; rejected invoices release their quantities |
| Medium | Full account numbers in other fields, grouped digits in the hidden-text warning, and in the audit log through a correction | Digit runs are masked in any text that talks about bank details, in evidence, in the hidden-text warning and in corrections |
| Medium | Duplicate totals compared as text ("604.2" vs "604.20") | Compared as numbers |
| Medium | An earlier invoice's change did not refresh later results (stale reuse) | The reuse key covers every earlier invoice's details, and decisions re-check later invoices |
| Medium | Malformed uploads, corrections and oversized CSV cells gave 500 errors and half-registered rows | Refused with a 400 and a reason before anything is stored |
| Medium | Contradicting party names (ACME vs BETA) did not stop automatic pairing | Names now count in the score, and a pair whose names contradict is only proposed (NAME_MISMATCH) |
| Medium | Rejecting one of two equal candidates made the other "the only record" and automatic | Records a person rejected a pairing for are only proposed afterwards |
| Medium | Invalidated decisions with all records gone shared one exception id | The id includes the decision |
| Low | Amount-difference layer only searched within a cent; older files re-run returned a run nobody could decide on; concurrent runs; "System.", "AI assistant" passed as people; "alice." bypassed separation of duties | All fixed: correct search window; re-run becomes the latest run; runs serialised; automated-name check by word; names compared normalised |

Not reproduced, closed anyway with tests: two decisions on the same run at once (the "latest run" check is now repeated
inside the write transaction); an approved credit note freeing PO quantity (negative quantities no longer count).
Still a hypothesis: invisible PDF text drawn off-page or in an invisible render mode.

## The data-quality gate (2026-10-24, night)

New assets: the source exports and last accepted snapshots (`var/finops-files/dq/`), the gate's runs and decisions
(`var/finops.sqlite3`), and the accepted load files it writes, which hold real bank details by design.

| # | Threat | Safeguard | Status |
|---|---|---|---|
| T27 | Vendor-master fraud: bank details changed in a source system, then invoices paid into the new account (the invoice engine's own check compares against the master, so it agrees with the fraud) | Bank account, routing number and tax id changes against the last accepted export are held; the last accepted version stays in force meanwhile; a person who corrected the record cannot release it | Tested end to end: without the gate the invoice passes the bank check, with it the invoice is blocked |
| T28 | A bad record loads silently: corrupted by a spreadsheet (scientific notation, lost leading zeros), a duplicate id overwriting another, a PO for an unknown vendor | Field checks with named reasons; lossy normalisation refused; key conflicts held; references checked | Measured on synthetic and independently written sets (README, IMPROVEMENT_LOG) |
| T29 | A source quietly drops a vendor that a held record's old version would revive (a blocked vendor paid again) | Carry-forward never applies when the held version blocks or deactivates the record; such keys are listed as withheld | Tested |
| T30 | Bank details leaking into logs, the database or the browser | Masked in stored results, API responses, the screen, the quarantine report and the audit log; only the accepted load file holds them | Tested (every account number of the sample checked against the API response and the audit log) |
| T31 | Formula injection through the quarantine report, or a record that runs a formula when opened | Formula-like text held for review; report cells written as plain text | Tested; costs one false hold on a company named "@Home Supply" (measured) |
| T32 | Two people deciding on the same run at once, or on a stale screen | Decisions only on the dataset's latest run, checked again inside the write transaction | Tested |

## The spreadsheet risk scanner (2026-10-24, night)

| # | Threat | Safeguard | Status |
|---|---|---|---|
| T33 | The scan changes or runs the workbook (macros, external links, recalculation) | Bytes read into memory; openpyxl never runs macros or follows links; nothing is written back; nothing is calculated | Tested (the file's hash and modification time are unchanged after `spreader scan`; every evaluation workbook is hashed before and after) |
| T34 | A hostile file: XML entity expansion, a zip that expands to gigabytes, a huge sheet, a damaged package | DOCTYPE/ENTITY refused before parsing (openpyxl uses the standard-library parser, and defusedxml is not installed); limits on file size, expanded size and filled cells; damaged files refused with a message | Tested (12 hostile files: 9 refused, 3 scanned, 0 crashes) |
| T35 | Formula injection through the findings export | Text that starts like a formula is written as plain text | Tested |
| T36 | A real problem dismissed as deliberate, or a dismissal reused on a changed formula | A named person and a written reason; errors cannot be dismissed; the review key includes the formula in relative form and the labels, so any change reopens it | Tested |
| T37 | False confidence: a clean scan read as "the model is right" | The README says what is not checked (values without a saved calculation, logic that is consistent but wrong, VBA) | Documented |
| T38 | Company memory poisoned: a document uploaded under another company's id, or a wrong mapping approved, then reused automatically every year | Memory is written only by an approval (a named reviewer, blockers resolved); rows behind a corrected line are not remembered; reuse is calibrated, so a memory that starts failing loses automation when recalibrated; approvals are append-only and withdrawn by a new row, so the history shows who approved what. Not covered: the company id and the approver's name are unverified until sign-in exists | Tested in part |
| T39 | An approved spread rewritten after the fact (to hide a restatement or an error) | `approved_values` and `company_mappings` refuse UPDATE and DELETE (triggers); a new approval adds rows | Tested |

## Identity, sessions, audit integrity and data protection (2026-10-28)

New assets: sessions and pending sign-ins (`auth_sessions`, `auth_pending` in `var/finops.sqlite3`; only hashes of
cookie values and sign-in states are stored), the sign-in configuration (`config/finops/auth/*.yaml`), the identity
provider's client secret (an environment variable named in the configuration, never in a file).

| # | Threat | Safeguard | Status |
|---|---|---|---|
| T40 | Identity spoofing or privilege escalation: a name in a header, body or cookie; a forged, expired, re-signed (`alg: none`, HS256 with the public key), wrong-audience or other-tenant token; a session cookie guessed or replayed after sign-out | Identity only from a server-issued session or a provider token checked with PyJWT against the provider's published keys (issuer, audience, expiry, not-before, nonce, required tenant claims, asymmetric algorithms only); sessions expire (idle and absolute) and end at sign-out; sign-in state and PKCE verifier single-use; every /api route has a permission and unknown routes are closed; roles only from the organisation's role map; provider unreachable means refused (D43) | Tested through the API with a local test provider (tests/test_identity.py, 47 tests); **not yet verified against a live provider** |
| T41 | History rewritten by someone with access to the database file | Statement and platform audit logs refuse UPDATE/DELETE (triggers) and are hash-chained; `/api/audit/verify` (auditor) finds the first entry that does not fit. **A full rebuild of the chain by whoever controls the file is not detected**: that needs the chain head (`Store.chain_head`) copied to storage the database owner cannot write (D44) | Partial edits tested (tests/test_audit_chain.py); external anchoring open |
| T42 | Development sign-in used for real | Refused with FINOPS_ENV=production or any non-local host name; every response carries `X-Auth-Mode: development-unverified`; the app shows a banner; audit entries are prefixed `dev:`; development sessions are worthless once a provider is configured; bearer tokens are refused in development | Tested |
| T43 | Cross-site use of a signed-in browser (CSRF) | Session cookie HttpOnly and SameSite=Lax (Secure outside local development); writes refused unless same-origin JSON or a file upload (existing middleware) | Tested (existing cross-site tests, now with sessions) |
| T44 | Stored uploads read from a copied data folder, a backup or a stolen disk | Uploaded files encrypted with AES-256-GCM, file name bound in; key outside the data folder (refused inside); production refuses to start without a key (D45) | Tested; **databases are not encrypted by the app** (volume encryption assumed) |
| T45 | Deletion that misses derived copies, or that breaks the evidence trail | Erasure covers files, spreads, results, decisions, notes, company memory, outcomes and audit payloads; chains stay verifiable; minimal record kept (D46) | Tested per engine; model cache and pre-2026-10-28 platform payloads not covered (DATA_LIFECYCLE.md) |
| T46 | Erasure used to rewrite history, or to delete what a legal hold protects | Triggers allow only an erased unit's payload to become the erasure marker; erasure records and holds cannot be deleted; held units are refused; erasure needs `admin` and a reason, and is itself audited | Tested |

## Not in scope for the prototype
Multi-tenant isolation in one deployment (one organisation per deployment for now), database encryption (volume encryption assumed), a key management service, and model-risk-management sign-off
(SR 11-7 in US banking) are required before any production use with real borrower data.
