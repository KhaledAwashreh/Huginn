# KAN-71 Management Foundation Implementation Plan

> **Superseded planning-session instruction:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Steps use checkbox syntax. The planning session did not authorize execution
> or commits. The execution amendment below now governs implementation.

> **Execution amendment (2026-09-17):** The user subsequently authorized and
> required per-task commits for the Subagent-Driven Development run. That
> authorization supersedes the historical planning restriction above. Review
> packages use committed ranges from `origin/master`; implementers report each
> commit SHA. The controller alone may push and create the PR after local gates,
> and nobody may merge. Implementation requirements are unchanged.

**Goal:** Deliver a Python 3.14 management API foundation and fresh operational
bootstrap schema, with live Postgres evidence and no business endpoints.

**Architecture:** Add `huginn.management` beside `huginn.elt` and `huginn.ops`.
Use a synchronous Flask application factory, Pydantic boundary schemas, and a
small psycopg readiness adapter behind a Protocol. Keep handwritten bootstrap
SQL and the existing dependency order.

**Tech Stack:** Python 3.14, uv, Flask 3, Pydantic 2, existing psycopg 3,
Postgres 16, pytest, testcontainers, Ruff. No ORM or migration framework.

**Spec:** The persisted KAN-71 contract in these two read-only inputs:

1. `architecture-notes/account-user-and-client-discovery-domain.md`,
   especially Confirmed decisions and Management MVP implementation tasks.
2. Historical context only: the planning session referenced
   `architecture-notes/management-mvp-codex-session-log-2026-09-17.md`,
   especially First action tomorrow and Verification process. That session
   log is absent from this branch and is not an implementation authority or
   build dependency.

## Authority And Starting Point

1. The user's scope is KAN-71, "Management API foundation and operational
   bootstrap schema". Jira OAuth is unavailable. Do not query Jira, infer
   additional acceptance criteria, or claim a Jira transition/comment occurred.
2. Read the repository-root `CLAUDE.md`, `docs/architecture.md` sections 2,
   3, 9 and 10,
   `docs/entities.md`, `db/schema/operational.sql`, and `pyproject.toml`.
   For the management model, the newer persisted contract supersedes the old
   `User.icp_profile` placeholder and single-credential architecture sketch.
   It does not supersede unrelated ELT decisions.
3. Relevant conventions: `src/huginn/config.py`,
   `src/huginn/elt/ingestion/__main__.py`,
   `src/huginn/ops/postgres_job_run_writer.py`, `tests/conftest.py`,
   `tests/elt/gold/test_company_repository_integration.py`,
   `db/schema/README.md`, `.github/workflows/ci.yml`, ADR-0003, ADR-0004,
   ADR-0005, and `adr/template.md`.
4. Planning baseline: branch `management/kan-71-foundation`, HEAD
   `4a66506dba736ea8e89c2ffc1bc39e227eef33a0`. The worktree was clean before
   this plan was added. Recheck at execution time and preserve newer changes.
5. The domain note explicitly leaves some representations undecided. Choices
   labeled "Selected implementation decision" below make this plan executable;
   they are not claims of additional user-approved product requirements.

## Global Constraints

1. Work only in the dedicated `management/kan-71-foundation` worktree. Read
   repository-relative authority files there without editing another checkout.
2. During planning, no commits, pushes, merges, PR creation, database resets,
   or Jira writes were authorized. For execution, per-task commits are required
   for review packages. The controller alone may push and create the PR after
   local gates; nobody may merge. Preserve unrelated user changes and existing
   untracked files. No subagents during planning. During execution, the
   controller alone dispatches one fresh implementer at a time and independent
   reviewers.
3. Python remains `>=3.14`; verify on Python 3.14 specifically. Use uv and
   prefix shell commands with `rtk` per the session's shell instructions.
   Commands below run from the worktree root unless explicitly stated.
4. TDD: write a failing behavioral test, observe its intended failure, make
   the smallest implementation, then rerun. Dependency setup failures and
   unavailable Docker do not count as behavioral RED evidence.
5. Core values remain frozen dataclasses; boundaries may use frozen Pydantic
   models. Interfaces are `typing.Protocol`. Use synchronous psycopg and
   context-managed connections, no asyncio, global connections, ORM, pool,
   speculative repository layer, or pyright installation.
6. No automatic DDL, migrations, reset, truncate, provisioning, or seed data
   at import, factory construction, server start, health, or readiness.
7. A dedicated `HUGINN_MANAGEMENT_DATABASE_URL` configures management.
   Never fall back to `HUGINN_DATABASE_URL`. Separate management development
   databases protect concurrent ELT work; this is development isolation,
   not a decision to split the production domain across databases.
8. Fresh bootstrap only. Preserve existing operational tables and all their
   foreign keys to `operational.users` and `gold.company`. Do not edit Bronze,
   Silver, Gold, ops, or existing ELT behavior.
9. Required personal fields are non-null. Professional collections are JSONB
   arrays of structured objects and default to `[]`, never SQL or JSON null.
   User owns domain data; Account owns credentials/lifecycle.
10. Log through per-module standard loggers. Configure handlers only at the
    executable entrypoint. Never log DSNs, credentials, raw validation input,
    or raw database exceptions that may contain credentials or row contents.
11. ASCII documentation and code additions, no em dashes. Cite architecture
    or the new ADR in docstrings. No unrelated refactors or formatting churn.
12. Completion requires focused live Postgres tests without skips, Python
    compile, Ruff lint/format, full pytest, and diff checks. A green suite
    whose database tests skipped is insufficient evidence for KAN-71.

## Selected Stack And Contract Decisions

1. Add runtime requirements `flask>=3.1.2,<4` and `pydantic>=2.12,<3`.
   Retain psycopg, python-dotenv, requests, and the existing dev group.
   Resolve with Python 3.14; `uv.lock` is part of the Task 1 commit and its
   reviewable change. No new test client dependency: Flask supplies one.
2. Flask is selected because the repository already uses synchronous I/O,
   explicit composition roots and small modules. Django would introduce an
   unused ORM/auth stack; FastAPI would introduce an ASGI serving model without
   a current concurrency need. This is an engineering choice, not a claim
   that FastAPI cannot run synchronous handlers.
3. Flask documents Python 3.9 and newer and the application-factory pattern.
   Pydantic 2.12 introduced Python 3.14 support. Verify the actual resolved
   dependency set with the gates below; documentation is not a substitute
   for installing and executing it on 3.14.
   Sources checked during planning:
   [Flask installation](https://flask.palletsprojects.com/en/stable/installation/),
   [Flask factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/),
   [Pydantic 2.12 release](https://pydantic.dev/articles/pydantic-v2-12-release).
4. Record the durable choice using `adr/template.md` in
   `adr/0011-management-api-foundation.md`, with Status: Proposed and the
   distinction between persisted requirements and selected defaults.
5. Selected implementation decision: Account status is `active` or `disabled`,
   default `active`. This is a storage vocabulary, not lifecycle transition
   behavior. KAN-73 implements disabled-account enforcement.
6. Selected implementation decision: preserve trimmed username spelling and
   enforce uniqueness on PostgreSQL `lower(username)`. Require nonblank text
   with no surrounding whitespace. Case-insensitivity follows the database's
   collation; no claim of Unicode casefold equivalence. KAN-72 and KAN-73
   must use the same expression for conflict checks and lookup. No `citext`.
7. Selected implementation decision: names, email, phone and country are
   trimmed nonblank text. Country is a residence label in this foundation,
   not a newly invented ISO catalog. Email/phone have no uniqueness or
   normalization rule beyond that storage boundary. Optional timezone is
   nullable trimmed nonblank text. Semantic email/phone/country/timezone
   validation belongs to KAN-72/KAN-74 before accepting user input.
8. Authentication handoff, documentation only: Account supplies username,
   password_hash and status; User is the ownership root. Use the persisted
   proposed opaque, revocable, server-side session direction for KAN-73.
   Do not use Flask's signed client-side session as the authentication store.
   Password hashing implementation belongs to KAN-72 and login verification,
   token transport, expiry, revocation, CSRF and authorization to KAN-73.
   KAN-71 installs no hashing/session dependency or authentication middleware.

## SQL Contract

Only two new tables are added, `operational.accounts` and
`operational.professional_profiles`; the existing `operational.users` is
replaced in the fresh DDL. No other KAN-71 foundation tables are needed.

1. All three tables use `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` and
   `created_at`/`updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
   `updated_at` is maintained by later writers, not by a new trigger.
2. `accounts`: username and password_hash are required TEXT; username has
   the trim/nonblank CHECK and a named unique index on `lower(username)`.
   password_hash must be nonblank, with no algorithm-specific CHECK.
   Status is required TEXT with the vocabulary and default above.
3. `users`: `account_id UUID NOT NULL UNIQUE REFERENCES operational.accounts
   (id)`; first_name, last_name, email, phone_number and country_of_residence
   are required trimmed nonblank TEXT; timezone is optional TEXT with the
   same CHECK when non-null. Remove `icp_profile`; do not relocate it into
   generic preferences JSON.
4. `professional_profiles`: `user_id UUID NOT NULL UNIQUE REFERENCES
   operational.users (id)`; headline and professional_summary are nullable
   TEXT, nonblank after trimming when present. skills, experience and
   previous_projects each use `JSONB NOT NULL DEFAULT '[]'::jsonb` and a
   CHECK requiring a top-level array containing only objects.
5. Foreign keys retain default `NO ACTION` delete/update behavior. No
   cascading deletion or delete endpoint. Unique FKs enforce at most one
   child and no orphan child. They do not enforce a mandatory child on
   parent insertion. KAN-72 must create Account, User and empty profile in
   one transaction to realize the required exactly-one lifecycle. No
   circular FKs, deferred trigger machinery or auto-created profiles here.
6. Preserve `employee`, `match`, `match_score`, `match_feedback`, `activity`,
   `communication`, `communication_version`, `communication_revision` and
   `communication_turn`. In particular, `match.user_id` still references
   `operational.users(id)`. These are legacy bootstrap tables, not new
   management features. Leave their columns and constraints unchanged.
7. Deferred tables: sessions (KAN-73), service offerings (KAN-75), ICPs
   (KAN-76), discovery strategies and reference constraints (KAN-77).
   BuyerPersona and EngagementPreferences remain domain concepts only.
   No matching contribution table, migration history table, audit table,
   role table or normalized professional child tables.
8. Preserve bootstrap order: `00_extensions.sql`, `ops.sql`, `bronze.sql`,
   `silver.sql`, `gold.sql`, `operational.sql`. A management development
   database receives all six, with empty ELT tables, because retained
   operational foreign keys reference Gold. Never remove those FKs merely
   to run `operational.sql` by itself.

Use this CHECK expression for each collection, substituting its column:

```sql
CHECK (
    jsonb_typeof(skills) = 'array'
    AND NOT jsonb_path_exists(skills, '$[*] ? (@.type() != "object")')
)
```

The database guards container shape; Pydantic guards object fields. SQL is
not a duplicate general JSON Schema validator. Direct SQL can bypass deep
validation, so every downstream writer must use the shared schemas.

## Structured Collection Contract

These are selected version-one storage contracts, not profile CRUD request
models. They validate only the three JSON collections needed by the bootstrap.
Use `ConfigDict(strict=True, extra="forbid", frozen=True)` on boundary models.
Reject coercion of numbers to strings, strings to booleans, and unknown keys.
Required strings are stripped and must remain nonempty. Optional strings may
be omitted or null; when supplied as strings they must remain nonempty.

| Object | Required fields | Optional fields and defaults |
| --- | --- | --- |
| `Skill` | `name: string` | None; proficiency/rank/years are rejected |
| `Experience` | `organization: string`, `role: string` | `summary: string or null = null`, `start_month: string or null = null`, `end_month: string or null = null`, `is_current: boolean = false` |
| `PreviousProject` | `name: string`, `description: string` | None |
| `ProfessionalCollections` | None | `skills: array[Skill] = []`, `experience: array[Experience] = []`, `previous_projects: array[PreviousProject] = []` |

1. Months use exactly `YYYY-MM`, years 0001 through 9999, months 01 through
   12. If both dates exist, end must be greater than or equal to start.
   `is_current=true` forbids a non-null end_month. Unknown start/end dates
   are allowed; do not infer duration or enforce dates relative to today.
2. Omitted collections normalize to new empty lists; explicit null is
   rejected. Empty experience and skills are legal during provisioning.
   Previous projects are optional for the person, represented by `[]`.
   List order and duplicate entries are preserved; no deduplication policy.
3. Examples of stored objects:

```json
{
  "skills": [{"name": "Python"}],
  "experience": [{"organization": "Acme", "role": "Consultant", "summary": null, "start_month": "2024-01", "end_month": null, "is_current": true}],
  "previous_projects": [{"name": "Reporting API", "description": "Delivered a reporting service."}]
}
```

4. Export `Skill`, `Experience`, `PreviousProject`, and
   `ProfessionalCollections` from `huginn.management.schemas`. Use
   `.model_validate(payload)` and `.model_dump(mode="json")`; callers pass
   individual collection lists to psycopg `Jsonb`. No model is an ORM entity.
   Do not expose a validation/debug endpoint to demonstrate these models.
5. Frozen Pydantic models freeze field assignment, not nested list mutation.
   Treat these as short-lived boundary values and replace rather than mutate
   them. Future domain entities remain frozen dataclasses; do not introduce
   duplicate Account/User domain models just for this ticket.
6. Full field/type validation runs before persistence by future KAN-72/74
   writers, and on loading these collections before using them as typed
   values. SQL tests prove outer shape only; schema unit tests prove deep
   shape and JSON round trips. No HTTP validation status-code policy yet.
7. Migration boundary: retain object keys and array order. When independent
   updates, querying, provenance or relationships justify child tables,
   KAN-49 must plan extraction and compatibility. There are no item IDs,
   version column, migration executor or normalization tables in KAN-71.
8. ICP item shapes, empty-selection semantics and preference-versus-mandatory
   criteria are explicitly deferred to KAN-76 before its implementation.
   They are not embedded into this foundation. The same applies to offering
   and strategy validation contracts in KAN-75/KAN-77.

## Runtime Contract

1. `ManagementConfig` is a frozen dataclass with `database_url: str`, using
   `field(repr=False)` to keep credentials out of repr. `load_config() ->
   ManagementConfig` loads dotenv then only `HUGINN_MANAGEMENT_DATABASE_URL`.
   Missing/blank configuration raises RuntimeError naming the variable,
   without echoing any supplied value. No database access while loading.
2. `ReadinessPort` declares `is_ready(self) -> bool`.
   `PostgresReadiness(database_url: str)` implements it. Constructor is
   inert. Each check opens/closes one connection with `connect_timeout=2`,
   server `statement_timeout=2000` milliseconds and a read-only transaction.
   No retries or global connection. A multi-host DSN is not promised a
   two-second total wall-clock bound by libpq's per-host timeout.
3. Readiness executes `SELECT 1`, then SELECTs every contract column from
   each of accounts, users and professional_profiles with `LIMIT 0`.
   This checks connectivity, read permissions and expected tables/columns
   without reading user data. Missing tables/columns or psycopg errors
   return false. Readiness is not a full constraint/migration auditor and
   cannot prove write permissions; live bootstrap tests prove constraints.
4. Catch `psycopg.Error`, log one sanitized warning with exception class
   name only, return false; do not swallow programming exceptions such as
   TypeError from application code. Success needs no per-request log.
5. `create_app(config: ManagementConfig | None = None, *, readiness:
   ReadinessPort | None = None) -> Flask` resolves config if absent and
   constructs PostgresReadiness only if no dependency was supplied. Use
   `Flask(__name__, static_folder=None)`; no static route or template UI.
   Factory construction makes no database call.
6. Routes are GET `/health` -> 200 `{"status": "ok"}` without a readiness
   call; GET `/ready` -> 200 `{"status": "ready"}` or 503
   `{"status": "not_ready"}`. Both return application/json. HEAD/OPTIONS
   may use Flask defaults; POST to these routes is 405. No other application
   routes; `/accounts`, `/users`, `/login`, `/sessions`, `/profiles`,
   `/offerings`, `/icps`, `/strategies` remain 404. No auth or Set-Cookie.
7. `python -m huginn.management` configures logging and runs the local
   development server on 127.0.0.1:8000 with debug and reloader disabled.
   Server deployment, production WSGI server selection, TLS and CORS policy
   are not deliverables. The Flask CLI can override the development port.

## Execution And Review Protocol

1. Execute Tasks 1 through 5 in order. Each has one owner; no parallel
   implementers and no worker-dispatched helpers or reviewers. The controller
   supplies authority references, this entire common pre-task contract, and
   the extracted task brief to each fresh implementer and reviewer.
2. The installed `scripts/task-brief` extracts only `Task N`, not this
   preamble. Copy the pre-task contract to a common brief inside this plan's
   SDD workspace and pass its path as well. Do not rely on inherited chat.
3. The controller creates the skill's per-plan ledger only at execution.
   Record a preflight table for Tasks 1-5 and shared interfaces: 1->2
   (schemas/JSON), 2->3 (DDL/fixtures), 3->4 (config/readiness), 1-4->5
   (documented behavior). No implementation file is jointly owned.
4. Commit each completed task before assembling its SDD review package. Use
   the exact committed range from the previous task SHA, or `origin/master`
   for Task 1, through the task's reported SHA. Before each commit, inspect the
   index and working tree, preserve unrelated user changes and untracked files,
   and stage only files owned by that task.
5. Every task gets independent spec-compliance and code-quality verdicts
   before proceeding. Return findings to the implementer and rerun affected
   checks. Commit every post-review fix, or amend the task commit where
   appropriate, and report the resulting SHA. Rerun the independent review
   over the updated exact committed range. Repeat this review loop over each
   updated committed range until both the spec-compliance and code-quality
   verdicts pass, unless an explicit recorded ruling resolves or accepts every
   finding. Do not progress to the next task before that condition is met.
   Controller coordinates, not implements. Follow the installed skill's
   bounded review loop and record rulings explicitly.
6. Each implementer reports files, intended RED failure, GREEN evidence,
   exact commands, test counts/skips, concerns, the task commit SHA, and every
   resulting post-review fix or amended SHA. Preserve the ignored ledger and
   review artifacts; do not run the skill's post-merge cleanup or
   branch-finishing mutations.
7. Final independent review covers committed `origin/master...HEAD`.
   At execution, read `.claude/skills/pre-mr-review/SKILL.md` if present;
   if missing, report that limitation and still perform the local gates and
   independent review. No external CodeRabbit invocation without existing
   authorization. The file was present during planning. After all local gates
   and reviews pass, only the controller may push and create the PR. Nobody
   merges.
   Reuse the SDD final independent review as the pre-MR independent review
   when it covers the same complete diff. Planning performs self-review only.

## Task 1: Pin The Stack And Validate Professional Collections

**Files:** Create `src/huginn/management/__init__.py`,
`src/huginn/management/schemas.py`, `tests/management/__init__.py`,
`tests/management/test_schemas.py`, and
`adr/0011-management-api-foundation.md`. Modify `pyproject.toml` and `uv.lock`.

**Interfaces:** Produce the four Pydantic classes in Structured Collection
Contract, including `.model_validate`, `.model_dump(mode="json")` and
`.model_json_schema()`. Package initializer contains only a citing docstring;
do not re-export app/config or connect to Postgres. Consumers are Task 2
and future KAN-72/KAN-74. No table or application code in this task.

- [ ] **Step 1: Resolve dependencies on 3.14.**

```bash
rtk uv add --python 3.14 'flask>=3.1.2,<4' 'pydantic>=2.12,<3'
rtk uv sync --python 3.14 --locked
rtk uv run --python 3.14 python --version
```

Expected: Python 3.14.x, an updated lockfile, no changes to unrelated direct
requirements. Resolve installation failures before claiming RED evidence.
Record the stack rationale, auth handoff, provisional representations and
validation boundaries from the common contract in ADR-0011.

- [ ] **Step 2: Write schema tests and observe RED.**

Start with these executable tests, then add the concrete cases below:

```python
import pytest
from pydantic import ValidationError

from huginn.management.schemas import ProfessionalCollections


def test_omitted_collections_are_empty_arrays():
    assert ProfessionalCollections.model_validate({}).model_dump(mode="json") == {
        "skills": [], "experience": [], "previous_projects": []
    }


@pytest.mark.parametrize("value", [None, ["Python"], [{"name": " "}], [{"name": 7}]])
def test_invalid_skills_are_rejected(value):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate({"skills": value})
```

1. Accept and round-trip the common-contract example; trim name strings.
2. Reject unknown fields at each level, including skill proficiency/years.
3. Reject null for every collection; reject a scalar or nested list item.
4. Reject missing required organization/role and project name/description.
5. Accept missing and null optional strings/dates; reject blank strings.
6. Reject `2024-00`, `2024-13`, `24-01`, `0000-01`, `2024-1` and full dates;
   accept `0001-01`, `9999-12` and equal start/end months.
7. Reject reversed months, current work with an end, and `"true"` as boolean;
   accept current work without dates and historical work with unknown dates.
8. Preserve order/duplicates; instances do not share default list objects.
9. Generated JSON Schema identifies arrays of objects and forbids extra keys.

```bash
rtk uv run --python 3.14 pytest tests/management/test_schemas.py -v
```

Expected RED: missing module/model first; after the minimal module exists,
run each new validation test before its validator and see the expected
acceptance/rejection fail. Do not treat one import error as proof of all rules.

- [ ] **Step 3: Implement just the boundary schemas.**

Use this implementation shape and the exact fields in the common table:

```python
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Month = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Skill(BoundaryModel):
    name: NonBlank


class Experience(BoundaryModel):
    organization: NonBlank
    role: NonBlank
    summary: NonBlank | None = None
    start_month: Month | None = None
    end_month: Month | None = None
    is_current: bool = False

    @model_validator(mode="after")
    def validate_months(self) -> Self:
        for value in (self.start_month, self.end_month):
            if value is not None and value.startswith("0000-"):
                raise ValueError("month year must be at least 0001")
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError("end_month precedes start_month")
        if self.is_current and self.end_month is not None:
            raise ValueError("current experience cannot have end_month")
        return self


class PreviousProject(BoundaryModel):
    name: NonBlank
    description: NonBlank


class ProfessionalCollections(BoundaryModel):
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    previous_projects: list[PreviousProject] = Field(default_factory=list)
```

- [ ] **Step 4: Verify and hand off.**

```bash
rtk uv run --python 3.14 pytest tests/management/test_schemas.py -v
rtk uv run ruff check src/huginn/management tests/management
rtk uv run ruff format --check src/huginn/management tests/management
```

Expected: all schema tests pass. Record dependency versions and schema
decisions in the report. Commit Task 1, report its SHA, complete independent
task review, then proceed to Task 2.

## Task 2: Prove The Fresh Operational Schema In Postgres

**Files:** Modify `db/schema/operational.sql`. Create
`tests/management/conftest.py` and
`tests/management/test_operational_schema_integration.py`.

**Interfaces:** Consume Task 1's ProfessionalCollections. Produce the exact
SQL Contract and two test-only fixtures:
`management_database_url` (session-scoped, fully bootstrapped container) and
`empty_management_database_url` (function-scoped, fresh container without
schemas). Tasks 3 and 4 consume these fixture names. Do not edit the root
`tests/conftest.py` or use an environment DSN for these fixtures.

- [ ] **Step 1: Add isolated testcontainers support.**

Follow the existing import/image/driver convention. Tests need real Postgres;
fixture failures must fail, not silently skip. Context managers stop the
containers even if schema application fails. The root conftest can also
start its own container for legacy tests; this intentional additional
container proves management fresh bootstrap without trusting external state.

```python
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "db" / "schema"
SCHEMA_FILES = (
    "00_extensions.sql", "ops.sql", "bronze.sql", "silver.sql",
    "gold.sql", "operational.sql",
)


@pytest.fixture(scope="session")
def management_database_url():
    with PostgresContainer(
        "postgres:16-alpine", username="postgres", password="huginn",
        dbname="huginn_management_test", driver=None,
    ) as container:
        database_url = container.get_connection_url()
        with psycopg.connect(database_url, autocommit=True) as conn:
            for filename in SCHEMA_FILES:
                conn.execute((SCHEMA_DIR / filename).read_text())
        yield database_url


@pytest.fixture
def empty_management_database_url():
    with PostgresContainer(
        "postgres:16-alpine", username="postgres", password="huginn",
        dbname="huginn_management_empty_test", driver=None,
    ) as container:
        yield container.get_connection_url()
```

The explicit order mirrors root conftest and CI. No fixture may reset the
shared development database. SQL constraint tests use an outer transaction
rolled back in `finally`, and `conn.transaction()` savepoints around expected
constraint errors so later assertions do not run in an aborted transaction.

- [ ] **Step 2: Write live tests and observe RED against current DDL.**

```python
def test_account_bootstrap_has_uuid_and_aware_timestamps(management_database_url):
    with psycopg.connect(management_database_url) as conn:
        try:
            row = conn.execute(
                "INSERT INTO operational.accounts (username, password_hash) "
                "VALUES (%s, %s) RETURNING id, status, created_at, updated_at",
                ("schema-test", "test-hash-not-a-real-credential"),
            ).fetchone()
            assert isinstance(row[0], UUID)
            assert row[1] == "active"
            assert row[2].utcoffset() is not None
            assert row[3].utcoffset() is not None
        finally:
            conn.rollback()
```

Import `UUID` from uuid and psycopg. Add plain pytest functions/parametrized
cases covering this complete matrix with parameterized SQL values:

| Area | Required live assertions |
| --- | --- |
| Fresh bootstrap | All six files apply in order; expected management tables exist; no `users.icp_profile` |
| Account | Defaults, required fields, empty/space/tab/newline-only or padded username rejected; `Alice`/`alice` conflict; distinct username succeeds; invalid/null status and whitespace-only hash rejected; disabled accepted |
| User | Every mandatory field rejects null/empty/space/tab/newline-only values and edge whitespace; null timezone accepted, blank rejected; unique account_id; nonexistent account rejected |
| Profile | Unique user_id; nonexistent user rejected; empty defaults; nullable headline/summary; supplied blank rejected |
| Collections | For each column reject SQL NULL, JSON null, object, scalar, string list and nested list; accept empty array and valid object arrays |
| Typed storage | Task 1 model dump through `psycopg.types.json.Jsonb` round-trips and revalidates, preserving values/order |
| Ownership/FKs | Duplicate child rejected; deleting referenced Account/User rejected; SQL permits a parent before child inside a transaction, as KAN-72 requires |
| Existing match FK | Insert a test Gold company and Account/User, then match succeeds; random nonexistent user fails; all test inserts roll back |
| Scope | New sessions/offerings/ICPs/strategies/normalized-profile tables absent; existing operational tables still present |

Use `psycopg.sql.Identifier` for parametrized column-name cases, never string
interpolation of values. Do not assert JSON field-level constraints at SQL:
that boundary is intentionally covered by Task 1.

```bash
rtk proxy env -u HUGINN_DATABASE_URL PYTHON_DOTENV_DISABLED=1 uv run --python 3.14 pytest tests/management/test_operational_schema_integration.py -v -ra
```

Expected RED includes UndefinedTable for accounts and missing user/profile
columns. Docker/image errors are an environment blocker, not useful RED.

- [ ] **Step 3: Replace only the initial users block and add its parents/child.**

After `CREATE SCHEMA IF NOT EXISTS operational`, use:

```sql
CREATE TABLE operational.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL CHECK (username <> '' AND username !~ '(^[[:space:]])|([[:space:]]$)'),
    password_hash TEXT NOT NULL CHECK (password_hash ~ '[^[:space:]]'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX accounts_username_lower_key
    ON operational.accounts (lower(username));

CREATE TABLE operational.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL UNIQUE REFERENCES operational.accounts (id),
    first_name TEXT NOT NULL CHECK (first_name <> '' AND first_name !~ '(^[[:space:]])|([[:space:]]$)'),
    last_name TEXT NOT NULL CHECK (last_name <> '' AND last_name !~ '(^[[:space:]])|([[:space:]]$)'),
    email TEXT NOT NULL CHECK (email <> '' AND email !~ '(^[[:space:]])|([[:space:]]$)'),
    phone_number TEXT NOT NULL CHECK (phone_number <> '' AND phone_number !~ '(^[[:space:]])|([[:space:]]$)'),
    country_of_residence TEXT NOT NULL CHECK (country_of_residence <> '' AND country_of_residence !~ '(^[[:space:]])|([[:space:]]$)'),
    timezone TEXT CHECK (timezone <> '' AND timezone !~ '(^[[:space:]])|([[:space:]]$)'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.professional_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES operational.users (id),
    headline TEXT CHECK (headline <> '' AND headline !~ '(^[[:space:]])|([[:space:]]$)'),
    professional_summary TEXT CHECK (professional_summary <> '' AND professional_summary !~ '(^[[:space:]])|([[:space:]]$)'),
    skills JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(skills) = 'array'
        AND NOT jsonb_path_exists(skills, '$[*] ? (@.type() != "object")')
    ),
    experience JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(experience) = 'array'
        AND NOT jsonb_path_exists(experience, '$[*] ? (@.type() != "object")')
    ),
    previous_projects JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(previous_projects) = 'array'
        AND NOT jsonb_path_exists(previous_projects, '$[*] ? (@.type() != "object")')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Update the obsolete file header to cite KAN-71/ADR-0011 and separate
management-owned data from matching-owned tables. Keep everything from
`CREATE TABLE operational.employee` onward unchanged.

- [ ] **Step 4: Rerun the exact live command and review.**

Expected: all matrix cases pass against Postgres 16, zero skips. Also run:

```bash
rtk uv run ruff check tests/management
rtk uv run ruff format --check tests/management
rtk proxy git diff --check
```

Report live test counts and constraint evidence. No provisioning function or
owner CLI. Commit Task 2, report its SHA, complete independent task review,
then proceed to Task 3.

## Task 3: Add Isolated Configuration And Read-Only Readiness

**Files:** Create `src/huginn/management/config.py`,
`src/huginn/management/ports.py`, `src/huginn/management/database.py`,
`tests/management/test_config.py`, `tests/management/test_database.py`, and
`tests/management/test_database_integration.py`.

**Interfaces:** Produce ManagementConfig, load_config, ReadinessPort and
PostgresReadiness with the exact Runtime Contract signatures. Consume Task
2's DDL and both database fixtures. Do not edit Task 2 files or shared config.

- [ ] **Step 1: Write config/adapter tests and observe RED.**

1. `load_config` reads only the management variable, rejects missing/empty/
   whitespace values even when the ELT URL is set, and never prints/reprs a
   credential-bearing URL. Disable dotenv in unit tests using monkeypatch.
2. Patch `database.psycopg.connect` with a small context-manager fake to
   assert constructors do not connect, checks close connections on success
   and failure, connect/statement timeouts are passed, and the transaction
   is read-only. Mock only the external database boundary.
3. psycopg connection/query failures return false; caplog contains one
   sanitized warning, no exception text or DSN. A deliberate TypeError
   propagates instead of being reported as an unavailable database.
4. Live full-bootstrap fixture reports ready. Empty fixture reports false.
   In one empty-fixture test, apply the same ordered six files, assert ready,
   rename `operational.users.email` to `legacy_email` and commit, then assert
   false. This disposable-container mutation tests old/missing columns and
   cannot touch the session fixture or development database.

```python
def test_ready_requires_bootstrapped_tables(
    management_database_url, empty_management_database_url
):
    assert PostgresReadiness(management_database_url).is_ready() is True
    assert PostgresReadiness(empty_management_database_url).is_ready() is False
```

```bash
rtk uv run --python 3.14 pytest tests/management/test_config.py tests/management/test_database.py -v
rtk proxy env -u HUGINN_DATABASE_URL PYTHON_DOTENV_DISABLED=1 uv run --python 3.14 pytest tests/management/test_database_integration.py -v -ra
```

Expected RED: missing symbols, then targeted failures for error handling and
schema probes. Write ReadinessPort before its concrete implementation.

- [ ] **Step 2: Implement config and the minimal adapter.**

```python
# config.py
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class ManagementConfig:
    database_url: str = field(repr=False)


def load_config() -> ManagementConfig:
    load_dotenv()
    value = os.environ.get("HUGINN_MANAGEMENT_DATABASE_URL")
    if not value or not value.strip():
        raise RuntimeError("HUGINN_MANAGEMENT_DATABASE_URL is not set")
    return ManagementConfig(database_url=value)
```

```python
# ports.py
from typing import Protocol


class ReadinessPort(Protocol):
    def is_ready(self) -> bool: ...
```

```python
# database.py, query contract
_PROBES = (
    "SELECT 1",
    "SELECT id, username, password_hash, status, created_at, updated_at "
    "FROM operational.accounts LIMIT 0",
    "SELECT id, account_id, first_name, last_name, email, phone_number, "
    "country_of_residence, timezone, created_at, updated_at "
    "FROM operational.users LIMIT 0",
    "SELECT id, user_id, headline, professional_summary, skills, experience, "
    "previous_projects, created_at, updated_at "
    "FROM operational.professional_profiles LIMIT 0",
)


class PostgresReadiness:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def is_ready(self) -> bool:
        try:
            with psycopg.connect(
                self._database_url, connect_timeout=2,
                options="-c statement_timeout=2000 -c default_transaction_read_only=on",
            ) as conn:
                for query in _PROBES:
                    conn.execute(query)
            return True
        except psycopg.Error as exc:
            logger.warning("Management readiness failed: %s", type(exc).__name__)
            return False
```

Add psycopg/logging imports and `logger = logging.getLogger(__name__)`;
no logging configuration in these modules. Do not log `exc` or use
`exc_info=True` here. Add concise citing docstrings.

- [ ] **Step 3: Rerun both commands and focused Ruff.**

```bash
rtk uv run ruff check src/huginn/management tests/management
rtk uv run ruff format --check src/huginn/management tests/management
```

Expected: unit and live tests pass, no live skips, connections closed.
Commit Task 3, report its SHA, complete independent task review, then proceed
to Task 4.

## Task 4: Expose Only Health And Readiness

**Files:** Create `src/huginn/management/app.py`,
`src/huginn/management/__main__.py`, `tests/management/test_app.py`,
`tests/management/test_main.py`, and
`tests/management/test_app_integration.py`.

**Interfaces:** Consume Task 3's ManagementConfig, load_config, ReadinessPort,
PostgresReadiness. Produce create_app with the Runtime Contract signature and
the module entrypoint. Do not alter package initializer or dependency files.

- [ ] **Step 1: Write HTTP/entrypoint tests and observe RED.**

```python
class FakeReadiness:
    def __init__(self, ready: bool):
        self.ready = ready
        self.calls = 0

    def is_ready(self) -> bool:
        self.calls += 1
        return self.ready


def test_health_does_not_probe_the_database():
    probe = FakeReadiness(False)
    app = create_app(ManagementConfig("unused"), readiness=probe)
    assert probe.calls == 0
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert response.mimetype == "application/json"
    assert probe.calls == 0
```

1. Parametrize readiness true/false: exact body/status, one probe per GET.
2. Factory has no database side effects; two factories have independent
   injected probes. Missing config raises without starting the server.
3. Assert only the two application paths are registered, POST gives 405,
   downstream routes give 404, and health/readiness set no session cookie.
4. Entry test monkeypatches module-local create_app and logging.basicConfig;
   `main()` calls run with host 127.0.0.1, port 8000, debug=False and
   use_reloader=False. It must not open a real socket in the test.
5. Live HTTP test uses the bootstrapped container: health/ready both 200.
   Empty container: health 200, ready 503; catalog still has no operational
   schema after constructing the app and calling both routes.
6. In the bootstrapped container insert and commit one UUID-named synthetic
   Account. Construct the app twice and call both routes; assert that exact
   row and its timestamps remain unchanged. Delete only that test row in
   `finally`. This proves startup/readiness do not reset persisted data.
   Creating Account alone here is test setup, not a provisioning feature.

```bash
rtk uv run --python 3.14 pytest tests/management/test_app.py tests/management/test_main.py -v
rtk proxy env -u HUGINN_DATABASE_URL PYTHON_DOTENV_DISABLED=1 uv run --python 3.14 pytest tests/management/test_app_integration.py -v -ra
```

- [ ] **Step 2: Implement the factory and local entrypoint.**

```python
# app.py
from flask import Flask, jsonify

from huginn.management.config import ManagementConfig, load_config
from huginn.management.database import PostgresReadiness
from huginn.management.ports import ReadinessPort


def create_app(
    config: ManagementConfig | None = None, *, readiness: ReadinessPort | None = None
) -> Flask:
    resolved_config = config if config is not None else load_config()
    probe = readiness if readiness is not None else PostgresReadiness(
        resolved_config.database_url
    )
    app = Flask(__name__, static_folder=None)

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    @app.get("/ready")
    def ready():
        if probe.is_ready():
            return jsonify(status="ready"), 200
        return jsonify(status="not_ready"), 503

    return app
```

```python
# __main__.py
import logging

from huginn.management.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    app = create_app()
    logger.info("Starting management development server on 127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
```

Add citing docstrings and return annotations consistent with Flask types.
No request DTOs, repository CRUD stubs, blueprint hierarchy, CORS extension,
authentication hooks or automatic schema application.

- [ ] **Step 3: Rerun both test commands and focused Ruff.**

```bash
rtk uv run ruff check src/huginn/management tests/management
rtk uv run ruff format --check src/huginn/management tests/management
```

Expected: no unit or integration failures/skips. Commit Task 4, report its SHA,
complete independent task review, then proceed to Task 5.

## Task 5: Document Bootstrap, Verify The Foundation And Hand Off

**Files:** Modify `README.md`, `.env.example`, `db/schema/README.md`,
`docs/architecture.md`, and `docs/entities.md`. Create
`docs/management-foundation.md`. No production/test/SQL changes owned here;
return defects to their owning task before rerunning affected checks.

**Interfaces:** Consume the schema, models and app already reviewed. Produce
an accurate local runbook and explicit KAN-72 dependency contract. Keep all
documentation edits restricted to management facts; do not rewrite the ELT
architecture or change legacy matching behavior.

- [ ] **Step 1: Document the implemented contract.**

1. Add `.env.example` management URL
   `HUGINN_MANAGEMENT_DATABASE_URL=postgresql://localhost:5432/huginn_management`.
   Leave the existing ELT variable and secrets examples unchanged.
2. `docs/entities.md`: add Account/User/ProfessionalProfile operational
   definitions, refer to the structured collection contract, and identify
   ownership keys. Existing Match.UserId remains User, not Account.
3. `docs/architecture.md`: update the obsolete User ICP diagram and the
   management/auth non-goal text narrowly. Explain KAN-71's foundation and
   KAN-72/73's deferred behavior, independent of the ELT pipeline. Keep the
   shared production database model and clarify development isolation.
4. `docs/management-foundation.md`: record all selected representations,
   validation boundaries, exactly-one enforcement split, auth handoff,
   deferred tables and API paths. Persist enough of the root-only domain
   decisions here that another clone does not require absolute local notes.
   Link ADR-0011, the original authority paths, and ticket identifiers;
   do not claim the live Jira ticket was checked.
5. `README.md` links the runbook and the module entrypoint.
   `db/schema/README.md` distinguishes bootstrap from migration, documents
   the complete six-file order and failure-on-SQL-error invocation below.

- [ ] **Step 2: Include these exact local operation commands.**

The database must be new, dedicated and disposable. The following are
operator-run examples, not startup behavior or permission to delete a
database. If `huginn_management` already exists with an old schema, choose
a new dedicated name or request an explicitly scoped rebuild; this plan
does not run `dropdb` or reset any existing data.

```bash
rtk proxy createdb huginn_management
export HUGINN_MANAGEMENT_DATABASE_URL='postgresql://localhost:5432/huginn_management'
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
rtk uv run --python 3.14 python -m huginn.management
```

`export` is a shell builtin, not an external command to wrap with rtk.
Run from the worktree in separate terminals for server and requests:

```bash
rtk proxy curl --fail-with-body http://127.0.0.1:8000/health
rtk proxy curl --fail-with-body http://127.0.0.1:8000/ready
```

If port 8000 is occupied, use:

```bash
rtk uv run --python 3.14 flask --app huginn.management.app:create_app run --host 127.0.0.1 --port 8001 --no-debugger --no-reload
```

State that this is a local development server. Only run a manual server
smoke test against an explicitly selected dedicated database; automated
test-client and live-container tests are the required portable evidence.

- [ ] **Step 3: Run final gates on the reviewed code.**

Unset the external ELT URL and disable dotenv for tests so root conftest
starts its own disposable container rather than touching a developer's ELT
database. Management fixtures always use their own Postgres 16 containers.
Docker availability and pulling the image are prerequisites.

```bash
rtk uv sync --python 3.14 --locked
rtk uv run --python 3.14 python --version
rtk proxy env -u HUGINN_DATABASE_URL PYTHON_DOTENV_DISABLED=1 uv run --python 3.14 pytest tests/management -v -ra
rtk uv run --python 3.14 python -m compileall -q src tests
rtk uv run ruff check .
rtk uv run ruff format --check .
rtk proxy env -u HUGINN_DATABASE_URL PYTHON_DOTENV_DISABLED=1 uv run --python 3.14 pytest -ra
rtk proxy git diff --check origin/master...HEAD
rtk proxy git diff --cached --check
rtk proxy git diff --check
rtk proxy git status --short
```

This is the full `uv run pytest` gate with explicit interpreter and test
database isolation. Record totals and every skip reason. All management
integration tests must execute; any unavailable Docker/Postgres result
leaves the foundation unverified. Investigate existing-suite failures
without silently changing unrelated ELT code. Check whitespace for newly
created files through the saved review diffs as well as tracked git diff.

- [ ] **Step 4: Review and provide the KAN-72 handoff.**

1. Commit Task 5 and report its SHA, then run independent final spec/code review
   of committed `origin/master...HEAD` and the available local pre-MR process
   as described in Execution And Review Protocol. Include all branch files in
   the review package. State missing review tooling explicitly.
2. KAN-72 consumes `operational.accounts`, `operational.users`,
   `operational.professional_profiles`, ManagementConfig and the collection
   schemas. It must implement one transaction creating Account, User and an
   empty profile, password hashing, owner-only CLI provisioning, same-index
   username conflict handling, and rollback tests proving no partial identity.
3. KAN-72 must finalize personal input validation before accepting owner
   input, while honoring the storage contract. It must not assume the
   database itself enforces mandatory children or normalizes usernames.
   KAN-73 subsequently implements session storage and ownership enforcement.
4. Report the implemented task list, exact gate results, unresolved concerns,
   no Jira sync, and every task commit SHA. Preserve unrelated user changes.
   After all local gates and reviews, the controller owns any push and PR
   creation; nobody merges.

**Explicitly out of scope:** provisioning implementation/CLI (KAN-72),
password hashing implementation and login/session/auth behavior (KAN-73,
with hashing owned by KAN-72), User/Profile CRUD (KAN-74), offering CRUD
(KAN-75), ICP CRUD/schema/matching semantics (KAN-76), strategy CRUD and
reference rules (KAN-77), MVP end-to-end business workflow (KAN-78), all UI
(KAN-79/80), BuyerPersona/EngagementPreferences workflows, resume/ATS parsing,
education/certifications/languages/portfolio collections, matching/scoring
(KAN-18), migration tooling/backfills/legacy-data conversion (KAN-49),
production deployment and changes to the ingestion pipeline.
