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
| 2a | Audit integrity | P1 | In progress | D44; `tests/test_audit_chain.py` | External anchoring of the chain head (T41) |
| 2b | Data protection: inventory, encryption at rest, retention and deletion, backups | P1 | Planned | - | Key management service for a deployment |
| 3 | OCR and ingestion reliability | P2 | In progress (before this tracker) | D42: OCR measured on simulated scans; every scanned value goes to a person | **Real borrower scans** (anonymised, with permission) |
| 4 | Multi-user persistence and concurrency | P3 | Not assessed | Existing: transactions, idempotency keys, edits re-checked inside the write transaction (red-team fixes) | Server database only if a shared deployment is chosen |
| 5 | Model risk management and AI governance | P4 | Not assessed | Existing: no model in the default path; optional local model capped below auto-accept (D8, D27, D35) | Qualified MRM review (SR 11-7) for a bank |
| 6 | Banks, insurers, IFRS | P4 | In progress (before this tracker) | D38, D41: bank and insurer keys and results; IFRS smoke-tested only | - |
| 7 | Analyst validation and ROI | P5 | Not assessed | Existing: ROI page refuses to report time saved under 3 + 3 sessions | **A real analyst's time** |
| 8 | Organisation adaptability | P4 | In progress | Two example sign-in configurations (Entra ID bank, Okta insurer) differ only in configuration | - |

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

## Session log

### 2026-10-28 (overnight, autonomous)
See the end of this file once the session closes.
