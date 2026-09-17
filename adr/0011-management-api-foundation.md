# 0011: Use Flask and Pydantic for the management API foundation

Status: Proposed
Date: 2026-09-17
Deciders: Khaled Awashreh

## Context and Problem Statement

KAN-71 establishes the boundary and runtime architecture for a management API
beside Huginn's existing synchronous ELT code. Later tickets need a stable
choice of web framework, validation boundary, identity ownership, and initial
storage representations without introducing authentication or CRUD behavior
in this foundation.

The account, user, and professional profile requirements are persisted in
`architecture-notes/account-user-and-client-discovery-domain.md`. Several
representations needed for implementation remain provisional engineering
decisions rather than new product requirements.

## Decision Drivers

1. Huginn already uses synchronous Python and psycopg 3 with explicit
   composition roots.
2. The initial API needs a small application factory and two operational
   probes, not an ORM, admin site, or asynchronous serving model.
3. Professional collections are transitional JSONB storage, but their object
   shape must be validated before persistence and after loading.
4. KAN-72 through KAN-74 need explicit ownership and authentication handoffs
   without KAN-71 implementing those behaviors early.
5. The stack must install and execute on Python 3.14.

## Considered Options

1. Synchronous Flask 3 with Pydantic 2 boundaries and psycopg 3. (chosen)
2. Django with its ORM and authentication stack.
3. FastAPI with an ASGI application model.

## Decision Outcome

Chosen option: 1, synchronous Flask 3 with Pydantic 2 boundaries and psycopg
3. This matches the repository's explicit synchronous composition while
keeping persistence and request validation independent of an ORM.

The runtime stack is Flask `>=3.1.2,<4`, Pydantic `>=2.12,<3`, psycopg 3, and
Postgres 16. Flask applications use an application factory. KAN-71 adds no
ORM, asynchronous framework, password hashing library, session library, or
authentication middleware.

### Identity and authentication handoff

1. `Account` owns username, password hash, and lifecycle status.
2. `User` owns mandatory personal and contact information and is the ownership
   root for business-domain entities.
3. `ProfessionalProfile` owns validated professional collections.
4. KAN-72 owns atomic creation of exactly one Account, User, and empty
   ProfessionalProfile, including password hashing.
5. KAN-73 owns login verification, opaque revocable server-side sessions,
   token transport, expiry, revocation, CSRF, and authorization. Flask's
   signed client-side session is not the authentication store.

### Provisional storage representations

1. Account status is `active` or `disabled`, defaulting to `active`. Lifecycle
   transitions are deferred.
2. Usernames retain trimmed spelling and use a named unique index on
   `lower(username)`. This does not claim Unicode casefold equivalence.
3. First name, last name, email, phone number, and country of residence are
   trimmed nonblank text. Country is a residence label. Timezone is nullable
   trimmed nonblank text.
4. Semantic validation and normalization for email, phone, country, and
   timezone are deferred to KAN-72 and KAN-74 before owner input is accepted.
5. Account, User, and ProfessionalProfile use UUID primary keys and
   timezone-aware created and updated timestamps. Unique foreign keys enforce
   at most one child; KAN-72's transaction enforces exactly one at creation.

### Professional collection boundary

1. `skills`, `experience`, and `previous_projects` are JSONB arrays of
   objects, never null, and default to independent empty arrays.
2. SQL validates only the outer array and object shape. Pydantic validates
   item fields before persistence and after loading typed values.
3. Boundary models are strict, frozen, and reject extra keys. Required text
   is trimmed and nonblank. Optional text and dates may be omitted or null,
   but supplied strings must be nonblank.
4. `Skill` contains only `name`; proficiency, rank, and years are rejected.
5. `Experience` requires `organization` and `role`; `summary`, `start_month`,
   and `end_month` are optional, and `is_current` defaults to false.
6. `PreviousProject` requires `name` and `description`.
7. Months use `YYYY-MM` from `0001-01` through `9999-12`. End cannot precede
   start, and current experience cannot have an end month. Unknown dates are
   allowed.
8. Collection order and duplicates are preserved. Item IDs, deduplication,
   normalization tables, and migration execution are deferred.

### Consequences

1. Good: later management tasks receive a small, explicit synchronous stack
   and stable validation interfaces.
2. Good: deep JSON shape is testable without coupling domain objects to SQL or
   an ORM.
3. Good: identity ownership and deferred authentication responsibilities are
   explicit before provisioning and endpoint work starts.
4. Bad: JSONB collections cannot provide normalized child-table querying,
   provenance, or independent updates without a future migration.
5. Neutral: frozen Pydantic models prevent field assignment but do not make
   nested lists immutable; callers treat them as short-lived boundary values.

## Pros and Cons of the Options

### Flask 3 and Pydantic 2 (chosen)

1. Good: fits synchronous psycopg and explicit application composition.
2. Good: keeps web routing, validation, and persistence separate.
3. Bad: validation errors and OpenAPI behavior are not supplied as an
   integrated framework feature and must be composed when CRUD arrives.

### Django

1. Good: includes mature ORM, authentication, and administration features.
2. Bad: introduces broad framework facilities that KAN-71 explicitly does
   not use and conflicts with the selected handwritten SQL boundary.

### FastAPI

1. Good: integrates Pydantic and generated API documentation.
2. Bad: introduces an ASGI serving model without a current concurrency need
   and diverges from the repository's synchronous runtime shape.

## Related

1. Jira KAN-71, management API foundation and operational bootstrap schema.
2. Jira KAN-72, atomic provisioning and owner account CLI.
3. Jira KAN-73, authentication, sessions, and ownership enforcement.
4. Jira KAN-74, User and ProfessionalProfile management API.
5. `architecture-notes/account-user-and-client-discovery-domain.md`.
