# Management foundation

KAN-71 establishes a synchronous management application boundary and a fresh
operational bootstrap. It does not implement provisioning, authentication, or
business CRUD. The management boundary is independent of ELT execution while
sharing the production Postgres data model.

## Authority and status

1. The persisted domain authority is
   [`architecture-notes/account-user-and-client-discovery-domain.md`](../architecture-notes/account-user-and-client-discovery-domain.md).
2. The executable plan is
   [`docs/superpowers/plans/2026-09-17-kan-71-management-foundation.md`](superpowers/plans/2026-09-17-kan-71-management-foundation.md).
3. [ADR-0011](../adr/0011-management-api-foundation.md) records the selected
   Flask, Pydantic, identity, and storage representations.
4. The original planning session also cited
   `architecture-notes/management-mvp-codex-session-log-2026-09-17.md` as
   historical context. That file is not present in this branch and is not a
   build dependency.
5. Jira OAuth was unavailable during implementation. The ticket links below
   identify ownership and sequencing; they do not claim that live Jira content
   or status was checked.

## Runtime contract

The selected runtime is synchronous Flask 3 with Pydantic 2 boundaries,
psycopg 3, and Postgres 16. KAN-71 adds no ORM, asynchronous framework,
password-hashing package, session package, or authentication middleware.

1. `ManagementConfig` is a frozen dataclass. It reads only
   `HUGINN_MANAGEMENT_DATABASE_URL`, does not fall back to
   `HUGINN_DATABASE_URL`, and hides the DSN from its representation.
2. `create_app` is inert. It applies no DDL, creates no identity, and opens no
   database connection during construction.
3. `GET /health` returns `200 {"status":"ok"}` without probing Postgres.
4. `GET /ready` opens one read-only psycopg connection per request, with a
   two-second connection timeout and two-second statement timeout. It checks
   `SELECT 1` and the required Account, User, and ProfessionalProfile columns,
   returning `200 {"status":"ready"}` or
   `503 {"status":"not_ready"}`.
5. `/accounts`, `/users`, `/login`, `/sessions`, `/profiles`, `/offerings`,
   `/icps`, and `/strategies` are not implemented and remain 404. KAN-71 sets
   no authentication cookie and exposes no static route.
6. `python -m huginn.management` runs Flask's local development server on
   `127.0.0.1:8000` with debug and the reloader disabled. It is not a
   production WSGI deployment contract.

## Identity and storage

| Entity | Owns | Key relationships |
| --- | --- | --- |
| Account | Username, password hash, status | UUID primary key; username has named uniqueness on `lower(username)` |
| User | Personal and contact data | UUID primary key; unique, required `account_id` foreign key |
| ProfessionalProfile | Professional summary and collections | UUID primary key; unique, required `user_id` foreign key |

Account status is `active` or `disabled` and defaults to `active`. Usernames
must be nonblank and have no leading or trailing whitespace; storage preserves
their spelling, and PostgreSQL's `lower(username)` index supplies
case-insensitive uniqueness under the database collation. The database does
not normalize usernames or promise Unicode casefold equivalence. Password
hashes must be nonblank, but the database imposes no algorithm-specific format.

First name, last name, email, phone number, and country of residence are
required text values that must be nonblank and have no leading or trailing
whitespace. Country is a residence label, not an ISO-code contract. Timezone,
headline, and professional summary are nullable text values that must satisfy
the same constraints when present. Email, phone, country, and timezone
semantic validation is deferred to input-owning tickets. All three entities
use UUID primary keys and timezone-aware `created_at` and `updated_at` values.
Later writers, not a database trigger, maintain `updated_at`.

Foreign keys use the default `NO ACTION` behavior. The unique foreign keys
enforce no orphan child and at most one child, but they cannot require a parent
to have a child. [KAN-72](https://kawashreh.atlassian.net/browse/KAN-72) must
create Account, User, and an empty ProfessionalProfile in one transaction to
enforce the intended exactly-one lifecycle. User is the business ownership
root: `operational.match.user_id` and future domain ownership keys reference
User, never Account.

## Professional collections

`skills`, `experience`, and `previous_projects` are JSONB arrays of objects.
They are never null, default to independent empty arrays, and preserve order
and duplicates. Explicit null collections are rejected. `Skill` contains only
`name`; proficiency, rank, and years fields are rejected.

| Object | Required fields | Optional fields and defaults |
| --- | --- | --- |
| `Skill` | `name` | None |
| `Experience` | `organization`, `role` | `summary = null`, `start_month = null`, `end_month = null`, `is_current = false` |
| `PreviousProject` | `name`, `description` | None |
| `ProfessionalCollections` | None | `skills = []`, `experience = []`, `previous_projects = []` |

The models in `huginn.management.schemas` are strict, frozen, and reject
unknown fields and type coercion. Required strings are stripped and must
remain nonblank. Optional strings may be omitted or null but must remain
nonblank when supplied. Months use `YYYY-MM` from `0001-01` through
`9999-12`; an end month cannot precede a start month, and current experience
cannot have an end month. Unknown dates are allowed.

The SQL boundary checks only that each collection is an outer array containing
objects. Pydantic checks the object fields before persistence and after loading
typed values. Direct SQL can bypass deep validation, so future writers must use
the shared schemas. Frozen Pydantic fields do not make nested lists immutable;
callers treat these models as short-lived boundary values and replace rather
than mutate them. Item IDs, deduplication, normalized child tables, and
migration execution are deferred to [KAN-49](https://kawashreh.atlassian.net/browse/KAN-49).

## Authentication and deferred work

[KAN-72](https://kawashreh.atlassian.net/browse/KAN-72) consumes
`operational.accounts`, `operational.users`,
`operational.professional_profiles`, `ManagementConfig`, and the `Skill`,
`Experience`, `PreviousProject`, and `ProfessionalCollections` schemas. It
owns password hashing, owner-only CLI provisioning, and one transaction that
creates Account, User, and an empty ProfessionalProfile. It must finalize
personal input validation before accepting owner input, use the same
`lower(username)` expression for conflict handling, and prove rollback leaves
no partial identity. It must not assume the database makes either child
mandatory or normalizes usernames.

[KAN-73](https://kawashreh.atlassian.net/browse/KAN-73) owns login verification,
opaque revocable server-side session storage, token transport, expiry,
revocation, CSRF, disabled-account enforcement, and ownership enforcement.
Flask's signed client-side session is not the authentication store.

The bootstrap intentionally contains no session, service-offering, ICP, or
discovery-strategy tables. Service offerings are deferred to
[KAN-75](https://kawashreh.atlassian.net/browse/KAN-75), ICP storage and
multi-value semantics to [KAN-76](https://kawashreh.atlassian.net/browse/KAN-76),
and strategies and their reference rules to
[KAN-77](https://kawashreh.atlassian.net/browse/KAN-77). User/Profile CRUD is
[KAN-74](https://kawashreh.atlassian.net/browse/KAN-74). BuyerPersona and
EngagementPreferences remain separate domain concepts without KAN-71 tables
or workflows. Matching and scoring remain under
[KAN-18](https://kawashreh.atlassian.net/browse/KAN-18).

## Local bootstrap and probes

Use a new, dedicated, disposable management development database. These are
operator-run examples, not application startup behavior and not permission to
delete a database. If `huginn_management` already contains an old schema,
choose a new dedicated name or request an explicitly scoped rebuild. Do not
run `dropdb` or reset existing data as part of this runbook.

Run from the worktree:

```bash
rtk proxy createdb huginn_management
export HUGINN_MANAGEMENT_DATABASE_URL='postgresql://localhost:5432/huginn_management'
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
rtk uv run --python 3.14 python -m huginn.management
```

`export` is a shell builtin, so it is not wrapped with `rtk`. The six-file
bootstrap is required because retained operational tables reference Gold.

With the local development server running, use a separate terminal:

```bash
rtk proxy curl --fail-with-body http://127.0.0.1:8000/health
rtk proxy curl --fail-with-body http://127.0.0.1:8000/ready
```

If port 8000 is occupied, run the local development server on 8001:

```bash
rtk uv run --python 3.14 flask --app huginn.management.app:create_app run --host 127.0.0.1 --port 8001 --no-debugger --no-reload
```

Only run a manual server smoke test against an explicitly selected dedicated
database. Automated Flask test-client tests and live Postgres 16 container
tests are the portable required evidence.
