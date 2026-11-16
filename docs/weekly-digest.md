# Weekly recommendation email

The weekly digest sends plain-text email through Huginn's existing SMTP
configuration. It selects up to seven distinct companies from the Business's
shared recommendations and active strategies. Each email link opens the exact
recommendation and assessment revision included in that message. Reading a link
does not generate new research or change recommendation state.

Before enabling this flow in a deployment, follow the
[recommendation and prospect cutover guide](recommendation-prospect-cutover.md).
That guide owns schema ordering and cutover checks. This page describes current
source behavior; it does not mean a deployment has been upgraded or a scheduler
has been enabled.

## Configuration and consent

The digest uses the existing `HUGINN_SMTP_*` settings and
`HUGINN_WEB_ORIGIN`. Configure a verified sender and production TLS in the
deployment's secret store. The application does not create provider accounts,
credentials, subscriptions, or a scheduler. Provider pricing and sending
quotas vary; check the selected provider's current terms directly.

Weekly subscription is an explicit Business-owned preference. For this pilot,
an operator opts in or out one user at a time with the CLI. Eligibility is
rechecked before delivery: the account must be active, the Business must have
an active valid strategy, and its current verified email must be available.
Editable profile contact details are not used as the recipient. Do not bulk
subscribe users without their consent.

```sh
uv run python -m huginn.management.weekly_digest subscribe --user-id USER_UUID
uv run python -m huginn.management.weekly_digest unsubscribe --user-id USER_UUID
uv run python -m huginn.management.weekly_digest send --dry-run
```

The dry run counts eligible subscriptions. It does not generate recommendations,
reserve a delivery, or contact SMTP. The `send` command accepts `--limit` and
`--daily-limit` (each 1 through 250); defaults are 100. Schedule the command
with the deployment's existing scheduler after source refresh. No schedule is
installed automatically.

## Selection and delivery

Each run uses the same shared recommendation records and assessment revisions
as the in-app Recommendations workspace. A Business can have at most one open
recommendation for a Company; closed records and earlier revisions remain in
history. It selects the strongest seven
distinct companies across active strategies, without adding scores across
strategies or imposing a per-offering quota. It does not weaken filters to fill
the email. No eligible recommendations means no empty email. Sending does not
fetch upstream sources.

The default Business repeat interval is 30 days. A successful first in-app
presentation or SMTP handoff starts the shared cooldown. An active Later pause
blocks that Business and Company across in-app and weekly presentation. Later
weekly selection also respects the cooldown, including when the recommendation
is still open. A
successful repeat uses the cadence captured for that delivery. A later eligible
assessment can be presented when its cooldown and other active blocks allow it.

The digest freezes its recipient and message content before SMTP handoff. Each
company entry links to `/recommendations` with both the recommendation ID and
the exact assessment revision ID. A new assessment cannot change the evidence
in an already prepared message. The weekly scheduler is a delivery channel for
shared recommendations, not a separate Weekly Matches list.

The database reservation prevents duplicate attempts for the same Business
delivery period. SMTP acceptance and database settlement cannot be one atomic
operation. If the connection outcome is uncertain, delivery remains `unknown`;
the system does not resend it automatically. Do not clear a reservation or send
the message again just because it is absent from an inbox. Check provider
records and resolve the actual outcome through the attributed recovery action
below.

## Opt-out

The email's signed opt-out link first opens a confirmation page. Opening or
scanning the link does not unsubscribe. The recipient confirms with a POST;
the token is submitted from the URL fragment rather than sent as an ordinary
URL query. The link is bound to the verified recipient and subscription
version, so changing the address or subscribing again invalidates an older
link. An operator can also unsubscribe a user with the CLI command above.

An opt-out or address change can race with a delivery that has already passed
its final database authorization and entered SMTP transport. In that case the
message may still arrive; the database and SMTP acceptance cannot be atomic.

## Resolve an uncertain delivery

Recovery is an authenticated, CSRF-protected API action. It is scoped to the
authenticated operator's Business and delivery; it does not accept a client
supplied owner ID. Only an `unknown` delivery can be resolved. The action
records the actor, a nonblank reason, the outcome, and the resolution time. It
does not send or retry email.

`sent` means provider evidence confirms acceptance. Supply `accepted_at` using
the actual timezone-aware SMTP acceptance time, not the time of investigation.
`failed` means evidence confirms the handoff did not succeed; omit
`accepted_at`. Do not guess an outcome or timestamp. If the outcome cannot be
established, leave the delivery unknown and investigate further.

```http
POST /api/v1/weekly-digests/{delivery_id}/recovery
X-CSRF-Token: <session csrf token>
Content-Type: application/json

{
  "reason": "<brief explanation with provider evidence reference>",
  "outcome": "sent",
  "accepted_at": "<actual timezone-aware SMTP acceptance timestamp>"
}
```

For a confirmed `failed` outcome, send `"outcome": "failed"` and leave out
`accepted_at`. The endpoint returns a conflict if the delivery is no longer
awaiting recovery. Repeating the same recorded resolution is idempotent; a
different resolution cannot overwrite it. Recovery settles the delivery and
its offer-cycle history together. A confirmed send records the actual
presentation time and starts the applicable cooldown; it does not trigger a
second SMTP handoff.

## Operational boundaries

The CLI prints safe outcome counts and exits nonzero when preparation or
delivery is failed or uncertain. Avoid logging recipients, frozen message
bodies, SMTP credentials, or unsubscribe tokens. Follow the cutover guide for
schema deployment, cleanup, and rollback procedures rather than applying DDL
from this page.
