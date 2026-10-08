# Public account lifecycle

Public signup requires email verification before login. Username identifies
login; email identifies verification resend and password recovery. Contact
email and pending-or-verified recovery destinations are each unique across
accounts, ignoring case and surrounding whitespace. The verified recovery address is separate from
editable profile contact email. Changing contact email never redirects
recovery, and this release offers no verified-address replacement.

Signup offers a country dropdown and derives the phone calling prefix from
that choice. Enter the national number; spaces and hyphens are normalized.
Signup and reset passwords require 8–16 characters, a letter, a number and a
special character. Browser and server enforce the same rules. Existing longer
passwords remain usable for login.

## Deployment

1. Apply the additive migration before deploying lifecycle account writers:

   ```bash
   rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/operational-account-lifecycle.sql
   ```

   The migration owns its transaction. It preserves accounts, passwords and
   active/disabled state, and backfills trusted recovery identities without
   assuming contact addresses are verified. If normalized duplicate contact
   or recovery addresses exist, the migration aborts transactionally with
   operator guidance. Resolve their ownership through an explicit operator
   decision before retrying. It never merges or deletes accounts, rewrites
   addresses or silently verifies them. Reapplication preserves pending
   public accounts and verified destinations. Fresh databases receive the
   same tables from `operational.sql`; follow [schema instructions](../db/schema/README.md)
   for a new dedicated database. Never reset a shared database.

2. Configure the management API and the separate mail worker with the same
   database, authenticated-encryption key and trusted web origin. Generate a
   Fernet key with the installed Python environment and store it in deployment
   secret configuration:

   ```bash
   rtk proxy .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   Set `HUGINN_LIFECYCLE_PROOF_KEY` to that key and `HUGINN_WEB_ORIGIN` to the
   browser origin, such as `https://huginn.example`. An origin has no credentials,
   query or fragment and no path other than `/`. Staging and production require
   HTTPS. Keep the key stable while queued ciphertext remains; replacing it
   makes earlier queued payloads unreadable. Do not put it in source control,
   SQL, logs or command-line arguments.

3. Configure SMTP:

   | Environment variable | Default / accepted values |
   | --- | --- |
   | `HUGINN_SMTP_HOST` | `localhost` |
   | `HUGINN_SMTP_PORT` | `1025`, range 1–65535 |
   | `HUGINN_SMTP_TLS` | `none`, `starttls`, `implicit` |
   | `HUGINN_SMTP_SENDER` | `no-reply@huginn.local` |
   | `HUGINN_SMTP_USERNAME` / `HUGINN_SMTP_PASSWORD` | Optional paired credentials |

   Use a local SMTP sink with `none` for development. Use the transport settings
   required by your deployment mail server. The API can boot without lifecycle
   mail configuration; requests needing a new delivery intent return a sanitized
   503 until the key and origin are configured. The worker requires both.

4. Run the mail worker separately from the API:

   ```bash
   rtk proxy .venv/bin/python -m huginn.management.presentation.cli.lifecycle_mail_worker --once
   rtk proxy .venv/bin/python -m huginn.management.presentation.cli.lifecycle_mail_worker --poll-seconds 5
   ```

   `--once` claims at most one message. Poll seconds must be 1–60. SIGINT/SIGTERM
   stops new claims and lets the current bounded attempt finish. Normal startup
   never applies DDL. See [management foundation](management-foundation.md)
   for API startup and session configuration.

## Delivery and recovery

Signup commits Account, User, empty Profile, pending recovery identity, proof
and encrypted delivery intent together. It issues no session. Duplicate signup,
resend and forgot-password receipts never claim that mail was sent or reveal
account eligibility. Verification and reset links use fragments; opening a
page does not consume a proof. Click Verify email or Save password explicitly.
The browser clears the fragment and keeps proof material only in page memory.
Reopening the original mail link is necessary after reload.

Existing trusted accounts retain login after migration. An authenticated trusted
owner without a verified destination can use Account security to verify their
current contact-email snapshot. A verified destination cannot be replaced in
this release. Missing recovery-identity rows are integrity failures, never an
implicit verification bypass. Owner provisioning creates the trusted row in
the same transaction as the account.

Reset changes the password, revokes every session and invalidates outstanding
reset proofs atomically. The browser clears its session and requires explicit
login with the new password. Disabled accounts remain disabled.

The outbox encrypts recipient and raw proof together. Workers claim using
`FOR UPDATE SKIP LOCKED`, commit a random owner token and 120-second lease,
then perform SMTP outside the identity transaction. Each claim increments the
five-attempt budget. The whole SMTP attempt has a 30-second bound; guarded
identity/ownership/settlement queries have five-second SQL bounds. Workers
check current proof, identity and live ownership before sending. Terminal
outcomes scrub ciphertext; logs contain safe message IDs and outcome codes.
Retry backoff starts at 60 seconds, doubles and caps at 15 minutes.

SMTP acceptance and SQL settlement cannot commit together. A crash or uncertain
send can deliver the same link again. Lease tokens fence stale settlement;
single-use proofs keep duplicate mail safe. A proof invalidated during SMTP
may arrive but remains unusable. Exhausted or invalid-payload messages are
terminal; a user can request a replacement under the normal limits.

| Policy variable | Default | Allowed maximum |
| --- | --- | --- |
| `HUGINN_VERIFICATION_TTL_SECONDS` | 86400 | 604800 |
| `HUGINN_RESET_TTL_SECONDS` | 1800 | 86400 |
| `HUGINN_RECEIPT_USERNAME_LIMIT` | 5 per hour | 1000 |
| `HUGINN_RECEIPT_EMAIL_LIMIT` | 5 per hour | 1000 |
| `HUGINN_RECEIPT_IP_LIMIT` | 20 per hour | 10000 |
| `HUGINN_PROOF_IP_LIMIT` | 10 per minute | 1000 |

All policy values must be positive integers. Signup reserves username and email
limits; resend and recovery reserve email limits. Persisted limits run before account
lookup. A separate 60-second delivery cooldown returns the same generic receipt.
Client identity uses the direct peer address, never arbitrary forwarded headers.

## Verification and rollback

Lifecycle tests use disposable PostgreSQL 16 from `tests.postgres_harness`.
Browser tests start the real API, a loopback SMTP sink and a test-only mailbox
viewer on port 8025. The viewer is part of the test fixture, not the production
API. It exposes test proofs and must remain loopback-only. The fixture generates
its own temporary encryption key and destroys its provisioned database on exit.

The current local preview also captures SMTP locally. Open
`http://127.0.0.1:8025/messages` to view its messages and open their links manually.
This server does not deliver to a real inbox and incurs no email-service charge.
The user explicitly deferred connecting a real SMTP service; provider credentials
and production delivery remain deployment configuration for later.

```bash
rtk proxy .venv/bin/python -m pytest -q
rtk proxy .venv/bin/python -m compileall -q src tests
rtk proxy .venv/bin/ruff check .
rtk proxy .venv/bin/ruff format --check .
rtk proxy npm --prefix frontend run check
rtk proxy npm --prefix frontend run test:e2e
rtk openspec validate public-account-lifecycle --strict
```

Use foundation's pinned Node 24/npm 12.2.0 and installed Playwright Chromium
for frontend commands. Browser tests require Docker and free loopback ports
8000, 4173 and 8025. See [web UI foundation](web-ui-foundation.md) for prerequisites.

Rollback stops public lifecycle traffic and the mail worker while retaining
the additive tables. Keep the verification gate for public accounts or disable
their login operationally. An older login server without that gate would admit
unverified public accounts. Do not drop recovery/proof/outbox tables or reset
account data as a rollback shortcut.
