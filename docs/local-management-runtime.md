# Local management runtime

Open <http://127.0.0.1:4173/> to use configuration, Matches and admin screens against the
existing Huginn PostgreSQL database. Create your own account through signup,
then open <http://127.0.0.1:8025/> and copy the verification link into your
browser. Account passwords are chosen by you. Separate preview accounts were
later provisioned without changing the existing user.

Lifecycle email is captured locally, never delivered to an external mailbox.
Captured messages persist privately under `.local-runtime/mail/`. The account
configuration UI manages your profile, service offerings, ideal client profiles,
and discovery strategies. Matches shows only your own recorded matches with
current company and signal context. Administrators additionally see Data
collection and Matchmaking controls, which trigger the existing services.

## Start, inspect, and stop

Run these commands from
`/home/kawashreh/Projects/Huginn/.worktrees/user-configuration-workspace`:

```sh
rtk proxy .venv/bin/python .local-runtime/manage.py start
rtk proxy .venv/bin/python .local-runtime/manage.py status
rtk proxy .venv/bin/python .local-runtime/manage.py stop
```

`start` starts the existing `huginn-verify-pg` container if it is stopped, then
starts six detached local processes using the integrated source at
`../admin-discovery-workspace`. The manager, saved environment, mail and backups
remain in `user-configuration-workspace/.local-runtime`. It never applies migrations. Processes
continue after the launching terminal or assistant session ends. After a host
reboot, run `start` again. This is local development hosting, without automatic
boot services.

`stop` checks recorded process identities before stopping only this runtime's
API, UI, mailbox, lifecycle mail worker, collection worker and matching worker.
It leaves PostgreSQL running. Occupied ports
cause startup to fail without stopping another process.

1. UI: <http://127.0.0.1:4173/>.
2. API: <http://127.0.0.1:8000/health>, with database readiness at `/ready`.
3. Local mailbox: <http://127.0.0.1:8025/>, SMTP capture on loopback port 1025.
4. Lifecycle worker: dispatches the durable local mail outbox once per second.
5. Collection worker: executes administrator-enqueued pipeline invocations.
6. Matching worker: executes administrator-enqueued user matching runs.

Logs are `.local-runtime/api.log`, `ui.log`, `mailbox.log`, `worker.log`,
`pipeline-worker.log` and `matching-worker.log`.
PID records are `.local-runtime/*.pid.json`. The entire runtime directory,
captured mail, and backups are ignored by Git. The persistent `.env` is ignored
and mode 600. Keep its lifecycle encryption key unchanged across restarts so
pending encrypted mail remains readable.

The runtime reuses the already installed Python environment and frontend
dependencies from the `web-ui-foundation` worktree through ignored symlinks.
Node is the installed version 24 executable copied into `.local-runtime/bin/node`.
These local dependency locations must remain available for subsequent starts.

## Database upgrade performed

On 2026-10-08, the existing account, user, and professional profile tables were
inspected and found compatible. The upgrade explicitly applied
`db/schema/operational-management-configuration.sql`, followed by
`db/schema/operational-account-lifecycle.sql`. The first migration creates the
four missing session and configuration tables; the second creates lifecycle
storage and its required indexes. Do not run the non-idempotent
`db/schema/operational.sql` bootstrap over this database, or reapply the
configuration upgrade after its tables exist.

A complete custom-format backup was taken before either migration at
`.local-runtime/backups/huginn-before-management-20261008T193600Z.dump`.
Its restore catalogue was verified. All 26 existing table counts remained
unchanged, including 3,764 rows in `gold.company`. No account credentials were
created or reset, and no ELT, matching, or workflow rows were changed.

The API's management database URL points to the existing PostgreSQL database
configured in the primary checkout. This is persistent application data.
Startup and shutdown never reset, seed, or clear that database.

## Admin and Matches deployment

On 2026-10-09 a complete backup was taken before additive upgrades:
`.local-runtime/backups/before-admin-matches-20261009T133432Z.dump`
(13,572,146 bytes; restore catalogue verified). All 34 existing table counts
were unchanged after applying `operational-account-role.sql`,
`ops-pipeline-control.sql` and `ops-matchmaking-control.sql`. The existing
matcher prerequisites `operational-match-user-company-unique.sql` and
`gold-company-signal-matchmaking-index.sql` were applied explicitly too.
No base bootstrap or database reset was performed.

Management, collection and matching use the same existing database. The manager
loads the saved environment explicitly and supplies
`HUGINN_MATCHMAKING_DATABASE_URL` from the management DSN; it refuses mismatched
collection and management DSNs. The lifecycle encryption key is preserved.

Trusted provisioning created separate `huginn-admin` and `huginn-demo`
accounts. Only the new admin received the admin role. Credentials are private in
`.local-runtime/test-credentials.json`, excluded from Git. The demo has a
small-US-B2B ICP and an active strategy against collected company values.
The existing account, password and discovery configuration were preserved.
