# Run Huginn with Docker Compose

Docker Engine with the Compose plugin and Python 3 (for one-time secret generation)
are the only host prerequisites. Node, uv and application dependencies build inside
the image from the committed lockfiles.

## Start

From this checkout's repository root:

```sh
python3 scripts/configure-compose.py
docker compose up -d --build --wait
```

Open <http://localhost:8080> and sign in with the seeded admin credentials described
below. For ordinary accounts, sign up, then open the local inbox at
<http://localhost:8026> and follow the verification link. Mailpit captures mail;
it does not deliver it to external recipients.

The first command creates an ignored, mode-600 `.env` with a random database
password and lifecycle signing/encryption key. It refuses to overwrite an existing
file. Run it only once; reuse the same configuration for later starts. Keep a private
backup of the configuration alongside database backups. Do not rotate the key just
to restart the app: old encrypted mail and signed links depend on it.

Compose starts the built website/API, PostgreSQL 16, local mailbox, lifecycle mail
worker, collection worker and matching worker. The workers process queued requests;
startup does not scrape sources, subscribe users or send weekly
digests. A one-shot `admin-seed` service applies the explicit admin data migration
before the app and workers start. There is no bundled FastEmbed model.

PostgreSQL and captured mail use named volumes. This is a **separate, initially empty
database**, not the existing `huginn-verify-pg` container. It will not contain your
existing accounts, profiles or companies until you deliberately import a backup.
Default ports 8080 and 8026 allow it to coexist with the previous local runtime.
PostgreSQL and SMTP are not published to the host; web ports bind to loopback.

Fresh setup seeds a missing EU-Startups discovery watermark to 365 days ago, so
normal admin collection can start without authorizing an all-history crawl. Existing
watermarks and retries are preserved. On an older Compose volume missing this
state, apply the explicit [watermark migration](../db/schema/README.md#initial-eu-startups-collection-window)
once, then request collection again; the failed run remains in history.

Schema files run in their explicit dependency order only when PostgreSQL initializes
an empty volume. Normal application startup and subsequent restarts apply no schema
migrations; the separate admin data seed is idempotent. The database healthcheck requires the final digest schema as well as TCP
readiness, so dependent processes do not start against an incomplete bootstrap.
For future upgrades, follow [the schema guide](../db/schema/README.md); rebuilding an
image does not upgrade an existing database.

## Inspect, stop and restart

```sh
docker compose ps
docker compose logs --tail=100 app mail-worker
docker compose down
docker compose up -d --wait
```

`down` preserves database and mail volumes. `down --volumes` deletes those volumes;
do not use it for normal shutdown. Docker's restart policy brings existing services
back when Docker restarts. Run `up` again after `down`.

## Administration and data

A default administrator is seeded automatically. Its username defaults to
`huginn-admin`; its randomly generated password is the
`HUGINN_BOOTSTRAP_ADMIN_PASSWORD` value in your private `.env`. These values
are never baked into the image or printed in startup logs. Log in directly with
that credential; no signup or email verification is needed for this owner-provisioned
account. It has all existing administrator permissions, including collection and
matchmaking controls. Ordinary ownership rules for personal workspace data remain
in force.

For a `.env` created before admin seeding was added, run once:

```sh
python3 scripts/configure-compose.py --add-admin
```

This adds missing admin credentials while preserving the database password and
lifecycle key. It refuses partially configured admin settings rather than replacing
them.
The SQL data migration is `db/schema/operational-bootstrap-admin.sql`. The trusted
runner hashes the configured password using the application's scrypt implementation
and supplies the identity through a transaction-local PostgreSQL setting. All four
identity rows are inserted atomically. Existing admins retain passwords, disabled
state, recovery settings and profile edits. An ordinary account with the same
case-insensitive username blocks the seed; it is never silently promoted. Choose a
different bootstrap username or explicitly promote an owned account. A conflicting
email rolls back the whole seed. No account is enrolled in weekly mail.

On an existing compatible database, running the migration requires no direct SQL:

```sh
docker compose run --rm admin-seed
```

Normal `up` runs this service as a startup dependency. Existing schema upgrades
remain explicit; this command is a data seed, not a schema bootstrap. Changing the
environment password later does not reset the stored admin password. Use the normal
account password change flow or the documented owner reset CLI.

You can still create accounts through signup or provisioning and promote one with:

```sh
docker compose exec app \
  python -m huginn.management.admin account assign-role \
  --username YOUR_USERNAME --role admin --confirm
```

Use the admin collection screen to populate the initially empty corpus. Configure
any required source keys in `.env` before collection. Data collection and
matching workers use the same Compose database as the API.

Before importing an existing database, stop all four application/worker services,
back up the source, and follow the schema-owner restore process. Restore the
original lifecycle key with that database, then apply only required additive
upgrades. This Compose setup neither mounts nor modifies the prior local database.

A backup of this Compose database can be written privately on the host:

```sh
umask 077
docker compose exec -T db \
  pg_dump -U huginn -d huginn --format=custom > huginn-backup.dump
```

Keep database dumps outside the checkout or in ignored private local storage.

## External SMTP and weekly delivery

Edit `.env` to configure your provider's host, port, TLS, username, SMTP key
and verified sender. These are the existing `HUGINN_SMTP_*` settings from
[weekly digest setup](weekly-digest.md). For DigitalOcean with Brevo, test port 2525
with `starttls`; DigitalOcean restricts the usual SMTP ports. Run `up -d` after editing
configuration so Compose recreates affected services. `restart` alone does not load
new environment values. The unused local inbox can remain running.

Opt in only consenting users, using their ID:

```sh
docker compose exec app \
  python -m huginn.management.weekly_digest subscribe --user-id USER_UUID
docker compose run --rm weekly-digest send --dry-run
```

The `weekly-digest` service is a manual job behind the `jobs` profile. It does not
run during ordinary startup. A dry run checks subscriptions and sends no email.
Schedule `docker compose run --rm weekly-digest send` once
weekly using the host scheduler after configuring and testing SMTP. Refresh source
data first. All job containers reuse the same image, environment and database.

## Hosting

This default is local development. For a hosted pilot, put an HTTPS reverse proxy
in front of the loopback app port and set `HUGINN_WEB_ORIGIN` to the public HTTPS
origin, `HUGINN_MANAGEMENT_ENVIRONMENT=production`, and TLS-enabled external SMTP.
Production cookies are secure automatically. Keep PostgreSQL and the mailbox
private; use normal schema-owner/runtime-role permissions for a production database.
The bundled database user owns its database for local setup. Configure backups and
the host firewall before accepting pilot users.

## First EU-Startups collection

Fresh database bootstrap initializes an absent EU-Startups watermark to 365 days
ago, matching the recommendation window. Existing checkpoints and retry rows are
preserved. For an older Compose volume with no checkpoint, apply once:

```sh
docker compose exec -T db psql -U huginn -d huginn -v ON_ERROR_STOP=1 \
  -f /schema/bronze-eu-startups-initial-watermark.sql
```

Then request collection again from the admin screen. This does not start collection
or restart services. The previous failure remains in history. Listings modified
before the seeded boundary are outside initial discovery; this is a date filter,
not a guarantee of a small request count. See the [schema guide](../db/schema/README.md#initial-eu-startups-collection-window).
