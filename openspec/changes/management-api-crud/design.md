# Management API CRUD design

## Context

Huginn already has an inert synchronous Flask application factory, strict
Pydantic 2 professional-collection models, direct psycopg 3 access, and a
fresh-bootstrap `operational` schema for Account, User, and
ProfessionalProfile. It deliberately has no ORM, authentication middleware,
session table, generic CRUD framework, or migration runner. This change must
extend those boundaries without coupling management requests to ELT jobs or
letting HTTP concerns leak into persistence.

The delivery spans Jira KAN-72 through KAN-78. User is the ownership root;
Account owns credentials and status; ProfessionalProfile is a one-to-one
child. Offerings, ICPs, and strategies are reusable User-owned records. The
current Pydantic shapes for skills, experience, and previous projects are the
authority for this change where the older KAN-74 draft differs.

The MVP will normally run as one process against a dedicated development
database. Current development data is disposable, and the repository has no
general migration tooling yet. The design must nevertheless enforce ownership
and referential integrity under direct or concurrent database writes.

## Goals / Non-Goals

### Goals

- Implement the complete synchronous path from HTTP and owner CLI boundaries
  through application services and repositories to PostgreSQL.
- Create and maintain the Account/User/ProfessionalProfile aggregate
  atomically.
- Provide minimal password login, opaque revocable sessions, CSRF protection,
  and server-resolved User ownership.
- Provide self-service User/Profile APIs and owner-scoped CRUD for offerings,
  ICPs, and discovery strategies.
- Preserve the confirmed broad ICP semantics and make an incomplete positive
  filter return no results before candidate SQL runs.
- Supply deterministic errors, pagination, automated tests, OpenAPI
  documentation, and a reproducible local verification runbook.

### Non-Goals

- Public registration, OAuth, MFA, roles, refresh tokens, password recovery,
  device/session management UI, or browser UI.
- BuyerPersona, EngagementPreferences, matching execution, ranking,
  preference weighting, or per-strategy Match identity.
- An ORM, generic repository framework, asynchronous API stack, or generalized
  migration system.
- Correlated ICP segments or persisted Cartesian targeting combinations.
- Legacy-data backfill or automatic schema mutation at application startup.

## Decisions

### 1. Keep explicit layers and make the application service the transaction boundary

The management package will be organized around these dependency directions:

```text
Flask blueprints and CLI
        |
Pydantic request/response models and error mapping
        |
application services / use cases
        |
domain values, results, errors, and repository ports
        |
psycopg repositories plus a management unit of work
        |
PostgreSQL operational schema
```

`create_app` remains the composition root. It constructs concrete adapters
when overrides are not injected, registers blueprints and error handlers, and
must remain inert with respect to DDL and provisioning. Tests can inject fake
services and clocks/randomness without monkeypatching global state.

Each mutating use case opens one unit of work. Repositories execute SQL on the
unit-of-work connection and never commit independently. The application
service commits only after all validation and writes succeed; exceptions roll
back. Provisioning therefore creates Account, User, and ProfessionalProfile
in exactly one transaction. Read use cases use short-lived read transactions.

The management unit of work may reuse the connection-lifecycle lessons from
`PostgresConnectionScope`, but it remains management-owned rather than
depending on a Silver repository implementation.

Owner operations use a separate module entry point so the existing management
server command remains stable:

```text
python -m huginn.management.admin account provision [identity flags]
python -m huginn.management.admin account enable --username USERNAME
python -m huginn.management.admin account disable --username USERNAME
python -m huginn.management.admin account reset-password --username USERNAME
```

Provision accepts username, first name, last name, email, phone, country, and
optional timezone as named flags. Provision and reset read the password twice
from a non-echoing prompt, or from standard input for controlled automation;
passwords are never accepted as command-line arguments or printed.

Alternative considered: route functions call psycopg repositories directly.
That is smaller initially, but it has no reliable home for atomic aggregate
creation, authorization, or cross-repository strategy validation.

### 2. Use resource-specific ports and SQL instead of generic CRUD abstractions

Ports will describe operations needed by the use cases, such as
`get_account_by_normalized_username`, `get_owned_offering`, and
`list_owned_strategies`. Domain results are typed dataclasses or Pydantic
boundary models, not raw psycopg rows. SQL always includes the authenticated
`user_id` for User-owned reads, updates, and deletes. Cross-owner identifiers
therefore produce the same not-found result as absent identifiers.

Updates will use explicit field sets assembled from validated patch models.
An omitted field is unchanged; explicit null is accepted only for nullable
fields; an explicit collection replaces the entire JSONB collection. Writers
set `updated_at = now()` and return the committed representation. MVP
concurrency is last-write-wins; ETags and optimistic version columns are
deferred.

Alternative considered: one generic repository and route generator. It would
obscure per-resource ownership and reference rules for little benefit across
only four HTTP resource families.

### 3. Extend the fresh bootstrap schema with sessions and User-owned resources

`db/schema/operational.sql` will add:

- `sessions`: UUID primary key, required `account_id`, unique SHA-256
  `token_digest`, SHA-256 `csrf_digest`, `created_at`, `expires_at`, and nullable
  `revoked_at`. Indexes support digest lookup and Account-wide revocation.
- `service_offerings`: UUID, `user_id`, nonblank `name` and `description`, and
  timestamps. `(user_id, id)` is unique for composite references.
- `ideal_client_profiles`: UUID, `user_id`, nonblank `name`, JSONB arrays for
  `industries`, `company_sizes`, `geographies`, and `exclusions`, plus
  timestamps. `(user_id, id)` is unique.
- `client_discovery_strategies`: UUID, `user_id`, nonblank `name`,
  `service_offering_id`, `ideal_client_profile_id`, `is_active` defaulting to
  false, and timestamps.

Strategy references use composite foreign keys
`(user_id, service_offering_id)` and `(user_id, ideal_client_profile_id)` so a
direct SQL write cannot connect records owned by different Users. Foreign
keys use `NO ACTION`; referenced offerings and ICPs are not cascade-deleted.
The service maps those constraint failures to conflict responses.

JSONB database checks guarantee an outer array of objects and constrain the
company-size strings to the Gold bands where practical. Pydantic performs the
complete tagged-item validation before writes and after reads. This matches
the established ProfessionalProfile boundary and avoids premature normalized
criterion tables.

Because KAN-49 migration tooling is deferred, this change updates fresh
bootstrap SQL only. Existing disposable management databases must be rebuilt
explicitly by the operator; application startup never applies DDL. A durable
environment with retained management data must receive a separately reviewed
additive migration before adopting this schema.

### 4. Use small, strict representations for targeting

The request and stored JSON shapes are:

- industry: `{ "name": <nonblank string> }`
- company size: `{ "band": "0-10" | "11-100" | "101-1000" | "1001+" }`
- geography: `{ "kind": "country" | "region", "value": <nonblank string> }`
- company exclusion: `{ "kind": "company", "company_id": <UUID> }`
- industry exclusion: `{ "kind": "industry", "name": <nonblank string> }`
- geography exclusion: `{ "kind": "geography", "geography": <geography> }`

Models are strict, reject extra keys and coercion, trim labels, and preserve
collection order and duplicates. Deduplication and controlled industry or
geography vocabularies are deferred. Company-size bands intentionally reuse
the values enforced by `gold.company.company_scale`, avoiding a second size
taxonomy.

An evaluation/query-builder entry point starts with this guard:

```python
if not icp.industries or not icp.company_sizes or not icp.geographies:
    return []
```

Only a complete positive filter may generate candidate SQL. Within each
positive dimension values use OR, while the three dimensions use AND.
Exclusions are then combined as global vetoes. The system neither creates nor
stores every possible industry/size/geography tuple. CRUD owns this contract
and tests the guard even though full matching remains KAN-18 work.

Alternative considered: an empty list means unrestricted. That conflicts with
the confirmed MVP decision and risks an incompletely configured ICP flooding
results. The KAN-76 wording must be updated to match this specification.

### 5. Use Werkzeug password hashing and database-backed opaque sessions

Passwords are accepted verbatim, must be 12 through 1024 characters, and have
no composition rules. `werkzeug.security.generate_password_hash` and
`check_password_hash` use Werkzeug's supported scrypt encoding, which embeds
a fresh random salt and parameters in every stored hash. No custom hashing,
manual salt field, pepper, reversible encryption, or credential logging is
introduced. Successful login may rehash when the configured method changes.

Login generates a raw session token and raw CSRF token with
`secrets.token_urlsafe(32)`. PostgreSQL stores only SHA-256 digests. The raw
session token is sent in an HttpOnly cookie with `Path=/`, explicit
`SameSite=Lax`, and `Secure=true` outside local development. The raw CSRF value
is returned once in the login response and must be sent as `X-CSRF-Token` for
authenticated POST, PATCH, PUT, and DELETE requests. Digest comparisons use
`hmac.compare_digest` where application comparison is needed.

Session lifetime is configurable and defaults to 12 hours. Every protected
request resolves session, active Account, and User from the database; status
changes therefore take effect without waiting for cookie expiry. Logout
revokes the current session. Password change, owner reset, and Account disable
revoke all Account sessions in the same transaction as the credential/status
change. Expired rows can remain until an explicit cleanup command is added;
they never authenticate.

The login boundary uses an injected fixed-window throttle keyed by client IP
and normalized username, defaulting to five failed attempts in 15 minutes.
The initial in-memory adapter is appropriate only for the documented
single-process MVP and does not reveal which key component matched. A shared
adapter is required before multi-process or multi-instance deployment.

Alternative considered: Flask's signed client-side session. It cannot provide
server-side revocation or safely satisfy password-change and disablement
requirements.

### 6. Resolve ownership in authentication, never request payloads

An authentication decorator loads a request-scoped principal containing only
the Account and User identifiers needed by application services. Resource
routes never accept `user_id` or `account_id` as writable fields. Self-service
routes are fixed at `/api/v1/me` and `/api/v1/me/professional-profile`.

Resource routes are:

- `/api/v1/sessions` and `/api/v1/sessions/current`
- `/api/v1/me`, `/api/v1/me/password`, and
  `/api/v1/me/professional-profile`
- `/api/v1/offerings`
- `/api/v1/ideal-client-profiles`
- `/api/v1/discovery-strategies`

Collection routes support create and list; member routes support get, patch,
and delete. Creation returns 201, reads and updates return 200, and deletion
returns 204. Strategy create/update checks owned references in the application
service for useful errors, while composite foreign keys close the concurrency
gap.

### 7. Standardize validation, errors, and pagination

All JSON bodies pass through strict Pydantic models. Malformed JSON is 400;
schema or semantic validation is 422; missing/invalid authentication is 401;
missing/invalid CSRF is 403; owned-resource absence, including cross-owner
access, is 404; uniqueness and referenced-delete conflicts are 409; and login
throttling is 429. Unexpected failures use a generic 500 response and retain
safe diagnostic context in logs.

Errors use one envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  }
}
```

No error or log field may contain passwords, password hashes, raw/digested
session tokens, or CSRF secrets.

Lists accept `offset >= 0` and `1 <= limit <= 100`, with default limit 50.
They order by `created_at, id` and return
`{ "items": [...], "offset": n, "limit": n, "has_more": bool }`. The
repository requests `limit + 1` rows to compute `has_more` without a separate
count query. Offset pagination is sufficient for the expected MVP volume;
cursor pagination can replace it when scale or concurrent list stability
requires it.

Pydantic models remain the executable schema source. The implementation will
serve a checked, deterministic `/openapi.json` document assembled from the
route declarations and model JSON schemas, plus tests that fail when required
paths or response components disappear. An interactive documentation UI is
not required.

### 8. Verify each layer and the complete two-user workflow

Tests will cover:

- Pydantic value and patch semantics, password hashing, session digests,
  expiry/revocation, CSRF, and the ICP empty-positive guard.
- Application services with fake repositories/unit of work, including atomic
  rollback, ownership, same-User strategy references, and session revocation.
- Psycopg repositories and schema constraints against the existing
  testcontainers PostgreSQL 16 harness.
- Flask test-client contracts for statuses, envelopes, cookies, pagination,
  and cross-User indistinguishability.
- One end-to-end flow that provisions two users, logs both in, updates the
  first profile, creates offering/ICP/strategy data, proves the second user
  cannot access it, exercises referenced-delete conflicts, logs out, and
  verifies revoked-session rejection.

The full gate is Python 3.14 compile, Ruff, the complete pytest suite, live
Postgres integration tests, OpenSpec strict validation, and an independent
fresh-context code review. The runbook records exact bootstrap, provisioning,
server, login/CSRF, CRUD, and teardown commands without embedding secrets.

### 9. Apply the change with explicit orchestration, implementation, and review roles

The code implementation uses a Sol medium agent as orchestrator, Luna agents
for scoped implementation tasks, and a fresh-context Sol high agent for the
final local code review. The orchestrator owns sequencing, artifact fidelity,
integration decisions, verification, and the working tree; Luna implementers
receive narrow task groups with exact tests and must not broaden scope. The
reviewer does not inherit implementation conclusions and reports findings
before any commit is created.

Shared-worktree changes require the orchestrator to inspect the diff between
delegations, avoid concurrent edits to the same files, and preserve unrelated
user modifications. A task is complete only after its stated verification,
not merely after an implementer reports completion. The orchestrator resolves
review findings, reruns affected tests and the final gate, then commits only
if the fresh review is clear. Pushing or opening a pull request still requires
separate authorization.

## Risks / Trade-offs

- **Bootstrap-only schema changes can discard local data.** Use only a named,
  dedicated disposable management database and make rebuild an explicit
  operator action. Add a reviewed migration before any retained environment.
- **In-memory throttling is process-local.** Document the single-process
  deployment bound and require shared storage before scaling horizontally.
- **JSONB criteria are harder to query and evolve.** Keep Pydantic as the deep
  validation authority and add normalized tables only when matching/query
  needs justify migration.
- **Offset pagination may shift during concurrent writes.** Deterministic
  ordering makes behavior predictable enough for MVP; adopt cursors later.
- **Last-write-wins can overwrite concurrent edits.** Timestamps provide audit
  clues, but optimistic concurrency remains a follow-up.
- **CSRF token handling adds a client responsibility.** The explicit header is
  required because cookie authentication alone is vulnerable to cross-site
  requests; the future UI must retain it in memory and refresh it on login.
- **Country/industry/region labels are not canonical.** Preserve strict shape
  without pretending a vocabulary exists; controlled identifiers can be
  introduced with an explicit migration and matching design.

## Migration Plan

1. Add dependencies only if implementation proves the standard library,
   Flask/Werkzeug, Pydantic, and psycopg stack insufficient; password hashing
   requires no new package.
2. Extend `operational.sql` and schema/readiness tests for the four new table
   families and their indexes/constraints.
3. Recreate only an explicitly selected disposable management database and
   apply the complete schema sequence. Never reset a shared/default database.
4. Deliver provisioning, then authentication, then owner-scoped resources in
   dependency order. Keep startup inert throughout.
5. Run the two-user end-to-end flow and full verification gate before merge.
6. Roll back application code by reverting the change. For disposable local
   data, rebuild from the earlier bootstrap; for retained data, do not drop
   columns or tables and instead prepare a separate rollback migration.

## Open Questions

None block implementation. Before a multi-process or public deployment,
choose shared login-throttle storage and a retained-data migration mechanism;
both are deliberately beyond this local MVP.
