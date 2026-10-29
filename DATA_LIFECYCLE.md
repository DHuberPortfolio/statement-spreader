# Data lifecycle

Where the platform keeps data, why, who can reach it, how it is protected and when it goes (DECISIONS D45, D46).
"Data folder" is `SPREADER_DATA` (default `var/`). Checked against the code on 2026-10-28.

## Inventory

| What | Where | Why it is kept | Who can reach it through the app | Encrypted by the app | Deleted by |
|---|---|---|---|---|---|
| Uploaded statements (10-K HTML, PDF, Excel) | `documents/<sha256>.<ext>` | Re-runs, page images, evidence | `view` (page images, parsed cells; never raw HTML) | **Yes** with a data key (AES-256-GCM) | Erasure of the statement |
| Bank and ledger exports | `finops-files/<sha256>` | Re-runs, decisions replayed | `view` (parsed records) | **Yes** | Erasure of the workspace, when no live workspace uses the file |
| Invoices (PDF, JSON) | `finops-files/invoices/<sha256>` | Re-processing, evidence | `view` | **Yes** | Erasure of the invoice |
| Vendor and PO exports | `finops-files/dq/<sha256>` | Re-runs, previous-load comparison | `view` | **Yes** | Erasure of the dataset, when unused elsewhere |
| Workbooks | `finops-files/sheets/<sha256>` | Version comparison | `view` (findings, not the file) | **Yes** | Erasure of the model, when unused elsewhere |
| Extracted values, spreads, review state (corrections with reasons, resolution notes, approvals) | `spreader.sqlite3`: `runs.spread`, `runs.state` | The work product | `view`; changes need `edit`/`review`/`approve` | No: volume encryption (see below) | Erasure of the statement |
| Company memory (approved values, confirmed mappings) | `spreader.sqlite3`: `approved_values`, `company_mappings` | Next year's comparison | Used by runs; shown as review items | No | Erasure of the statement it came from |
| Disagreements and seniors' rulings (learning period, D53) | `spreader.sqlite3`: `disagreements` (row labels, the analyst's and the model's line, who approved, the ruling) | Teach the model and decide when it goes live | Server only; never shown to analysts | No | Erasure of the statement it came from |
| The model's second opinions (learning period, D52) | `spreader.sqlite3`: `shadow_opinions` (row labels and section headers, the platform's and the model's line; no numbers) | Compare the model with what analysts approved | Server only; never shown to analysts | No | Erasure of the statement it came from |
| Reviewer mapping memory (label -> line) | `spreader.sqlite3`: `mapping_memory` | Learned mappings for every company | Used by runs | No | **Not erased with a document** (a label, not a value); see limits |
| Engine results (matches, invoice outcomes, gate results, scan findings) and decisions | `finops.sqlite3`: `recon_runs.result`, `inv_outcomes`, `dq_runs.result`, `sheet_scans.result`, `*_decisions`, `sheet_reviews` | The work product | `view`; decisions need `review`/`approve` | No | Erasure of the unit |
| Audit events | `spreader.sqlite3`: `events`; `finops.sqlite3`: `audit_events` | Who did what, when (evidence) | `view` (per item history); `audit` (chain verification) | No | **Never deleted.** On erasure the payload (file names, values, notes) is replaced by `{"erased": true}`; kind, actor, time and chain stay |
| Erasure records, legal holds | `erasures` (both databases), `legal_holds` | Proof of what was deleted and why; what must not be | `admin` | No | Never (append-only) |
| Sessions | `finops.sqlite3`: `auth_sessions` (hash of the cookie, roles), `auth_pending` | Sign-in | Server only | Cookie values are never stored | Retention job: ended sessions after `ended_sessions_days` |
| Reviewer outcomes (calibration feed) | `outcomes/*.jsonl` or `FINOPS_OUTCOMES_DIR` | Recalibrating rules (D40) | Accuracy page (counts) | No | Erasure of the statement or workspace removes the lines that point at it |
| Model cache (optional local model) | `var/llm-cache.sqlite3` (fixed path, not the data folder) | Same answer for the same question | Server only | No | **Not covered by erasure**; delete the file by hand. Off unless `SPREADER_MODEL_URL` is set |
| Bank-number fingerprint key | `bank-fingerprint.key` in the data folder | Comparing bank details without storing them | Server only | - | **Stored beside the data it protects**: a known gap (below) |
| Data key | Outside the data folder (`FINOPS_DATA_KEY_FILE`) | Decrypting stored files | Server only; refused inside the data folder; never printed | - | By its owner, after `spreader vault migrate` to a new key |
| Temporary files | `*.tmp` beside the file being written (atomic writes; content already encrypted) | Crash safety | Nobody | Yes (same as the file) | Retention job after `temporary_files_hours` |
| Exports | Not stored: generated on request and sent to the browser; the CLI writes where it is told | The deliverable | `export` | No (they leave the platform) | The recipient |
| Logs | Server output | Timings and counts, never values (THREAT_MODEL T11) | Operators | - | The operator's log rotation |
| Browser storage | `localStorage` (layout preferences, a running timer) | Convenience | That browser | - | The browser |
| Evaluation sets and reports | `eval/` | Measuring accuracy | Repository | - | Public filings and synthetic data only |

## Encryption boundary

- **In transit**: the app serves plain HTTP on 127.0.0.1 for local use. A deployment puts it behind TLS (a reverse
  proxy or the platform's load balancer); with `FINOPS_ENV=production`, sign-in cookies are Secure-only (D43).
- **At rest, by the app**: every uploaded file, with a data key configured (D45). `spreader vault new-key --out
  <outside the data folder>`, then `FINOPS_DATA_KEY_FILE=<that file>`, then `spreader vault migrate` for files
  stored before. `FINOPS_ENV=production` without a key refuses to start (fail-safe).
- **At rest, not by the app**: the two SQLite databases (spreads, notes, results, audit payloads), the outcomes files
  and the model cache. A deployment keeps the data folder on an encrypted volume (BitLocker, LUKS, an encrypted cloud
  disk). SQLCipher would encrypt the databases themselves; not adopted yet (it needs a native build on every platform
  and changes the database driver) - see D45.
- **Outside every boundary**: exports once downloaded, the operating system's swap and crash dumps, and anything an
  operator copies out of the data folder.

## Retention and deletion

- **Policy**: `config/finops/retention/default.yaml` deletes nothing automatically. An organisation sets periods per
  engine in an overlay (`example-seven-years.yaml`) and points `FINOPS_RETENTION_POLICY` at it. Periods count from a
  unit's last activity.
- **The job**: `spreader retention plan` (changes nothing) and `spreader retention run` (erases what is due, removes
  old temporary files and ended sessions). Exit status 1 if any unit failed or an earlier erasure is unfinished, so a
  scheduler notices. Same from the API for administrators (`GET /api/admin/retention`, `POST /api/admin/retention/run`).
- **A deletion request**: `spreader retention erase --engine statement --unit <document id> --reason "..."` or
  `POST /api/admin/erasures`.
- **Legal holds**: `spreader retention hold ...` / `POST /api/admin/holds`. A held unit is never erased; a hold is
  released with a note, never deleted.
- **What erasure leaves**: the audit events' kind, actor, time and hashes; the run and document rows' ids (content
  hashes), statuses and times; the erasure record. That is the minimal record that the work and the deletion happened.

## Backups and restore

The app does not make backups. A backup of the data folder carries the encrypted files and the plain databases; the
data key is backed up separately (a backup that holds both is as exposed as the live system). A restore is verified
with `GET /api/audit/verify` (both chains) and `spreader vault status`. A restore can bring back units erased after
the backup was taken: re-apply the `erasures` records after a restore (not automated yet).

## Known gaps

1. The databases are not encrypted by the app (volume encryption assumed).
2. `bank-fingerprint.key` sits in the data folder: a copy of the folder carries the key that makes bank-number
   digests comparable (the numbers themselves are not stored, only masked forms and keyed digests).
3. The model cache and reviewer mapping memory are not erased with a document.
4. Audit events written before 2026-10-28 in `finops.sqlite3` chain their payload directly and cannot be erased
   (erasure reports them as `audit_payloads_not_erasable`).
5. Re-applying erasures after a restore from backup is manual.
