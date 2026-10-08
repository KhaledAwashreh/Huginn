## Context

See [proposal.md](proposal.md). The user explicitly selected required email verification before login. Source inspection at `.worktrees/simple-matchmaking` `ca2ddd9` found owner-only atomic provisioning, case-insensitive unique username, nonunique `User.email`, Account statuses active/disabled, password hashing, revocable sessions, and no public signup/recovery/email verification. Earlier architecture exclusions are phase boundaries deliberately expanded here; existing change artifacts are not rewritten.

Observed references: `management/application/services/{provisioning,authentication,account_admin}.py`, `application/commands/provisioning.py`, `domain/entities/{account,user}.py`, `security/{passwords,tokens}.py`, `presentation/api/requests/{authentication,user}.py`, `db/schema/operational.sql`, and `docs/management-foundation.md`. Retain the current layered placement and identity validation rather than inventing a second identity service. The user subsequently clarified public form rules: country selection and country-derived phone prefix, and 8–16 character passwords with a letter, an ASCII number and a punctuation/symbol character.

## Goals / Non-Goals

**Goals:** Public signup verification, trusted-owner recovery enrollment, proof-safe reset, durable SMTP delivery, and complete browser flows.

**Non-Goals:** Recovery-email replacement after an address is verified, username renaming, OAuth, MFA, billing, account deletion, or a general notification platform. A changing profile email is explicitly contact-only.

## Decisions

### 1. Keep lifecycle and status separate

Add an `operational.account_recovery_identity` row keyed by Account with `verification_required`, `pending_email`, `verified_email`, `verified_at`, created/updated timestamps. Public signup sets verification_required=true and pending_email to submitted email. Successful verification sets verified_email/verified_at and clears pending_email. Verification does not alter Account.status; login requires active plus either verification_required=false (trusted legacy) or verified_email present. User identity/profile fields retain existing required/optional semantics.

An additive migration creates trusted rows for existing Accounts with verification_required=false and no assumed verified address. Existing accounts continue login; disabled accounts remain disabled. New owner CLI provisioning explicitly creates the trusted row in the same identity transaction. Missing recovery rows after migration are a server integrity error, not an implicit bypass. Existing/owner users enroll a recovery address through `POST /api/v1/me/recovery-email-verifications` with empty JSON, current session and CSRF: snapshot current contact email, queue proof, no session or status change. Reject enrollment with 409 if verified_email already exists. This narrowly completes recovery for existing users without offering unrequested address replacement.

The user subsequently required email uniqueness and email-based check-email forms. Username remains the unique login identifier. Email is the verification-resend and password-recovery identifier. Add case-insensitive, whitespace-normalized unique indexes on User contact email and the recovery identity pending-or-verified destination (COALESCE), excluding null destinations. Signup checks both contact and recovery destinations; a duplicate username or email returns the same generic 202 receipt without changing the existing account or delivery intent. Contact PATCH rejects duplicate contact email without redirecting recovery. Preserve existing data: the additive migration detects conflicting normalized emails and aborts transactionally with operator guidance instead of merging/deleting accounts or assuming verification. Existing addresses are not rewritten or silently verified.

### 2. Explicit application types and layers

The exact inventory below replaces category-only placement. New application ports use `application/protocols`, matching the existing matchmaking convention; persistence ports preserve management's `persistence/contracts` convention.

Domain does not import request models, SMTP types, application projections, or HTTP concerns. Application transaction services validate before repositories, then atomically write identity/proof/outbox. Mail worker is a separate process and uses its sender Protocol; no FastAPI BackgroundTasks, broker, or delivery in an open identity transaction.

### 3. HTTP contracts

All paths are under `/api/v1`; public endpoints return existing sanitized validation and error contracts. Origin/Fetch-Metadata checks reject cross-origin browser mutations, require JSON, and preserve operator clients without browser headers. Authenticated enrollment uses normal session CSRF.

| Endpoint | Request | Success |
| --- | --- | --- |
| `POST /accounts` | username, password, first_name, last_name, email, phone_number, country_of_residence, optional timezone | 202 `{message: "Check your email for next steps"}` for valid input, including duplicate username or email |
| `POST /email-verifications` | token | 204 after valid explicit consumption |
| `POST /email-verifications/resend` | email | Generic 202 receipt |
| `POST /me/recovery-email-verifications` | `{}` and session/CSRF | Generic 202 after eligible authenticated enrollment |
| `POST /password-resets` | email | Generic 202 receipt |
| `POST /password-resets/complete` | token, new_password | 204 after atomic reset/revocation |
| `GET /me/account-security` | session | `{username, email_verification_required, email_verified, recovery_email}` for the owner only |

`recovery_email` is the verified address or null; do not return pending proof/address to anonymous callers. Login remains generic 401 for unverified as for invalid credentials, preventing account-state enumeration. Public proof submission returns generic 422 for unusable proof without identifying an Account. Public unknown, disabled, and ineligible receipt paths have equivalent response shapes and avoid distinguishable expensive hashing behavior. Do not promise cryptographically exact constant latency; perform comparable bounded work and add security tests for obvious differences.

Public signup and reset passwords use 8–16 Unicode code points, contain a Unicode letter, an ASCII digit and a Unicode punctuation/symbol character, and reject control characters. Whitespace does not count as a special character. Enforce identical rules in browser and application/HTTP validation. Login still accepts previously stored longer passwords; do not impose creation composition on existing credentials. Extend existing `security/password_policy.py` and `security/passwords.py` rather than introducing another security module.

Signup uses a labeled country dropdown of the 245 two-letter regions with calling codes in Google libphonenumber metadata. Store the selected region code. Show its calling prefix beside a national-number field, preserve national digits when changing country, and submit one E.164 value. Reject missing/unknown countries, invalid phone digits/length (at least three national digits, at most 15 total E.164 digits) and mismatched prefix on the server. Keep immutable calling-code maps in existing `application/constants/lifecycle_policy.py` and frontend `forms/signupDraft.ts`; no new dependency or runtime metadata request.

### 4. Proof policy and mail safety

Use at least 256-bit random proofs, stored only as digest with Account, purpose (`verify_email` or `reset_password`), exact destination snapshot, expires_at, consumed_at, and superseded flag. Default verification lifetime 24 hours; reset 30 minutes; configurable bounded values. Same-purpose replacement invalidates previous proofs transactionally. Lock proof/Account during consumption so only one concurrent use commits. Verification accepts pending signup or owner-enrollment proof and never activates disabled accounts. Reset requires verified recovery destination matching the proof snapshot and current identity. Password reset revokes all sessions and outstanding reset proofs in one transaction.

Frontend links carry token in URL fragment (`/verify-email#token=...`, `/reset-password#token=...`) so it is absent from request URLs and access logs; page moves it to local memory and replaces history. Pages submit POST only when the user clicks verify/save. Apply `Referrer-Policy: no-referrer`; no third-party analytics on proof pages. Reload after history clearing requires reopening the original mail link. Token values are never query cache keys.

Use persisted throttling keyed by normalized email digest and trusted client-IP identity: default 5 receipt requests per email and 20 per IP per hour. Signup additionally reserves its normalized username limit. All limits are enforced before identity lookup identically for eligible and unknown identifiers; generic 429 with Retry-After. A 60-second per-account mail-delivery cooldown is internal only and still returns generic 202 when suppressing a resend; it never produces an account-dependent 429. Proof attempts are also bounded (10 per IP per minute). Do not trust arbitrary forwarded IP headers. Values are server configuration, not browser parameters. Avoid logging plaintext usernames/emails on public lifecycle endpoints.

The transactional outbox contains a lifecycle message ID, Account, purpose, recipient snapshot, proof material protected with authenticated encryption, attempt count, next_attempt_at, delivery state, safe failure code, and timestamps. The encryption key is server configuration, not in SQL or logs. Protect queued plaintext-equivalent secrets, scrub proof payload after successful send or terminal expiry, and retain safe delivery metadata only. Use configurable SMTP host/port/TLS/sender/credentials and trusted web origin; a local SMTP sink is supported for development, no vendor lock-in. SMTP retries are bounded (5 attempts, exponential backoff capped at 15 minutes). Before send, re-read the bound proof and identity: suppress deliveries known expired, superseded, consumed, disabled, or no longer matching the pending/verified destination. A concurrent invalidation during SMTP can still deliver an unusable link, but it cannot restore proof validity.

Mail workers claim due rows using a short `FOR UPDATE SKIP LOCKED` transaction, record a random claim-owner token, claimed_at/lease_until, and increment attempts before committing; SMTP runs outside the transaction with a bounded 30-second timeout and a120-second claim lease. Settlement/backoff writes are conditional on row ID and claim token. Expired claims are reclaimable, stale workers cannot overwrite a later claim, and five total claims exhaust the retry budget even after crashes. Workers stop claiming on shutdown and finish or expire their current bounded attempt. At-least-once SMTP may deliver duplicate links after uncertain send or a stalled process outliving its lease; identical links remain safe single-use and no receipt claims delivery success. Email worker has its own narrow process and durable claim policy, separate from pipeline invocation worker.

### 5. Browser UX

Routes: `/create-account`, `/check-email`, `/verify-email`, `/forgot-password`, `/reset-password`; foundation owns `/login`. Show required identity fields and explicit email-verification notice. Email is the label on forgot/resend and check-email forms. Retain only email and purpose in non-secret receipt navigation state; signup and login retain username. Validate email before requests, preserve drafts and show actionable field/rate-limit/connectivity guidance. Verification completion links to login, no automatic login. Empty/invalid/expired proof states offer resend or request-reset guidance. Profile account security explains contact email versus verified recovery email; enrollment action appears only for eligible trusted accounts lacking one. Secret inputs are local memory; non-secret drafts survive failed submission but no browser persistence is introduced.

## Risks / Trade-offs

- [Existing duplicate email data] → Abort the additive uniqueness migration without changing account data; resolve records through an explicit operator decision.
- [Editable contact email hijack] → Recovery snapshot stored separately and change flow explicitly deferred.
- [SMTP uncertain delivery] → At-least-once outbox, single-use proof, bounded retry, honest receipts.
- [Legacy trusted accounts] → Preserve login, require explicit address proof for recovery, no fabricated verification backfill.
- [Outbox secrecy] → Authenticated encryption, deployment key prerequisite, payload scrubbing and secret-free logs.

## Migration Plan

Implement additive lifecycle/proof/outbox/throttle tables, normalized email uniqueness and an idempotent trusted-account backfill; no resets or deletion of shared data. Duplicate-email preflight must fail before backfill or index creation and roll back the complete migration. Apply explicit operator migrations before enabling registration; boot does not apply DDL. Deploy SMTP worker/key/config, then enable new endpoints/pages. Verify migrations and concurrency against fresh and legacy-shaped disposable PostgreSQL 16 databases. Rollback disables public routes/mail worker while preserving identity/proof tables. An older server would ignore verification gates, so it MUST NOT be used for login to new public accounts during rollback; retain the gate or disable public-account login operationally.

## Shared standards dependency

The authoritative [foundation implementation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) govern this change: exact Node/npm/dependency locks, strict TypeScript, naming, offline schema drift, lint/format/test/CI/hook gates, WCAG 2.2 AA target, and Python layer placement. Consume shared components and transport; do not introduce divergent tooling or duplicate session/database ports. The inventories below define the new production files/types for this feature. Package `__init__.py` markers are empty, not public re-export umbrellas. Test files mirror these use cases and add the behavior scenarios already specified in this design.

## Exact lifecycle inventory

Paths relative to `src/huginn/management/`; API request names deliberately occupy a separate namespace from frozen application requests. Mail outbox/throttle are persistence delivery/bookkeeping rows, not domain entities. Query/delivery projections remain application types and are never imported into domain. Identity/proof persistence contracts return domain entities. Outbox/throttle application ports return immutable application projections; persistence adapters map private row models into those projections. Application services never import row models. No domain/application inversion.

| Exact path | Named types / exports |
| --- | --- |
| `domain/entities/account_recovery_identity.py` | AccountRecoveryIdentity |
| `domain/entities/account_lifecycle_proof.py` | AccountLifecycleProof |
| `domain/value_objects/verification_state.py` | VerificationState |
| `domain/value_objects/proof_purpose.py` | ProofPurpose |
| `domain/errors/lifecycle.py` | LifecycleProofError; invariant validation only |
| `application/read_models/account_security.py` | AccountSecurity |
| `application/read_models/lifecycle_mail_message.py` | LifecycleMailMessage (secret hidden from repr) |
| `application/read_models/lifecycle_mail_outbox.py` | LifecycleMailOutboxRecord; immutable delivery metadata/protected proof input |
| `application/read_models/lifecycle_throttle.py` | LifecycleThrottleReservation; immutable admission result |
| `application/read_models/mail_delivery_claim.py` | MailDeliveryClaim (claim owner/lease, secret hidden from repr) |
| `application/protocols/lifecycle_mail_sender.py` | LifecycleMailSender Protocol |
| `application/protocols/proof_cipher.py` | ProofCipher Protocol |
| `application/constants/lifecycle_policy.py` | VERIFICATION_TTL_SECONDS, RESET_TTL_SECONDS, MAIL_MAX_ATTEMPTS, MAIL_TIMEOUT_SECONDS, MAIL_CLAIM_LEASE_SECONDS, MAIL_COOLDOWN_SECONDS, RECEIPT_USERNAME_LIMIT, RECEIPT_IP_LIMIT, PROOF_IP_LIMIT, COUNTRY_CALLING_CODES |
| `application/errors/lifecycle.py` | LifecycleConflictError, LifecycleRateLimitError, LifecycleIntegrityError |
| `application/requests/signup_request.py` | SignupRequest |
| `application/responses/signup_response.py` | SignupResponse |
| `application/services/signup_service.py` | SignupService.execute(SignupRequest) -> SignupResponse |
| `application/requests/verify_email_request.py` | VerifyEmailRequest |
| `application/responses/verify_email_response.py` | VerifyEmailResponse |
| `application/services/verify_email_service.py` | VerifyEmailService.execute(VerifyEmailRequest) -> VerifyEmailResponse |
| `application/requests/resend_verification_request.py` | ResendVerificationRequest |
| `application/responses/resend_verification_response.py` | ResendVerificationResponse |
| `application/services/resend_verification_service.py` | ResendVerificationService.execute(ResendVerificationRequest) -> ResendVerificationResponse |
| `application/requests/enroll_recovery_email_request.py` | EnrollRecoveryEmailRequest |
| `application/responses/enroll_recovery_email_response.py` | EnrollRecoveryEmailResponse |
| `application/services/enroll_recovery_email_service.py` | EnrollRecoveryEmailService.execute(EnrollRecoveryEmailRequest) -> EnrollRecoveryEmailResponse |
| `application/requests/forgot_password_request.py` | ForgotPasswordRequest |
| `application/responses/forgot_password_response.py` | ForgotPasswordResponse |
| `application/services/forgot_password_service.py` | ForgotPasswordService.execute(ForgotPasswordRequest) -> ForgotPasswordResponse |
| `application/requests/reset_password_request.py` | ResetPasswordRequest |
| `application/responses/reset_password_response.py` | ResetPasswordResponse |
| `application/services/reset_password_service.py` | ResetPasswordService.execute(ResetPasswordRequest) -> ResetPasswordResponse |
| `application/requests/get_account_security_request.py` | GetAccountSecurityRequest |
| `application/responses/get_account_security_response.py` | GetAccountSecurityResponse |
| `application/services/get_account_security_service.py` | GetAccountSecurityService.execute(GetAccountSecurityRequest) -> GetAccountSecurityResponse |
| `application/requests/deliver_lifecycle_mail_request.py` | DeliverLifecycleMailRequest |
| `application/responses/deliver_lifecycle_mail_response.py` | DeliverLifecycleMailResponse |
| `application/services/deliver_lifecycle_mail_service.py` | DeliverLifecycleMailService.execute(DeliverLifecycleMailRequest) -> DeliverLifecycleMailResponse |
| `persistence/contracts/repositories/account_recovery_identity.py` | AccountRecoveryIdentityRepository Protocol |
| `persistence/repositories/account_recovery_identity.py` | PostgresAccountRecoveryIdentityRepository |
| `persistence/row_models/account_recovery_identity.py` | AccountRecoveryIdentityRow; persisted record only |
| `persistence/contracts/repositories/account_lifecycle_proof.py` | AccountLifecycleProofRepository Protocol |
| `persistence/repositories/account_lifecycle_proof.py` | PostgresAccountLifecycleProofRepository |
| `persistence/row_models/account_lifecycle_proof.py` | AccountLifecycleProofRow; persisted record only |
| `application/protocols/lifecycle_mail_outbox.py` | LifecycleMailOutboxRepository Protocol |
| `persistence/repositories/lifecycle_mail_outbox.py` | PostgresLifecycleMailOutboxRepository |
| `persistence/row_models/lifecycle_mail_outbox.py` | LifecycleMailOutboxRow; persisted record only |
| `application/protocols/lifecycle_throttle.py` | LifecycleThrottleRepository Protocol |
| `persistence/repositories/lifecycle_throttle.py` | PostgresLifecycleThrottleRepository |
| `persistence/row_models/lifecycle_throttle.py` | LifecycleThrottleRow; persisted record only |
| `security/lifecycle_proofs.py` | generate_lifecycle_proof, digest_lifecycle_proof |
| `security/encrypted_proof_cipher.py` | EncryptedProofCipher implements ProofCipher; authenticated encryption |
| `delivery/smtp_lifecycle_mail_sender.py` | SmtpLifecycleMailSender implements LifecycleMailSender |
| `delivery/templates/verify_email.py` | render_verification_mail |
| `delivery/templates/reset_password.py` | render_reset_mail |
| `presentation/cli/lifecycle_mail_worker.py` | main; invokes delivery service |
| `presentation/api/routers/account_lifecycle.py` | public lifecycle routes |
| `presentation/api/routers/account_security.py` | authenticated enrollment/security routes |
| `presentation/api/requests/signup.py` | SignupRequest HTTP model |
| `presentation/api/requests/verify_email.py` | VerifyEmailRequest HTTP model |
| `presentation/api/requests/resend_verification.py` | ResendVerificationRequest HTTP model |
| `presentation/api/requests/enroll_recovery_email.py` | EnrollRecoveryEmailRequest HTTP model |
| `presentation/api/requests/forgot_password.py` | ForgotPasswordRequest HTTP model |
| `presentation/api/requests/reset_password.py` | ResetPasswordRequest HTTP model |
| `presentation/api/responses/lifecycle_receipt.py` | LifecycleReceiptResponse |
| `presentation/api/responses/account_security.py` | AccountSecurityResponse |

Reuse/extend `persistence/contracts/unit_of_work.py` (`UnitOfWorkProtocol`) and `persistence/database/unit_of_work.py` (`UnitOfWork`) transaction boundary, existing database contracts and repository base; inject new repositories from `app.py`/`presentation/api/dependencies/services.py` on the same connection. Extend `config.py` (`ManagementConfig`) for bounded lifecycle/SMTP/key settings, `application/services/provisioning.py` for trusted-row creation, `application/services/authentication.py` for verification gate, `presentation/api/errors/handlers.py` for safe mappings. Reuse identity/password/session/principal validation and revocation. Extend `db/schema/operational.sql`; additive operator migration is `db/schema/operational-account-lifecycle.sql`, including recovery identity, proofs, outbox, throttle and trusted backfill. Use the existing `db/schema/` additive hyphenated SQL naming convention, not a new migration framework/directory. No boot DDL.

### Frontend inventory

Relative to `frontend/src/features/account-lifecycle/`; wire routes into existing app router and optional enrollment component into workspace account page.

| Exact path | Named types / exports |
| --- | --- |
| `pages/CreateAccountPage.vue` | CreateAccountPage |
| `pages/CheckEmailPage.vue` | CheckEmailPage |
| `pages/VerifyEmailPage.vue` | VerifyEmailPage |
| `pages/ForgotPasswordPage.vue` | ForgotPasswordPage |
| `pages/ResetPasswordPage.vue` | ResetPasswordPage |
| `components/RecoveryEmailEnrollment.vue` | RecoveryEmailEnrollment; optional workspace integration |
| `api/signup.ts` | signup |
| `api/verifyEmail.ts` | verifyEmail |
| `api/resendVerification.ts` | resendVerification |
| `api/enrollRecoveryEmail.ts` | enrollRecoveryEmail |
| `api/forgotPassword.ts` | forgotPassword |
| `api/resetPassword.ts` | resetPassword |
| `api/getAccountSecurity.ts` | getAccountSecurity |
| `forms/signupDraft.ts` | SignupDraft, COUNTRY_CALLING_CODES, COUNTRY_OPTIONS, callingCodeForCountry, normalizeE164Phone |
| `forms/resetPasswordDraft.ts` | ResetPasswordDraft, validateLifecyclePassword |
| `composables/useProofFragment.ts` | useProofFragment; memory/history sanitization |
| `composables/useAccountSecurity.ts` | useAccountSecurity |
| `routes.ts` | accountLifecycleRoutes |
