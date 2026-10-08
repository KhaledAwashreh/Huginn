## 1. Additive identity and proof contracts

- [x] 1.1 Apply after foundation browser contracts are available and compare actual identity/auth source; record baseline and verify no earlier change artifacts or unrelated files are modified.
- [x] 1.2 Add separate recovery-identity/proof entities, value objects, domain errors, repository/UoW Protocols and row models; verify domain has no application/HTTP/delivery dependencies and validation tests cover state/purpose/destination.
- [x] 1.3 Add idempotent lifecycle/proof/outbox/throttle migrations and trusted-account backfill; verify fresh and legacy-shaped disposable PostgreSQL 16 databases retain usernames/passwords/active-disabled state and gain no fabricated verified addresses.
- [x] 1.4 Extend trusted provisioning transaction to create recovery identity without granting admin; verify rollback leaves no partial identity and existing CLI provisioning remains usable.

## 2. Public lifecycle services and API

- [x] 2.1 Implement separate signup request/response/service with atomic identity, proof and encrypted delivery intent; verify valid signup creates all rows, duplicate username gives generic 202 and privileged/unknown inputs give sanitized 422.
- [x] 2.2 Implement verification request/response/service and login gate; verify single-use/expiry/concurrent consumption, generic 401 preverification, and disabled accounts never reactivate.
- [x] 2.3 Implement email resend and persisted prelookup limits plus invisible delivery cooldown; verify pending/verified/unknown emails share 202 behavior and identical 429 public limit policy.
- [x] 2.4 Implement authenticated initial recovery enrollment and account-security read response; verify contact-email snapshot needs proof, already-verified destination rejects replacement, and contact PATCH never redirects recovery.
- [x] 2.5 Implement email forgot/reset services and endpoints; verify ineligible receipts are generic, reset atomically changes password/revokes all sessions/proofs, and concurrent proof consumption commits once.
- [x] 2.6 Add strict API request/response models, origin guard reuse, safe errors and OpenAPI types; verify unexpected fields, proof failure, throttling and no secrets in logs/responses with API contract tests.

## 3. Durable SMTP delivery

- [x] 3.1 Add lifecycle sender Protocol, per-purpose templates, trusted-origin fragment links and configurable SMTP adapter; verify local SMTP sink delivery and no scanner GET can consume proof.
- [x] 3.2 Add dedicated mail-worker CLI with SKIP LOCKED claim, random token/lease, bounded timeout/attempt/backoff and conditional settlement; verify competing workers, crash reclaim, stale settlement fencing, uncertain-send duplicate safety and exhaustion.
- [x] 3.3 Add current-proof/identity checks and encrypted-payload scrubbing after sent/obsolete/expired outcomes; verify known superseded/consumed/disabled proofs are suppressed and encryption secrets/addresses/proofs are absent from exported logs.

## 4. Public pages and account integration

- [x] 4.1 Add create-account/check-email/verify-email pages using foundation controls; verify required personal fields, explicit verification notice, resend limits, expired link, and explicitPOST consumption.
- [x] 4.2 Add forgot/reset pages and login links; verify email label, proof fragment removal, secret-memory-only handling, reset-to-login and safe invalid-proof states.
- [x] 4.3 Add optional Account security section for verified recovery destination and trusted-owner initial enrollment; verify profile contact email distinction and no replacement/self-promotion control appears.

## 5. Integration and release readiness

- [x] 5.1 Exercise signup→SMTP sink→verification→login→contact change→recovery→reset against disposable PostgreSQL 16 and browser fixtures; verify old sessions revoke and new contact email is not used as recovery destination.
- [x] 5.2 Document mail-key/SMTP/web-origin prerequisites, trusted enrollment, migration and guarded rollback; verify runbook commands and keep local implementation log/current task checkboxes.
- [x] 5.3 Run frontend type/lint/build/browser checks, Python 3.14 compilation, Ruff check/format, full pytest with live PostgreSQL 16 integration, strict OpenSpec validation and exact file/type inventory/dependency review against the chosen implementation base and fresh Sol high review; resolve findings before separately authorized commit/push.

## 6. User feedback: unique email and actionable forms

- [x] 6.1 Add normalized email uniqueness for contact and recovery destinations; verify duplicate/signup races, conflicting contact updates and an idempotent migration that aborts on duplicate legacy data without deleting or changing accounts.
- [x] 6.2 Use email for verification resend, password recovery and check-email forms; verify strict email input, prelookup email throttling, preserved recovery snapshots and safe generic receipts.
- [x] 6.3 Improve generic and action-specific error guidance; document that the current preview captures SMTP locally and real SMTP setup is deferred by the user.
- [x] 6.4 Regenerate API types and rerun compilation, Ruff, full live PostgreSQL 16 pytest, frontend/browser gates, strict OpenSpec and fresh Sol high review; preserve preview data and unrelated worktrees, and keep log current.
