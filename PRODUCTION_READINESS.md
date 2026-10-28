# Production readiness tracker

What stands between this prototype and use with real financial data at a company, one workstream per row. Updated at
the end of every work session. Statuses: *Not assessed, Planned, In progress, Implemented (awaiting validation),
Validated against defined criteria, Blocked by external dependency, Deferred with documented rationale.*

"Validated" here means checked by this repository's own automated tests against the acceptance criteria below. It
never means checked by a live identity provider, a real analyst, an independent reviewer or a regulator; those are
listed separately as external dependencies.

## Baseline (2026-10-28, before any change; main 6a870ac)

| Check | Result | Command |
|---|---|---|
| Python tests | 1,110 collected, 0 failures, 0 skipped, 82 s | `.venv/Scripts/python -m pytest -q` |
| Web tests | 3 files, 31 tests, all passed | `cd web && npm test` |
| Evaluation manifests | pass | `.venv/Scripts/python scripts/eval_manifest.py check` |
| Release gate | PASSED | `.venv/Scripts/python scripts/release_gate.py --out gate.md` |
| Smoke check (every engine through the API) | 12 of 12 | `.venv/Scripts/python scripts/smoke_check.py` |
| Known warnings | Starlette's TestClient deprecation (httpx); pre-existing lint in `evaluation/synthetic.py` (B023, SIM201) and `pipeline.py` (import order) | `ruff check src tests` |

Defects found by reading the code before changing it:
- **Identity**: the actor was the `X-Actor` header; anyone could act as anyone, so every second-person control rested
  on a typed name (THREAT_MODEL T10, T26).
- **Statement audit log**: described as append-only, but the `events` table had no guard and no hash chain (the
  platform engines' log had both). Fixed: D44.

## Workstreams

| # | Workstream | Priority | Status | Evidence | Open / external |
|---|---|---|---|---|---|
| 0 | Baseline and regression protection | P0 | Validated against defined criteria | Table above; `var/readiness/` holds the raw outputs (not committed) | - |
| 1 | Identity, authorization, separation of duties | P1 | Implemented, awaiting validation | D43; `tests/test_identity.py` (47 tests); smoke check step "sign-in" | **Live identity provider** (an Entra ID or Okta test tenant and a client registration) - Devin; per-record ownership inside one organisation (not needed until multi-team use) |
| 2a | Audit integrity | P1 | Implemented, awaiting validation | D44, D46, D47 (anchors); `tests/test_audit_chain.py`, erasure tamper tests in `tests/test_data_protection.py`; `/api/audit/verify` | Anchors exist (`spreader backup anchor`); keeping them somewhere the data's owner cannot write, on a schedule, is the organisation's job: changes after the last anchor remain undetectable by a rebuild |
| 2b | Data protection: inventory, encryption at rest, retention and deletion, backups | P1 | Implemented, awaiting validation | DATA_LIFECYCLE.md; D45, D46; `tests/test_data_protection.py` (16 tests); smoke step "audit chains intact; retention plan" | Databases not encrypted by the app (volume encryption assumed); the organisation's retention periods; a key management service; backup re-application of erasures is manual |
| 3 | OCR and ingestion reliability | P2 | In progress (before this tracker) | D42: OCR measured on simulated scans; every scanned value goes to a person | **Real borrower scans** (anonymised, with permission) |
| 4 | Multi-user persistence and concurrency | P3 | Implemented, awaiting validation | D47; `tests/test_concurrency.py` (11 tests: real races between two connections, same-cell refusal, stale approval 409, interrupted action and upload, backup during writes, restore, anchor catches a rebuilt chain); `scripts/load_check.py`; existing `tests/test_review_fixes.py` race tests for the platform engines | Several application servers (PostgreSQL) not done; restore of erasures after a backup is manual; load measured in-process on one machine only |
| 5 | Model risk management and AI governance | P4 | Implemented, awaiting validation | MODEL_RISK.md (inventory of 3 models, 10 risks); D48; `tests/test_model_governance.py` (21 tests: malformed and invented outputs, server failures, injection, no numbers sent, blocking review, model id per run, drafts hold only wording) | Independent validation and governance approval by qualified people (SR 11-7); a live model run to refresh the #9 measurement after D48 (needs the local GPU server) |
| 6 | Banks, insurers, IFRS | P4 | In progress | D38, D41: keys and results; D50: corporate checks and ratios that cannot hold are declared not applicable (bank 8 + 14, insurer 8 + 11), dev results unchanged; `tests/test_profile_applicability.py` | IFRS answer keys and IFRS-specific checks (presentation by nature); bank and insurer accuracy is still well below commercial (holdout 68.7%, 59.1% right) |
| 7 | Analyst validation and ROI | P5 | Blocked by external dependency (tooling implemented) | PILOT_PROTOCOL.md; D49; `scripts/pilot_report.py`; `tests/test_pilot.py` (5 tests); same-analyst re-timing refused; difficulty and experience recorded | **Two analysts' time, six comparable documents, permission to use them**; no session run yet |
| 8 | Organisation adaptability | P4 | Implemented, awaiting validation | D50: `config/organisations/*.env` + `spreader serve --org`; two example organisations differing in sign-in, profile, retention and payables policy; `tests/test_organisation.py` (11 tests: files validated, secrets refused, a profile or policy change alters only what it declares) | No real organisation onboarded; connectors to an organisation's systems (ERP, document store) are integration work |

### Workstream 1 acceptance criteria and evidence

| Criterion | Evidence |
|---|---|
| 1. Unauthenticated requests to protected endpoints are denied | `test_every_protected_route_refuses_a_caller_who_is_not_signed_in` (every route in the table) |
| 2. A forged reviewer-name header cannot establish identity | `test_a_reviewer_name_header_is_not_identity`, `test_a_cookie_the_server_did_not_issue_is_worthless`; smoke check |
| 3. Each role is permitted and denied the right operations | `test_each_role_is_refused_every_route_it_is_not_granted` (7 roles x every route), `test_statement_actions_need_the_permission_of_the_action`, `test_bank_detail_verification_and_record_release_need_approve` |
| 4. Changing resource identifiers cannot bypass authorization | `test_changing_the_resource_id_does_not_bypass_authorization`; routes without a permission are closed (`test_every_api_route_in_the_source_has_a_permission...`) |
| 5. Expired, malformed or invalid tokens are rejected | `test_bad_tokens_are_refused` (12 cases incl. `alg: none`, HS256 key confusion, wrong key, tampered claims), tenant and unreachable-provider tests |
| 6. Separation of duties enforced server-side | `test_the_uploader_cannot_approve_their_own_spread`, `test_a_corrector_cannot_approve_and_the_rule_is_configurable` |
| 7. Audit records use the verified actor | `test_audit_entries_name_the_identity_the_server_verified`, `test_sign_ins_are_recorded_in_the_platform_audit_chain` |
| 8. Development mode cannot be mistaken for production | `test_development_sign_in_refuses_production_and_remote_hosts`, `test_development_mode_says_so_on_every_response...`, `test_a_development_session_is_worthless_once_a_provider_is_configured` |
| 9. A second provider or organisation without code changes | `test_two_example_organisations_load_and_map_their_own_groups`; `config/finops/auth/example-entra-id.yaml`, `example-okta.yaml` |

Not established by these tests: that a specific live provider's tokens, claims and key rotation behave as configured.
To validate: register the app in a test tenant, set `FINOPS_AUTH_CONFIG` to a copy of an example file with the
tenant's ids and `FINOPS_OIDC_CLIENT_SECRET`, sign in with one user per role, and repeat criteria 2-7 by hand.

Rollback: revert the commit. The schema 4 migration (two columns and two triggers on `events`) is one-way: older code
refuses to open a schema 4 database ("newer than this code"), so rolling back the code means restoring the database
copy taken before upgrading. That copy was taken for `var/demo` (`var/readiness/backup-before-schema4/`).

### Workstream 2 acceptance criteria and evidence

| Criterion | Evidence | Gap |
|---|---|---|
| Sensitive persistent data is protected by the configured encryption | `test_every_engines_stored_files_are_encrypted_and_still_work` (all five engines' uploads) | Databases: volume encryption, not the app |
| Key material not exposed or stored with the data | `test_keys_are_kept_away_from_the_data_and_never_printed`; key refused inside the data folder | `bank-fingerprint.key` still in the data folder (DATA_LIFECYCLE gap 2) |
| Retention configurable and deterministic | `test_the_policy_decides_what_is_due_and_never_deletes_by_default` | Periods are the organisation's decision |
| Deletion covers derived artifacts and temporary storage | `test_erasing_a_statement_removes...`, `test_erasing_a_platform_unit...` (4 engines), temp files in the policy test | Model cache, mapping memory |
| Legal holds respected | `test_a_legal_hold_blocks_erasure_until_released` | - |
| Audit verification detects modification | `test_an_edit_made_around_the_guards_is_detected` (5 attacks), `test_erasure_cannot_be_used_to_rewrite_other_history` | Full rebuild (T41) |
| Failed deletion observable and retryable | `test_an_interrupted_erasure_is_visible_and_finishes_when_run_again`; `spreader retention run` exits 1 on failure or unfinished erasures | - |
| Backups, restores, migrations keep the guarantees | Migration: `test_a_schema_3_database_is_migrated...`, `test_migration_encrypts_old_files_and_rotates_keys`; platform chain upgraded on a copy of the demo data and still verifies | Backup/restore drill not automated; erasures after a restore re-applied by hand |
| Documented defaults and fail-safe behaviour | Default policy deletes nothing; production without a data key refuses to start | - |

Rollback: revert the commit and restore the database copy taken before upgrading. Older code would open the
upgraded platform database but report its chain broken at the first event written by this version (that event
chains a payload digest), and it cannot read encrypted files.

## Cross-platform QA and adversarial testing (running)

| Area | Evidence | Found and fixed |
|---|---|---|
| Dependency vulnerabilities | `pip-audit --local`, `npm audit` (2026-10-28) | PyJWT 2.10.1 -> 2.15.1 (advisories), Vite 7.3.6 -> 7.3.7 (dev only), setuptools in the venv; both audits then clean (T48) |
| Download headers and export traceability | `test_download_names_cannot_break_the_header_and_exports_name_the_user` | Unescaped user file name in a header; two exports logged no person, two logged none at all (T47) |
| Authorization bypass | `tests/test_identity.py` | Header-based identity (D43) |
| Concurrency and replay | `tests/test_concurrency.py`, `scripts/load_check.py` | Spurious conflicts, stale-screen approval (D47) |
| Model output | `tests/test_model_governance.py` | Crash on non-object replies, non-blocking model placements (D48) |
| Erasure abuse and tampering | `tests/test_data_protection.py`, `tests/test_audit_chain.py` | Statement audit log had no guard or chain (D44) |

## Session log

### 2026-10-28 (overnight, autonomous)
See the end of this file once the session closes.
