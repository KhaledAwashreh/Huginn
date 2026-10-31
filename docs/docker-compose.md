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

## Pull a published image on EC2

On each push to `master`, CI publishes the Linux amd64 application image to GHCR
only after lint, Python tests, frontend checks and browser tests succeed. Pull
requests run the checks without publishing. Publishing uses GitHub's built-in
`GITHUB_TOKEN` with package-write permission; no publishing credential is added to
repository secrets. The image name is lowercase and its tag is the full commit
SHA, for example `ghcr.io/khaledawashreh/huginn:FULL_COMMIT_SHA`. There is no moving
`latest` tag. The publish job summary gives the commit, tag and digest reference.
This builds on GitHub's runner, not on the small EC2 instance. It does not connect
to or deploy anything on EC2 automatically.

GHCR packages are private by default on first publication. For a private package,
create a GitHub personal access token (classic) with only `read:packages`, from an
account allowed to read that package. On EC2, log in using the same `sudo` Docker
context used for pulls. Read the token interactively so it does not enter shell
history:

```sh
read -s -p "GHCR token: " GHCR_TOKEN
printf '\n'
printf '%s' "$GHCR_TOKEN" | sudo docker login ghcr.io \
  --username KhaledAwashreh --password-stdin
unset GHCR_TOKEN
```

If you deliberately make the package public in GitHub package settings, anonymous
pulls work and this login is unnecessary. GitHub CLI and AWS credentials are not
needed on EC2. See [GHCR authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

After the publish job succeeds, copy its full commit SHA and image reference.
For first setup, clone this public repository and check out that same commit:

```sh
git clone https://github.com/KhaledAwashreh/Huginn.git
cd Huginn
git checkout FULL_COMMIT_SHA
python3 scripts/configure-compose.py
```

Replace `FULL_COMMIT_SHA` with the published commit. In the generated private
`.env`, replace the `HUGINN_IMAGE` line with the exact image tag or digest copied
from the job summary:

```dotenv
HUGINN_IMAGE=ghcr.io/khaledawashreh/huginn:FULL_COMMIT_SHA
```

Then pull and start without building:

```sh
sudo docker compose pull
sudo docker compose up -d --no-build --wait
sudo docker compose ps
curl -f http://127.0.0.1:8080/ready
```

`HUGINN_IMAGE` selects the same image for the API, admin seed, workers and manual
weekly job. PostgreSQL and Mailpit keep their separately pinned images. Omitting
this setting retains `huginn-app:local` for local builds. The application remains
bound to localhost; configure [hosting](#hosting) for public HTTPS separately.

For later releases, keep `.env` and the named data volumes. Fetch the repository,
check out the published commit, and change only the image reference and settings
the release requires. The matching checkout supplies the schema and bootstrap
files mounted by Compose. Apply any required upgrades explicitly using the
[schema guide](../db/schema/README.md) before starting the new version; pulling an
image does not migrate an existing database. Run `--add-admin` only if upgrading
an older configuration missing founder settings. Do not rerun secret generation
or use `down --volumes` as an upgrade step.

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

Two founder administrators are seeded automatically on a fresh deployment:

| Username | Private password setting | Placeholder email |
| --- | --- | --- |
| `Khaled` | `HUGINN_BOOTSTRAP_ADMIN_PASSWORD` | `khaled@huginn.local` |
| `Craig` | `HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD` | `craig@huginn.local` |

Usernames are case-insensitive: `khaled` and `KHALED` identify the same account.
Each password is generated independently in your private `.env`, never baked into
the image or printed in startup logs. Both use the existing `admin` role, with all
administrator permissions including collection and matchmaking. Founder labels
are profile information, not a new authorization role. Ordinary ownership rules
for personal workspace data still apply.

Log in directly with the configured credentials; signup/email verification is not
required for these owner-provisioned identities. Replace placeholder emails and
personal details before using account recovery. Initial profiles use the username
as first name, `Founder` as a placeholder last name and `Huginn co-founder` as the
headline. The seed does not claim the configured email has been verified.

For an older `.env` with no admins or only a primary admin, run once:

```sh
python3 scripts/configure-compose.py --add-admin
```

This adds missing complete admin settings while preserving the database password,
lifecycle key and any existing primary administrator settings. An old
`huginn-admin` or custom primary username is preserved, not renamed or deleted;
only fresh configuration defaults to `Khaled`. Set the primary username explicitly
before its first seed if deploying an older configuration to a new database.
Partial or empty primary/secondary configuration fails without modifying the file.
Rerunning after both sets exist leaves their settings unchanged.

The SQL data migration is `db/schema/operational-bootstrap-admin.sql`. The trusted
runner validates both configured identities before connecting and hashes both
passwords with scrypt. It applies the migration for both in one transaction, so a
collision on the second founder rolls back the first new identity. Existing admins
retain passwords, disabled state, recovery settings and profile edits. An ordinary
account with the same case-insensitive username blocks the seed; it is never
silently promoted. Choose a different bootstrap username or explicitly promote an
owned account. No account is enrolled in weekly mail.

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
