# Management foundation

KAN-71 established the synchronous management application boundary and fresh
operational bootstrap. KAN-72 through KAN-78 add provisioning,
authentication, and owner-scoped business CRUD on that foundation. The
management boundary is independent of ELT execution while sharing the
production Postgres data model.

## Authority and status

1. The persisted domain authority is
   [`architecture-notes/account-user-and-client-discovery-domain.md`](../architecture-notes/account-user-and-client-discovery-domain.md).
2. The executable plan is
   [`docs/superpowers/plans/2026-09-17-kan-71-management-foundation.md`](superpowers/plans/2026-09-17-kan-71-management-foundation.md).
3. [ADR-0015](../adr/0015-management-fastapi-runtime.md) records the selected
   FastAPI/Uvicorn runtime and synchronous psycopg execution model.
   [ADR-0011](../adr/0011-management-api-foundation.md) remains as the history
   of the superseded Flask decision and the identity and storage choices.
4. The original planning session also cited
   `architecture-notes/management-mvp-codex-session-log-2026-09-17.md` as
   historical context. That file is not present in this branch and is not a
   build dependency.
5. Jira OAuth was unavailable during implementation. The ticket links below
   identify ownership and sequencing; they do not claim that live Jira content
   or status was checked.

## Runtime contract

The selected runtime is FastAPI with Uvicorn, Pydantic 2 boundaries,
synchronous psycopg 3, and Postgres 16. Database-backed handlers and
dependencies use normal `def` functions, which FastAPI runs in its worker
thread pool so psycopg calls do not block the ASGI event loop. Production
worker count, thread capacity, and database connection capacity must be
configured together. The login throttle is process-local, so the runtime must
remain single-process until throttle state is shared. Werkzeug is an explicit
runtime dependency because password code imports its scrypt helpers directly.
The application adds no ORM or automatic migrations.

1. `ManagementConfig` is a frozen dataclass. It reads only
   `HUGINN_MANAGEMENT_DATABASE_URL`, does not fall back to
   `HUGINN_DATABASE_URL`, and hides the DSN from its representation.
2. `create_app` is inert. It applies no DDL, creates no identity, and opens no
   database connection during construction.
3. `GET /health` returns `200 {"status":"ok"}` without probing Postgres.
4. `GET /ready` opens one read-only psycopg connection per request, with a
   two-second connection timeout and two-second statement timeout. It checks
   `SELECT 1` and the required columns for accounts, users, professional
   profiles, sessions, service offerings, ideal client profiles, and client
   discovery strategies, returning `200 {"status":"ready"}` or
   `503 {"status":"not_ready"}`.
5. `/api/v1` implements session login and logout, password changes,
   self-service User and ProfessionalProfile access, and owner-scoped CRUD for
   service offerings, ideal client profiles, and discovery strategies. Login
   sets an opaque `HttpOnly` session cookie; authenticated unsafe requests also
   require the session-bound `X-CSRF-Token` header. Logout and password changes
   clear the cookie.
6. `python -m huginn.management` runs Uvicorn on `127.0.0.1:8000` without
   debug mode or reload. It is a local development command, not a production
   deployment configuration.
7. FastAPI generates `/openapi.json`, `/docs`, and `/redoc` from the declared
   routes, request and response models, and security dependencies.
8. Invalid body, path, query, and header values use HTTP 422 with a sanitized
   `detail` array. Submitted values and validation context are removed to
   protect credentials.

## Management package layers

`huginn.management.app` is the composition root. It chooses concrete database,
repository, and security adapters and supplies application services to the HTTP
and owner CLI presentation layers. Construction opens no database connection.
The documented `python -m huginn.management.admin` command remains a thin
launcher; its input, output, and secret handling live in `presentation/cli`.

```text
huginn/management/
├── app.py, config.py, __main__.py, admin.py
├── presentation/
│   ├── api/{routers,dependencies,requests,responses,errors,openapi,constants}/
│   │   ├── primitives.py
│   │   └── mapping.py
│   └── cli/account_admin.py
├── application/
│   ├── services/
│   ├── commands/
│   ├── errors/
│   ├── throttling/
│   └── authentication_policy.py
├── domain/{entities,value_objects,services,errors}/
├── persistence/
│   ├── contracts/{repositories,database.py,unit_of_work.py,postgresql.py}
│   ├── repositories/
│   ├── row_models/
│   ├── errors/
│   └── database/{client.py,unit_of_work.py,policy.py}
└── security/{passwords.py,tokens.py,password_policy.py,token_policy.py}
```

Presentation depends on application services and domain values. Application
services depend on persistence contracts, domain values, and credential helpers.
Domain imports only the standard library and other domain modules. Persistence
owns both resource-specific repository contracts and SQL implementations, plus
row validation, sessions, and transaction contracts; it is a first-class layer.
Security imports neither presentation nor persistence. Import-graph tests
enforce these boundaries, and package initializers do not re-export their APIs.

Only `persistence/database/client.py` imports psycopg. It adapts connections,
cursors, JSONB parameters, and driver failures to persistence-owned contracts
and safe structured SQLSTATE metadata. Repositories execute and map rows;
application use cases control commit and rollback through a unit of work.
PostgreSQL remains the selected database engine. Handwritten PostgreSQL SQL,
JSONB, constraints, and row locks stay in the repositories. The client boundary
allows replacing the Python driver; it does not promise another SQL dialect.
Internal imports use the layered paths directly, with no legacy aliases.

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

The directional models in
`huginn.management.presentation.api.requests.professional_profile` and
`huginn.management.presentation.api.responses.professional_profile` are strict
and frozen.
Request models reject unknown fields and unwanted type coercion. Required
strings are stripped and must remain nonblank. Optional strings may be omitted
or null but must remain nonblank when supplied. Months use `YYYY-MM` from
`0001-01` through `9999-12`; an end month cannot precede a start month, and
current experience cannot have an end month. Unknown dates are allowed.

The SQL boundary checks only that each collection is an outer array containing
objects. Request models validate values before a use case, and private
PostgreSQL row models validate persisted JSONB after loading. Direct SQL can
bypass deep validation, so writers must use the application services and
repositories. Frozen Pydantic fields do not make nested lists immutable;
callers treat request values as short-lived boundaries and replace rather than
mutate them. Item IDs, deduplication, normalized child tables, and migration
execution are deferred to [KAN-49](https://kawashreh.atlassian.net/browse/KAN-49).

## Authentication and ownership

[KAN-72](https://kawashreh.atlassian.net/browse/KAN-72) consumes
`operational.accounts`, `operational.users`,
`operational.professional_profiles`, `ManagementConfig`, professional-profile
request values, and PostgreSQL row validation. It
owns password hashing, owner-only CLI provisioning, and one transaction that
creates Account, User, and an empty ProfessionalProfile. It validates personal
input before accepting owner input, uses the same
`lower(username)` expression for conflict handling, and proves rollback leaves
no partial identity. It must not assume the database makes either child
mandatory or normalizes usernames.

[KAN-73](https://kawashreh.atlassian.net/browse/KAN-73) owns login verification,
opaque revocable server-side session storage, token transport, expiry,
revocation, CSRF, disabled-account enforcement, and ownership enforcement.
The session cookie contains only an opaque token; PostgreSQL holds its digest.

The operational schema now contains sessions, service offerings, ICPs, and
discovery strategies. Service offerings are owned by
[KAN-75](https://kawashreh.atlassian.net/browse/KAN-75), ICP storage and
multi-value semantics by [KAN-76](https://kawashreh.atlassian.net/browse/KAN-76),
strategies and their reference rules by
[KAN-77](https://kawashreh.atlassian.net/browse/KAN-77), and User/Profile CRUD
by [KAN-74](https://kawashreh.atlassian.net/browse/KAN-74). BuyerPersona and
EngagementPreferences remain separate domain concepts. Matching and scoring
remain under
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
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql -f db/schema/operational-account-role.sql -f db/schema/ops-pipeline-control.sql -f db/schema/ops-matchmaking-control.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/operational-account-role.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/ops-pipeline-control.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/ops-matchmaking-control.sql
rtk uv run --python 3.14 python -m huginn.management
```

`export` is a shell builtin, so it is not wrapped with `rtk`. Apply the seven
base files first because retained operational tables reference Gold, then run
the role and pipeline-control additive migrations in order. These migrations
are operator-applied and never run during application startup.

With the local development server running, use a separate terminal. The API
reference is available at `/docs`, `/redoc`, and `/openapi.json`:

```bash
rtk proxy curl --fail-with-body http://127.0.0.1:8000/health
rtk proxy curl --fail-with-body http://127.0.0.1:8000/ready
rtk proxy curl --fail-with-body http://127.0.0.1:8000/docs
rtk proxy curl --fail-with-body http://127.0.0.1:8000/redoc
```

If port 8000 is occupied, run the local development server on 8001:

```bash
rtk uv run --python 3.14 uvicorn huginn.management.app:create_app --factory --host 127.0.0.1 --port 8001 --no-reload
```

Only run a manual server smoke test against an explicitly selected dedicated
database. Automated FastAPI `TestClient` tests and live Postgres 16 container
tests are the portable required evidence.

## Management CRUD local runbook

This procedure exercises KAN-72 through KAN-78 with the unique database name
`huginn_management_crud_local_kan78`. If that name exists, stop and select
another unused name. Never adapt these commands to an existing or shared
database.

Create and bootstrap the disposable database from the repository root:

```bash
rtk proxy createdb huginn_management_crud_local_kan78
export HUGINN_MANAGEMENT_DATABASE_URL='postgresql://localhost:5432/huginn_management_crud_local_kan78'
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql -f db/schema/operational-account-role.sql -f db/schema/ops-pipeline-control.sql -f db/schema/ops-matchmaking-control.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/operational-account-role.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/ops-pipeline-control.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/ops-matchmaking-control.sql
```

Provision the owner. The command prompts twice with terminal echo disabled, so
the raw password is neither a command-line argument nor shell history:

```bash
rtk uv run --python 3.14 python -m huginn.management.admin account provision --username owner --first-name Local --last-name Owner --email owner@example.test --phone-number +970599000000 --country-of-residence Palestine --timezone Asia/Hebron
```

For non-interactive automation, add `--password-stdin` and redirect a protected
file containing the password twice on separate lines. Do not place the password
in an argument, environment variable, example file, or log.

Start the development server. Startup opens no database connection and applies
no DDL:

```bash
rtk uv run --python 3.14 python -m huginn.management
```

In a second terminal, export the same database URL, then create private local
files for the response and cookie jar. The producer reads the password through
`getpass`, so neither credential is embedded in the command:

```bash
umask 077
rtk uv run --python 3.14 python -c 'import getpass,json,sys; print("Username: ", end="", file=sys.stderr, flush=True); username=input(); print(json.dumps({"username": username, "password": getpass.getpass()}))' | rtk proxy curl --fail-with-body --silent --show-error --request POST --header 'Content-Type: application/json' --data-binary @- --cookie-jar /tmp/huginn-kan78-cookies.txt --output /tmp/huginn-kan78-login.json http://127.0.0.1:8000/api/v1/sessions
export HUGINN_CSRF_TOKEN="$(rtk uv run --python 3.14 python -c 'import json; print(json.load(open("/tmp/huginn-kan78-login.json"))["csrf_token"])')"
rtk proxy curl --fail-with-body --cookie /tmp/huginn-kan78-cookies.txt http://127.0.0.1:8000/api/v1/me
```

The cookie authenticates every API request. Every unsafe request also requires
the session-bound `X-CSRF-Token` header. These commands exercise self-service
and the offering, ICP, and strategy CRUD chain:

```bash
rtk proxy curl --fail-with-body --request PATCH --cookie /tmp/huginn-kan78-cookies.txt --header "X-CSRF-Token: $HUGINN_CSRF_TOKEN" --header 'Content-Type: application/json' --data '{"headline":"Local operator","skills":[{"name":"Python"}]}' http://127.0.0.1:8000/api/v1/me/professional-profile
rtk proxy curl --fail-with-body --silent --show-error --request POST --cookie /tmp/huginn-kan78-cookies.txt --header "X-CSRF-Token: $HUGINN_CSRF_TOKEN" --header 'Content-Type: application/json' --data '{"name":"Local service","description":"Disposable runbook service"}' --output /tmp/huginn-kan78-offering.json http://127.0.0.1:8000/api/v1/offerings
export HUGINN_OFFERING_ID="$(rtk uv run --python 3.14 python -c 'import json; print(json.load(open("/tmp/huginn-kan78-offering.json"))["id"])')"
rtk proxy curl --fail-with-body --silent --show-error --request POST --cookie /tmp/huginn-kan78-cookies.txt --header "X-CSRF-Token: $HUGINN_CSRF_TOKEN" --header 'Content-Type: application/json' --data '{"name":"Local ICP","industries":[{"name":"Software"}],"company_sizes":[{"band":"11-100"}],"geographies":[{"kind":"country","value":"Palestine"}],"exclusions":[]}' --output /tmp/huginn-kan78-icp.json http://127.0.0.1:8000/api/v1/ideal-client-profiles
export HUGINN_ICP_ID="$(rtk uv run --python 3.14 python -c 'import json; print(json.load(open("/tmp/huginn-kan78-icp.json"))["id"])')"
rtk proxy curl --fail-with-body --request POST --cookie /tmp/huginn-kan78-cookies.txt --header "X-CSRF-Token: $HUGINN_CSRF_TOKEN" --header 'Content-Type: application/json' --data "{\"name\":\"Local strategy\",\"service_offering_id\":\"$HUGINN_OFFERING_ID\",\"ideal_client_profile_id\":\"$HUGINN_ICP_ID\",\"is_active\":true}" http://127.0.0.1:8000/api/v1/discovery-strategies
rtk proxy curl --fail-with-body --cookie /tmp/huginn-kan78-cookies.txt 'http://127.0.0.1:8000/api/v1/discovery-strategies?active=true&limit=50&offset=0'
rtk proxy curl --fail-with-body http://127.0.0.1:8000/openapi.json
```

Run the required verification from the repository root:

```bash
rtk uv run --python 3.14 python -m compileall -q src tests
rtk uv run --python 3.14 ruff check .
rtk uv run --python 3.14 ruff format --check .
rtk uv run --python 3.14 pytest -q tests/management
rtk uv run --python 3.14 pytest -q
rtk openspec validate management-api-crud --strict
```

For teardown, revoke the current session while the server is running, then stop
the server, remove the named local artifacts, and clear shell values:

```bash
rtk proxy curl --fail-with-body --request DELETE --cookie /tmp/huginn-kan78-cookies.txt --header "X-CSRF-Token: $HUGINN_CSRF_TOKEN" http://127.0.0.1:8000/api/v1/sessions/current
rtk rm -f /tmp/huginn-kan78-cookies.txt /tmp/huginn-kan78-login.json /tmp/huginn-kan78-offering.json /tmp/huginn-kan78-icp.json
unset HUGINN_CSRF_TOKEN HUGINN_OFFERING_ID HUGINN_ICP_ID HUGINN_MANAGEMENT_DATABASE_URL
```

Only after confirming `huginn_management_crud_local_kan78` is the dedicated
disposable database created above, remove it by its explicit name:

```bash
rtk proxy dropdb huginn_management_crud_local_kan78
```
