# Weekly Matches email

The digest is one scheduled command using the existing SMTP configuration and
Python standard library. It selects up to seven distinct companies across all valid active strategies for an
explicitly subscribed user, saves the email content, and sends plain text
with a link to the exact weekly selection for feedback. There is no user-facing
weekly generation action; Recommendations remain on demand for one strategy. There is no provider SDK,
campaign dashboard or new background queue.

## Configure once

1. Deploy the recommendation flow first. Apply its migration, followed by this
   migration through the normal schema-owner process. Reapply it when upgrading:
   existing subscriptions retain consent but now cover all active strategies;
   the obsolete subscription strategy column is removed. Delivery history is preserved:

   ```sh
   rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f db/schema/gold-current-source-evidence.sql \
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
     --user-id USER_UUID
   rtk uv run python -m huginn.management.weekly_digest send --dry-run
   ```

   Dry run counts eligible subscriptions only; it does not generate batches,
   reserve delivery slots or contact SMTP. Opt-in is operator-managed for this
   pilot. Each subscription covers all valid active strategies and their offerings. Do not bulk-enroll users without opt-in.

4. Schedule `python -m huginn.management.weekly_digest send` for Monday at
   09:00 UTC with cron or your existing scheduler. For example, in a crontab
   whose timezone is UTC, replace these paths with the deployment paths:

   ```cron
   0 9 * * 1 cd /srv/Huginn && /srv/Huginn/.venv/bin/python -m huginn.management.weekly_digest send >> /srv/Huginn/.local-runtime/weekly-digest.log 2>&1
   ```

   Refresh source data through the existing pipeline before the digest job.
   The command does not fetch upstream sources. It creates a new recommendation
   selection from current guarded evidence using the shared built-in ranker.
   ICP filters use OR within each populated field and AND across fields. Known
   mismatches and explicit exclusions are removed; missing attributes remain
   eligible and visibly unverified, earning no ICP match points. Weekly ranking
   selects the strongest seven distinct companies without adding scores across
   overlapping strategies or forcing a quota per offering. Fewer eligible
   companies produce fewer entries; the job does not weaken filters to fill seven.

Provider references checked 2026-10-28:
[free-plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan),
[SMTP configuration](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP).
An SMTP key is distinct from a Brevo API key. The implementation also works with
other SMTP providers through the same settings.

## Delivery behavior

1. At most one automatic attempt per user per UTC Monday-based week. A unique
   database reservation prevents concurrent jobs and repeated cron runs from
   producing another attempt. Prepared content, recipient, batch identity and
   company IDs are retained. Source line endings are normalized in the frozen
   email body so the saved plaintext and received SMTP plaintext agree. Previously sent or uncertain-delivery companies
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
   users, inactive strategies and unverified addresses are not eligible.
   Strategies whose ICP selects and excludes the same value are skipped until
   corrected; their existing configuration and historical batches are preserved. The
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
   of standard access-log URLs. Links are bound to the verified recipient and
   subscription version; changing recipient or subscribing again invalidates
   older links. Confirming stops future weekly emails. An email already being
   handed to SMTP can still arrive if opt-out or a recipient change races with
   delivery preparation and transport; the database transaction and SMTP
   acceptance cannot be atomic.
   Later sends are excluded by subscription and recipient eligibility checks.
   The operator can also run:

   ```sh
   rtk uv run python -m huginn.management.weekly_digest unsubscribe --user-id USER_UUID
   ```

The CLI returns safe JSON counts and exits nonzero for preparation failures or
uncertain SMTP outcomes. Logs do not include recipients, message bodies, SMTP
passwords or unsubscribe signatures. No production scheduler or provider send is
enabled automatically.

## Review in the platform

`/weekly-matches` lists saved weekly selections with the same order and evidence
as the email, strategy/offer associations and detailed occurrence feedback.
Recommendations at `/recommendations` remain on demand for a chosen active
strategy and link to that strategy's weekly history. Later generation cannot
replace a saved weekly selection. Previously recorded Matches, notes and status
remain available through the earlier-history link; no strategy provenance is
invented for those records. Weekly Matches do not imply mutual interest or
confirmed buying intent. The current shared retrieval remains a whole-word
service-topic baseline; this change does not add contact-person enrichment.
