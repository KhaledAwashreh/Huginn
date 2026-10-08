# Browser foundation runbook

Use the feature checkout containing the layered management API. The browser is a
Vue SPA; FastAPI remains the only application server. Signup, email verification,
recovery, configuration editors and the administrator console are separate changes.

## Prerequisites and checks

Use Python 3.14 with the committed uv.lock, Node **24.21.0** from
`frontend/.node-version`, and npm **12.2.0** from packageManager. Use your Node
version manager to select that exact version. PrimeVue 4.5.5 and the theme 1.2.5
are MIT releases. Install the exact npm version if your Node distribution differs.

From the repository root:

```bash
rtk uv sync --frozen --python 3.14
rtk npm --prefix frontend ci
rtk npm --prefix frontend run check
rtk npm --prefix frontend exec -- playwright install --with-deps chromium
rtk npm --prefix frontend run test:e2e
rtk uv run --frozen python -m compileall -q src tests scripts
rtk uv run --frozen ruff check .
rtk uv run --frozen ruff format --check .
rtk uv run --frozen pytest -q
rtk openspec validate web-ui-foundation --strict
```

Docker is required for live tests. Browser fixtures start real FastAPI against a
UUID-named PostgreSQL 16 testcontainer database, provision harmless fixture accounts
and clean up their container. No shared database is reset and no scraping is run.
The full Python suite has independently isolated integration fixtures. Browser
installation may require host dependency installation; hooks do not install it.
Missing required Node/npm/dependencies fail conditional hooks with setup guidance.

`api:generate` exports deterministic OpenAPI directly from the composed app without
startup, a database connection, SMTP or a running server, then generates locked
TypeScript transport types. Review both generated files together. `api:check`
compares temporary output without modifying committed files. Backend schema edits
must pass this gate too.

## Development and deployment

Follow [the existing management runbook](management-foundation.md) to provision
an owner in a dedicated development database and configure backend environment.
Start the backend on its normal loopback port 8000:

```bash
rtk uv run --frozen python -m huginn.management
rtk npm --prefix frontend run dev
```

Vite proxies `/api` to that backend and preserves the browser Host so login's
same-origin guard can validate Origin. Do not configure permissive credentialed CORS.

For production, run `rtk npm --prefix frontend run build` and set
`HUGINN_FRONTEND_ASSETS_PATH` to the **absolute** path of that checkout's
`frontend/dist` in deployment environment configuration. FastAPI serves the build
after API/docs/health routes. Browser deep links get index.html; unknown API routes,
missing assets and files outside the build directory return 404. Hash assets are
immutable; index and session bootstrap use no-store. Configure production secure
cookies and HTTPS through the existing management environment contract.

Omit the assets environment setting, or point to an absent build, for API-only
startup. Backend CLI, runtime and tests do not require Node or frontend artifacts.

## Sessions and rollback

Login is followed by GET `/api/v1/sessions/current`. The HttpOnly opaque cookie
never appears in JSON or browser storage. Bootstrap returns identity, expiry and
a stable purpose-separated CSRF proof derived from the credential. A conditional
database transition converges legacy random proofs across tabs and revalidates
account/session state under locks. Existing sessions are not revived or extended.

An older open tab with a random proof receives 403 and reload guidance. Reload
obtains the stable proof; the failed mutation is not replayed. A 401 clears private
query data and returns to sign-in. Credential/identity changes invalidate pending
reads and cached data. A failed sign-out retains identity with actionable feedback.

Remove the assets setting to roll back the browser independently. Rolling back the
server to an older random-CSRF implementation requires users with transitioned
sessions to sign in again. No schema migration or shared-data reset is needed.

See [ADR-0016](../adr/0016-browser-foundation-and-session-bootstrap.md).
