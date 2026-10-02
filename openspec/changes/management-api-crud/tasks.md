## 1. Implementation setup and contract lock

- [x] 1.1 Have a Sol medium orchestrator read the complete change artifacts, `AGENTS.md`/RTK instructions, ADR-0011, and the management foundation; verify it records scope, dependencies, unrelated working-tree changes to preserve, and the Sol-orchestrator/Luna-implementation/Sol-high-review workflow before delegating code.
- [x] 1.2 Create or select a feature worktree from current `master`, confirm no feature changes are mixed with unrelated user files, and verify `rtk git status --short` and the branch base are recorded before implementation.
- [x] 1.3 Run the current Python 3.14 management tests, full pytest suite, Ruff, and OpenSpec strict validation; verify either a clean baseline or a written list of pre-existing failures before any implementation edit.
- [x] 1.4 Reconcile KAN-76 and any copied implementation notes with the accepted ICP rule that any empty positive dimension yields no results; verify no implementation artifact still describes empty positives as unrestricted.

## 2. Shared management persistence and boundaries

- [x] 2.1 Add schema tests first for sessions, offerings, ICPs, strategies, indexes, JSONB outer-shape checks, `NO ACTION` deletes, and composite same-User strategy foreign keys; verify the new integration tests fail against the unchanged bootstrap for the expected missing-schema reasons.
- [x] 2.2 Extend `db/schema/operational.sql` with the designed tables, constraints, and indexes while preserving existing table behavior; verify all operational schema integration tests pass against a fresh PostgreSQL 16 container.
- [x] 2.3 Extend readiness requirements to cover every management-owned table/column needed at runtime without applying DDL; verify ready returns 503 for a deliberately incomplete schema and 200 for the complete fresh bootstrap.
- [x] 2.4 Implement the management connection factory and unit-of-work abstraction with explicit commit/rollback and no repository-owned commits; verify unit tests cover success, body failure, commit failure, rollback, and connection cleanup.
- [x] 2.5 Define resource-specific repository ports, clocks/token generators, principal and page result types, and domain errors without importing Flask into application/domain modules; verify architectural import tests or focused unit tests enforce the dependency direction.
- [x] 2.6 Add strict shared Pydantic primitives for nonblank text, bounded pagination, email, E.164 phone, IANA timezone, UUIDs, and patch field-presence handling; verify focused schema tests cover valid values, rejected coercion/extra fields, explicit null, and omitted fields.
- [x] 2.7 Implement the common JSON parser, response serializer, error envelope, exception-to-status mapping, and deterministic page response; verify Flask boundary tests cover 400, 401, 403, 404, 409, 422, 429, and safe generic 500 behavior.

## 3. Atomic identity aggregate and owner CLI (KAN-72)

- [x] 3.1 Add password value validation and Werkzeug scrypt hashing/verification adapters with injected behavior where testing needs determinism; verify tests prove a 12-to-1024-character verbatim password boundary, distinct salts for the same password, successful verification, and no plaintext retention.
- [x] 3.2 Implement Account, User, and ProfessionalProfile persistence methods on one unit-of-work connection, including case-insensitive username lookup/conflict handling and safe returned fields; verify live-Postgres repository tests cover mappings, uniqueness, and empty profile defaults.
- [x] 3.3 Implement atomic provisioning with input validation and constraint-to-domain-error translation; verify service and live-Postgres tests prove exactly three linked records on success and zero partial records after each injected or database failure point.
- [x] 3.4 Implement `python -m huginn.management.admin account` provision/enable/disable/reset-password commands without exposing hashes or accepting password arguments, with session revocation in the same transaction for disable/reset; verify CLI tests cover prompts/stdin, exit codes, safe output, preserved User/Profile rows, and rollback.
- [x] 3.5 Have the orchestrator inspect the KAN-72 diff and rerun its focused unit/integration tests after the Luna implementation task; verify no public registration route or generic Account/User CRUD was introduced.

## 4. Authentication, sessions, CSRF, and ownership (KAN-73)

- [x] 4.1 Extend `ManagementConfig` with validated cookie name, local/production secure-cookie behavior, SameSite policy, 12-hour default session TTL, and login throttle settings while keeping secrets/DSN out of repr; verify configuration tests cover defaults and invalid environment values.
- [x] 4.2 Implement opaque session and CSRF token generation, SHA-256 digesting, session persistence, active lookup, current revocation, Account-wide revocation, and expiry checks; verify tests prove raw tokens are never stored and revoked/expired sessions do not resolve.
- [x] 4.3 Implement the injected fixed-window failed-login throttle with the documented five-failures-per-15-minutes default and process-local limitation; verify clock-controlled tests cover threshold, window expiry, composite key behavior, and successful-login reset without account disclosure.
- [x] 4.4 Implement login and password-change application services with one generic credential failure, active-Account enforcement, optional Werkzeug rehash, current-password verification, and transactional all-session revocation; verify service tests cover every credential/status branch and rollback.
- [x] 4.5 Implement request authentication and CSRF enforcement that resolves Account/User ownership server-side and never trusts payload ownership identifiers; verify Flask tests cover missing/invalid cookies, disabled Accounts, valid read requests, unsafe methods with missing/wrong CSRF, and ownership injection.
- [x] 4.6 Add `POST /api/v1/sessions`, `DELETE /api/v1/sessions/current`, and `PATCH /api/v1/me/password` with correct cookie flags and clearing behavior; verify test-client responses, headers, statuses, generic errors, and post-revocation rejection.
- [x] 4.7 Add log-capture and serialization tests that exercise every authentication failure path; verify passwords, hashes, raw/digested session tokens, and CSRF secrets appear in neither responses nor logs.
- [x] 4.8 Have the orchestrator inspect the KAN-73 diff and run the complete authentication plus existing management suite after the Luna implementation task; verify application construction remains connection-free and startup performs no DDL.

## 5. User and ProfessionalProfile self-service (KAN-74)

- [x] 5.1 Add strict read and patch models for User and the established Skill, Experience, and PreviousProject shapes, reusing existing collection validators; verify schema tests cover required-field preservation, malformed months, unknown fields, replacement arrays, explicit clearing, and omission.
- [x] 5.2 Implement owned User/Profile repositories with typed JSONB round trips, partial updates, writer-maintained timestamps, and post-load validation; verify live-Postgres tests cover valid mappings and rejection of malformed stored collection data.
- [x] 5.3 Implement self-service read/update use cases and `/api/v1/me` plus `/api/v1/me/professional-profile` GET/PATCH routes; verify two-user Flask tests prove self-only access, atomic invalid-patch rejection, omitted-field preservation, and explicit null/array clearing.
- [x] 5.4 Have the orchestrator inspect the KAN-74 diff and rerun focused and management-wide tests after the Luna implementation task; verify the implementation follows current repository profile shapes rather than the conflicting older Jira draft.

## 6. ServiceOffering CRUD (KAN-75)

- [x] 6.1 Add strict offering create/patch/read models and owned repository SQL with deterministic `(created_at, id)` pagination; verify unit and live-Postgres tests cover validation, CRUD, limit-plus-one pagination, timestamps, and ownership predicates.
- [x] 6.2 Implement offering services and `/api/v1/offerings` collection/member routes; verify two-user Flask tests cover 201/200/204 behavior, 404 cross-owner indistinguishability, 422 invalid input, and 409 referenced-delete mapping.
- [x] 6.3 Have the orchestrator inspect the KAN-75 diff and rerun focused and management-wide tests after the Luna implementation task; verify ownership cannot be assigned or transferred by payload.

## 7. IdealClientProfile CRUD and semantics (KAN-76)

- [x] 7.1 Add strict tagged models for industry, Gold-compatible company-size band, country/region geography, and company/industry/geography exclusions; verify schema tests cover every valid variant, invalid discriminator, extra/coerced fields, UUID parsing, whitespace, order, and duplicates.
- [x] 7.2 Add ICP create/patch/read models and owned repository SQL with typed JSONB validation and deterministic pagination; verify unit and live-Postgres tests cover CRUD, full supplied-collection replacement, explicit empty arrays, omitted fields, malformed stored JSON, and ownership predicates.
- [x] 7.3 Implement and unit-test the ICP positive-filter guard before candidate query construction; verify a spy candidate repository is never called when industries, company sizes, or geographies is empty, while complete filters encode OR within dimensions, AND across dimensions, and global exclusion vetoes without Cartesian materialization.
- [x] 7.4 Implement ICP services and `/api/v1/ideal-client-profiles` collection/member routes; verify two-user Flask tests cover lifecycle, pagination, cross-owner 404, progressive incomplete saves, and 409 referenced-delete behavior.
- [x] 7.5 Have the orchestrator inspect the KAN-76 diff and rerun focused and management-wide tests after the Luna implementation task; verify no code path treats an empty positive collection as unrestricted.

## 8. ClientDiscoveryStrategy CRUD (KAN-77)

- [x] 8.1 Add strict strategy create/patch/read models and owned repository SQL with active-state filtering and deterministic pagination; verify unit and live-Postgres tests cover inactive default, CRUD, filtering, and multiple active/shared references.
- [x] 8.2 Implement strategy services that preflight both references as owned resources and rely on composite foreign keys for concurrent/direct-write safety; verify tests cover missing and cross-User offering/ICP references, atomic updates, and constraint translation without resource disclosure.
- [x] 8.3 Implement `/api/v1/discovery-strategies` collection/member routes; verify two-user Flask tests cover lifecycle, activation/deactivation, active filtering, shared references, bounded pages, and cross-owner 404 behavior.
- [x] 8.4 Have the orchestrator inspect the KAN-77 diff and rerun focused and management-wide tests after the Luna implementation task; verify strategy operations do not create or redefine Match records.

## 9. API schema and end-to-end delivery (KAN-78)

- [x] 9.1 Assemble and serve deterministic `/openapi.json` documentation from the registered management routes and Pydantic JSON schemas; verify a contract test validates every implemented path, method, security requirement, request model, response model, and shared error envelope.
- [x] 9.2 Add a live-Postgres two-user end-to-end test covering provision, login, CSRF, User/Profile update, offering/ICP/strategy creation, multiple active strategies, cross-owner isolation, referenced-delete conflicts, logout, and rejected token reuse; verify the test passes independently and as part of the full suite.
- [x] 9.3 Update the management runbook with exact safe fresh-bootstrap, owner provisioning, server, cookie/CSRF, CRUD, verification, and teardown instructions; verify a fresh reader can execute commands without hidden state, embedded credentials, automatic DDL, or destructive commands against an unspecified database.
- [x] 9.4 Run Python 3.14 compilation, Ruff, all unit tests, the PostgreSQL 16 integration suite, full pytest, and `rtk openspec validate management-api-crud --strict`; verify every command and result is recorded in a concise validation report.
- [x] 9.5 Start a fresh-context Sol high local code-review agent only after all implementation and tests are complete; verify it reviews the full diff against the artifacts, ownership/authentication threats, SQL constraints, failure atomicity, tests, and unrelated-file preservation, and records findings by severity with file/line evidence.
- [x] 9.6 Resolve every verified review finding through Luna-scoped implementation under Sol medium orchestration, rerun affected tests and the full gate, and obtain a clear fresh Sol high re-review; verify no unresolved correctness or security finding remains.
- [x] 9.7 Inspect the final diff and working tree, preserve unrelated user files, and commit the reviewed feature with an accurate message; verify the commit contains only intended implementation/specification files. Do not push or open a pull request without separate authorization.
