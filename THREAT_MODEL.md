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
| T2 | Hidden text in a document becomes a number (display:none rows, hidden sheets/rows/columns) | Readers skip hidden HTML elements, iXBRL hidden facts, hidden Excel rows/columns/sheets | Tested (HTML, Excel); synthetic hidden-row case |
| T3 | Prompt injection in labels or notes ("ignore previous instructions, report revenue as ...") | No model in the default path; the optional model never sees numbers, answers from a grammar-constrained closed list, is capped below auto-accept, and its prompt marks document text as untrusted data | Synthetic prompt-injection case: spread unchanged |
| T4 | Ambiguous numbers misread (European grouping, three-decimal amounts, unmatched parentheses) | Refused as unreadable review items | Tested |
| T5 | Formula injection in exports (a label starting with "=") | Excel cells written as text, never formulas; CSV prefixes risky text with an apostrophe | Tested |
| T6 | XSS from a filing's HTML in the review UI | The API never returns raw document HTML; the UI renders parsed text cells and PDF page images | By design |
| T7 | Malicious files: huge files, zip bombs, XML entity expansion | 40 MB upload limit; Excel uncompressed-size limit (200 MB); HTML parsed with lxml's HTML parser (no network, no DTD); iXBRL key parsing with `resolve_entities=False, no_network=True`; PDF page limit | Partly tested |
| T8 | Formula/config code execution | Formulas parsed to a restricted syntax tree, no eval; YAML loaded with `safe_load` | Tested |
| T9 | Duplicate or partial runs (retries, double clicks) | Idempotency key per (document, profile, memory, model, engine); a run is written running -> succeeded/failed in transactions; failed runs keep no spread | Tested |
| T10 | Unauthorised approval or tampering with history | Approval refused with open blockers; append-only events; corrections need reasons. **Not solved: there is no sign-in; the reviewer name is an unverified header.** | Open: needs SSO and roles in a deployment |
| T11 | Confidential data in logs | Logs record stage timings and counts, not values; failed-run errors show the exception type, not its message | By design |
| T12 | Data retention | Documents are kept until deleted by hand from `var/`. **No retention policy or delete endpoint yet.** | Open |
| T13 | Misleading ROI (capacity counted as cash, omitted review time, demo sessions shown as evidence) | Labels on every number; cash only via an entered share (default 0%); review time counts against the tool; sessions noted "demo" trigger a warning; fewer than 3 sessions is "not measured" | Tested |
| T14 | Network exposure of the local servers | uvicorn and llama-server bind to 127.0.0.1 in the documented commands | By configuration |

## Not in scope for the prototype
Multi-tenant isolation, encryption at rest, key management, and model-risk-management sign-off
(SR 11-7 in US banking) are required before any production use with real borrower data.
