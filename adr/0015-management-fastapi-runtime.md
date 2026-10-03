# 0015: Use FastAPI and Uvicorn for the management API

Status: Accepted
Date: 2026-10-03
Deciders: Khaled Awashreh

## Context and Problem Statement

The management API was first established with Flask in ADR-0011. The complete
CRUD implementation is now moving to FastAPI, so the original framework choice
no longer describes the running application. The API needs typed request and
response boundaries, generated OpenAPI, and framework validation while
preserving synchronous psycopg repositories and explicit transaction
ownership. The runtime choice must also make the limits of the process-local
login throttle clear.

## Decision Drivers

1. FastAPI integrates the existing Pydantic 2 models with routing, dependency
   injection, response validation, and generated OpenAPI.
2. psycopg repositories and application services remain synchronous; moving
   only the HTTP boundary must not block the ASGI event loop.
3. Password hashing imports Werkzeug directly and must not depend on Flask to
   install it transitively.
4. The local entry point and runbook need predictable single-process defaults.

## Considered Options

1. FastAPI with Uvicorn and synchronous psycopg. (chosen)
2. Retain Flask and hand-build validation and OpenAPI.
3. Rewrite repositories and services for asynchronous psycopg.

## Decision Outcome

Chosen option: 1, FastAPI with Uvicorn, Pydantic 2, and synchronous psycopg 3.
Database-backed routers and dependencies use ordinary `def` functions, which
FastAPI executes in its worker thread pool. This preserves the established
transaction and repository design while keeping blocking database operations
off the ASGI event loop. `python -m huginn.management` binds to
`127.0.0.1:8000` and disables reload; deployment-specific worker, thread, and
connection capacity are outside this local development command.

Flask is no longer the management runtime. Werkzeug remains an explicit
runtime dependency because password code imports its scrypt helpers directly.
FastAPI generates `/openapi.json`, `/docs`, and `/redoc` from executable route
declarations. Invalid request values return the conventional HTTP 422 response
with sanitized details that omit submitted input and validation context.

The failed-login throttle remains in memory per process. The runtime therefore
uses one process until a shared throttle backend is selected; process-local
state must not be mistaken for a deployment-wide limit.

### Consequences

1. Good: request parsing, response filtering, dependency wiring, and API
   documentation use FastAPI's standard mechanisms.
2. Good: the migration keeps psycopg repositories and transaction ownership
   synchronous without running database calls on the event loop.
3. Good: Werkzeug's password-hashing dependency is explicit and survives
   removal of Flask.
4. Bad: database concurrency is bounded by worker-thread capacity and must be
   planned with PostgreSQL connection capacity.
5. Bad: the in-memory login throttle is not coordinated across processes.
6. Neutral: native FastAPI request-validation status and details replace the
   previous Flask parsing behavior; details are sanitized to protect secrets.

## Pros and Cons of the Options

### FastAPI with Uvicorn and synchronous psycopg (chosen)

1. Good: Pydantic models integrate directly with validation, response models,
   dependency injection, and generated OpenAPI.
2. Good: standard `def` endpoints run in FastAPI's worker thread pool, so
   synchronous psycopg I/O does not block the ASGI event loop.
3. Bad: production thread and process capacity must be bounded against
   database connections, and process-local throttle state limits deployment
   topology.

### Retain Flask and hand-build validation and OpenAPI

1. Good: it retains the original synchronous development-server model.
2. Bad: validation, dependency composition, response filtering, and OpenAPI
   require custom plumbing already provided by FastAPI.

### Rewrite for asynchronous psycopg

1. Good: an end-to-end async design could support high concurrent I/O.
2. Bad: it requires changing repository protocols, unit of work, services,
   dependencies, tests, and lifecycle code without measured need.

## Related

1. [ADR-0011](0011-management-api-foundation.md), the superseded Flask
   foundation decision.
2. [Management foundation runbook](../docs/management-foundation.md).
3. OpenSpec change `management-api-crud`, including runtime and cleanup tasks.
4. Jira KAN-71 through KAN-78, management foundation and CRUD capabilities.
