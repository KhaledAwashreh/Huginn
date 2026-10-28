# Weekly research digest

The digest is one scheduled command using the existing SMTP configuration and
Python standard library. It generates up to five fresh recommendations for an
explicitly subscribed pilot user, saves the email content, and sends plain text
with a link to the exact saved batch for feedback. There is no provider SDK,
campaign dashboard or new background queue.

## Configure once

1. Deploy the recommendation flow first. Apply its migration, followed by this
   additive migration through the normal schema-owner process:

   ```sh
   rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f db/schema/operational-weekly-digest.sql
   ```

2. Use a free SMTP account. Brevo currently includes 300 sends per day on its
   free plan. Authenticate your sender domain and create an SMTP key. Set these
   existing application variables in the ignored deployment environment:

   ```dotenv
   HUGINN_SMTP_HOST=smtp-relay.brevo.com
   HUGINN_SMTP_PORT=587
   HUGINN_SMTP_TLS=starttls
   HUGINN_SMTP_USERNAME=your-brevo-smtp-login
   HUGINN_SMTP_PASSWORD=your-brevo-smtp-key
   HUGINN_SMTP_SENDER=weekly@your-verified-domain.example
   HUGINN_WEB_ORIGIN=https://your-huginn-domain.example
   ```

   Keep the existing `HUGINN_MANAGEMENT_DATABASE_URL` and
   `HUGINN_LIFECYCLE_PROOF_KEY` configured. The key signs purpose-specific
   unsubscribe links; rotating it invalidates old links. Production/staging
   requires SMTP TLS. No real provider account or credentials are created by
   this implementation, and application startup never applies migrations.

3. Explicitly opt in a pilot user with an active owned strategy and verified
   email. Delivery uses the verified account address, not editable contact email:

   ```sh
   rtk uv run python -m huginn.management.weekly_digest subscribe \
     --user-id USER_UUID --strategy-id STRATEGY_UUID
   rtk uv run python -m huginn.management.weekly_digest send --dry-run
   ```

   Dry run counts eligible subscriptions only; it does not generate batches,
   reserve delivery slots or contact SMTP. Opt-in is operator-managed for this
   pilot, with one strategy per user. Do not bulk-enroll users without opt-in.

4. Schedule `python -m huginn.management.weekly_digest send` for Monday at
   09:00 UTC with cron or your existing scheduler. For example, in a crontab
   whose timezone is UTC, replace these paths with the deployment paths:

   ```cron
   0 9 * * 1 cd /srv/Huginn && /srv/Huginn/.venv/bin/python -m huginn.management.weekly_digest send >> /srv/Huginn/.local-runtime/weekly-digest.log 2>&1
   ```

   Refresh source data through the existing pipeline before the digest job.
   The command does not fetch upstream sources. It creates a new recommendation
   batch from current guarded evidence using the built-in ranker.

Provider references checked 2026-10-28:
[free-plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan),
[SMTP configuration](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP).
An SMTP key is distinct from a Brevo API key. The implementation also works with
other SMTP providers through the same settings.

## Delivery behavior

1. At most one automatic attempt per user per UTC Monday-based week. A unique
   database reservation prevents concurrent jobs and repeated cron runs from
   producing another attempt. Prepared content, recipient, batch identity and
   company IDs are retained. Previously sent or uncertain-delivery companies
   are excluded from later digest generation.
2. The default is at most 100 eligible users per run and 100 reservations per
   UTC day. `--limit` and `--daily-limit` accept 1 through 250. Reservations,
   including empty/preparation-failure cases, count conservatively against the
   application budget. Never/oldest-served users come first. For a pilot larger
   than the daily limit, run daily to spread one digest per user across the
   week, or choose an appropriate provider plan.
3. The budget is for digests. Account verification/reset mail shares the SMTP
   provider's allowance, so leave headroom and check provider usage. Provider
   quotas are enforced by the provider; this is not a global account quota API.
4. No new recommendations means no empty email. Disabled accounts, unsubscribed
   users, inactive strategies and unverified addresses are not eligible. The
   subscription and verified recipient are checked again before preparing SMTP.
5. SMTP acceptance and database settlement cannot be atomic. A send error is
   recorded as `unknown`, and an interrupted attempt can remain `preparing` or
   `sending`. These are not automatically retried that week. This favors
   avoiding duplicate email over recovering every missed message. Investigate
   provider logs before any manual resend; do not blindly reset reservations.
6. Email links preserve the saved recommendation batch instead of showing a
   newer assessment. The opt-out link first displays a confirmation; opening
   or scanning it does not unsubscribe. Its signed capability stays in the URL
   fragment and is submitted only in the confirmation POST body, keeping it out
   of standard access-log URLs. Confirming stops future weekly emails.
   The operator can also run:

   ```sh
   rtk uv run python -m huginn.management.weekly_digest unsubscribe --user-id USER_UUID
   ```

The CLI returns safe JSON counts and exits nonzero for preparation failures or
uncertain SMTP outcomes. Logs do not include recipients, message bodies, SMTP
passwords or unsubscribe signatures. No production scheduler or provider send is
enabled automatically.
