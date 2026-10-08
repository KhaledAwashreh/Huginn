# 0016: Browser foundation and session bootstrap

Status: Accepted
Date: 2026-10-08
Deciders: Khaled Awashreh

## Context and Problem Statement

Huginn needs configuration pages and an administrator pipeline console over the
existing JSON management API. Cookie sessions lacked an identity/bootstrap read;
random CSRF proofs available only at login made reload and multiple tabs awkward.

## Decision Drivers

1. The owner prefers a minimal JSON frontend with less HTML back-and-forth than HTMX.
2. Existing FastAPI layering, session storage and API-only operation must remain usable.
3. Reload and legacy tabs must preserve sessions without exposing opaque credentials.
4. Tooling must be reproducible and browser data must remain isolated by identity.

## Considered Options

1. Vue SPA served by FastAPI with stable per-session bootstrap (chosen).
2. React or Angular SPA over the same API.
3. Next.js with another server runtime.
4. HTMX server-rendered interaction.

## Decision Outcome

Chosen option: 1. Vue Composition API, TypeScript, Vite, Router, MIT PrimeVue 4
and TanStack Vue Query provide a compact configuration UI over the existing API.
Pin Node 24, npm and direct dependencies with a committed lockfile. Generate
transport types offline from the composed OpenAPI schema and check drift.

Bootstrap authenticates the HttpOnly credential and returns identity, expiry and
HMAC-derived purpose-separated CSRF proof. Store only digests. Atomically transition
legacy proof digests after locked active-state revalidation. Never replay failed
mutations. Invalidate query data and pending reads on identity/proof changes.

### Consequences

1. Good: FastAPI remains the sole application server; static delivery is optional.
2. Good: Reload and multiple tabs converge on one proof without storing credentials in JS.
3. Bad: The frontend adds a Node build/test toolchain and requires browser interaction tests.
4. Bad: Old open tabs need reload; rolling back to random-CSRF servers requires new login.

## Pros and Cons of the Options

### Vue SPA

1. Good: Small composition-oriented UI aligned with the chosen JSON workflows.
2. Bad: Browser routing, accessibility and session boundaries need explicit maintenance.

### React or Angular SPA

1. Good: Both support the same API and mature component/testing ecosystems.
2. Bad: They offer no decisive benefit for the agreed compact Vue implementation.

### Next.js

1. Good: Supports SSR and a full-stack deployment model.
2. Bad: Adds a server runtime for an authenticated configuration UI without an SSR need.

### HTMX

1. Good: Familiar to the owner and integrates server-rendered forms.
2. Bad: Its repeated backend/template interaction conflicts with the owner's preference.

## Related

1. [ADR-0015](0015-management-fastapi-runtime.md).
2. [Approved foundation design](../openspec/changes/web-ui-foundation/design.md).
3. [Runtime and rollback runbook](../docs/web-ui-foundation.md).
