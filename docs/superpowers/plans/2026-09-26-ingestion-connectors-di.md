# Ingestion connectors: extract Firebase and Algolia behind injected classes

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` to implement this plan task-by-task. Write the failing test first, watch it fail, then write the minimum code to pass it.

**Goal:** Move the Firebase and Algolia clients out of the per-source adapter
modules and into a new `src/huginn/elt/ingestion/connectors/` package, one
class each, and have the adapters receive them by constructor injection instead
of calling module-level functions that reach `requests` directly. No behavior
change: same requests, same parsing, same records, same logs.

**Architecture:** Two new modules,
`src/huginn/elt/ingestion/connectors/firebase.py` (`FirebaseConnector`) and
`src/huginn/elt/ingestion/connectors/algolia.py` (`AlgoliaConnector`). Both are
stateless. `HackerNewsAdapter` and `YcDirectoryAdapter` each gain one required
constructor argument, their connector, and `build_service` in
`src/huginn/elt/ingestion/__main__.py` becomes the composition root that
constructs the concrete instances. `Config` in `src/huginn/config.py` gains
`yc_algolia_api_key`, so the Algolia key is read in one place instead of inside
`yc.py`.

**Tech Stack:** Python 3.14, `requests` (already a dependency),
`concurrent.futures.ThreadPoolExecutor` (ADR-0003), pytest with hand-rolled fake
doubles. No mocking framework, no fixture framework, matching the existing
style in `tests/elt/ingestion/`.

**Spec:** No Jira ticket exists for this work. That is a known gap: all eight
earlier artifacts in this directory cite one. The shape decision recorded in
"Locked decisions" below is ADR-shaped, since `AlgoliaConnector` is not the
generic Algolia client its name suggests, and if that is to be recorded rather
than merely obeyed, it wants a ticket or an ADR before implementation closes.

**Review outcome:** this plan was reviewed on two independent axes after the code
was written, and both found real defects. Everything they identified is fixed
here and in the code, and the two claims they showed to be false, the
no-behavior-change claim and the `os.environ` sweep claim, are corrected in
place rather than quietly dropped. See Global Constraint 9 for the one
deliberate behavior change that survived.

## Locked decisions

1. **`AlgoliaConnector` holds every Algolia call, as methods.** `query`,
   `discover_batches`, `fetch_batch`, `total_hit_count`. Not a generic wire
   client with the batch logic left in the adapter. Chosen so the class and the
   adapter are each one file to read.
2. **The name is honest about scope, in the docstring only.** `discover_batches`
   and `fetch_batch` are welded to YC's `batch` facet, so the class is
   "Algolia, YC-shaped" despite the generic-looking name. Stated plainly in the
   module and class docstrings so no later reader takes the name as a promise it
   does not keep. The wire half (headers, POST, `raise_for_status`, JSON parse,
   URL construction) is genuinely generic and intact.
3. **The key comes from `Config`,** not from `os.environ` inside `yc.py`. This
   honours `config.py`'s own docstring calling itself the abstraction boundary,
   and puts the "required env var missing" error beside the identical
   `HUGINN_DATABASE_URL` error that is already there.
4. **No `typing.Protocol` for the connectors.** `ports.py` reserves Protocols
   for what the core depends on; these are leaf I/O the adapters consume, and
   pyright adoption is still deferred per `CLAUDE.md`. A hand-rolled fake
   satisfies the shape without one.
5. **OpenCorporates is out of scope.** Its docstring at
   `src/huginn/elt/ingestion/adapters/opencorporates.py:45` cross-references
   `yc.py`'s `_algolia_api_key` and goes stale in phase 1. Deliberately left
   alone, to be handled when OpenCorporates is dealt with separately.
6. **Algolia before Firebase,** in two phases, because the Firebase API is
   unauthenticated and so needs no `Config` change, making the phases
   independent.

## Global Constraints

1. **The connectors are called concurrently on a single shared instance.** Under
   ADR-0003 each adapter drives a `ThreadPoolExecutor` with 8 workers, so after
   this change the calls become `executor.map(self._connector.fetch_batch,
   batches)` and `executor.map(self._connector.get_item, kid_ids)`. One instance,
   eight threads. **Both connectors must therefore stay stateless and must keep
   using module-level `requests.get`/`requests.post`.** Do not give either class
   a `requests.Session`: `Session` is explicitly documented as not thread-safe,
   so it would be a latent bug that only appears under concurrency, and today's
   code avoids it only because every call builds its own. Each connector's
   docstring records this, citing ADR-0003 for the concurrency. Note that
   ADR-0003 is itself silent on connection state and shared-instance safety, so
   there is no existing decision to lean on here; if the rule should be recorded
   rather than merely obeyed, that is a separate ADR question this plan does not
   answer.
2. **TDD is mandatory** (`CLAUDE.md` code standard 5). Failing test first, watch
   it fail, minimal code to pass. For this refactor the moved tests are the
   failing tests: a test importing `connectors.algolia` fails with
   `ModuleNotFoundError` before the module exists, which is the correct red.
3. **No behavior change to the request path.** Same URLs, same request bodies,
   same headers, same timeouts, same error types, same log records, same
   `RawRecord` values. This is a relocation plus a wiring change, not a
   redesign. One deliberate exception, recorded as Global Constraint 9: the
   Algolia key is now read eagerly at startup rather than per request, which
   moves where a missing key fails.
4. **Docstrings cite, they do not restate** (`CLAUDE.md` code standard 3). Point
   at `docs/architecture.md` by section, or the ADR or Jira ticket that settled
   the rationale. Docstrings move with their code, keeping their existing
   fetch-plan citations. This constraint was written as "neither fetch plan
   names any constant being moved, so every existing citation stays valid", and
   that turned out to be true of constants while missing two citations that
   review caught: `architecture-notes/yc-fetch-plan.md:39` named
   `_discover_batches()` as living in the adapter, and its line 13 quoted the
   section 5 diagram label that this change replaced. Both were updated to point
   at the connector. The general rule stands: a fetch plan is a live document
   and has to be re-checked for moved symbols, not assumed safe because the
   symbol it named was a function rather than a constant.
5. **No em dashes** in any new prose, in code or in docs.
6. **No `asyncio`,** bounded `ThreadPoolExecutor` only (ADR-0003). Unchanged.
7. **Logging** per ADR-0005. The existing YC INFO and WARNING records in
   `fetch()` are preserved exactly, including the mismatch reconciliation.
8. **No ADR and no ticket are created by this plan.** Noted as a gap above.
9. **The Algolia key's failure point moves, and that is a real behavior
   change.** Recorded here because the original claim of none was wrong and
   both review passes caught it independently. Before, `yc.py` read
   `os.environ` per request inside `_algolia_api_key()`, so a missing key
   raised during `YcDirectoryAdapter.fetch()`, was caught by the per-source
   `except Exception` in `service.py:69`, was logged through `logger.exception`,
   and left a FAILED `job_runs` row while HN and OpenCorporates still fetched.
   Now `load_config()` reads it at startup and raises before `build_service()`
   runs, so the process exits with no job_runs row and no log record. Fail-fast
   on misconfiguration is the better default, it follows unavoidably from the
   approved decision to source the key from `Config`, and the user confirmed
   that reading on review, so it is kept rather than reverted. It also makes the
   key behave like `HUGINN_DATABASE_URL`, which has always failed the same way,
   so the two required variables now fail consistently instead of one failing
   loudly at startup and the other mid-run. What is lost is the observability: a
   misconfigured key is invisible in `job_runs`, which is tech debt for Jira
   KAN-16. Phase 3 narrows that loss, logging the failure in `main()` so it lands
   as a record instead of a bare traceback, but cannot close it, since a missing
   variable means no service and therefore no `job_runs` writer.

## Phase 1: Algolia

### Task 1: `Config` carries the YC Algolia key

`src/huginn/config.py`: add `yc_algolia_api_key: str` to the frozen
`Config` dataclass, and add a module-level `_require_env(name, guidance="")`
helper. `load_config()` calls it for both `HUGINN_DATABASE_URL` and
`HUGINN_YC_ALGOLIA_API_KEY`.

The helper exists so the two variables raise the same way without losing the
Algolia message's extra guidance, which names the secured-key blob to paste:

```python
def _require_env(name: str, guidance: str = "") -> str:
    value = os.environ.get(name)
    if not value:
        suffix = f" {guidance}" if guidance else ""
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env.{suffix}")
    return value
```

The `f"{ALGOLIA_API_KEY_ENV_VAR} is not set. Copy .env.example to .env and fill
in YC's current Algolia secured-key blob." message currently lives in
`yc.py:52-55`. Its substance moves to the `load_config()` call site as the
`guidance` argument; the variable name it named moves out of `yc.py` entirely,
which is the point.

Tests, in a new `tests/test_config.py`:
1. `load_config` returns both values when both variables are set.
2. It raises naming `HUGINN_DATABASE_URL` when only that is missing.
3. It raises naming `HUGINN_YC_ALGOLIA_API_KEY` when the key is unset.
4. It raises naming `HUGINN_YC_ALGOLIA_API_KEY` when the key is empty.

Cases 3 and 4 relocate the intent of `test_algolia_api_key_raises_when_unset`,
`test_algolia_api_key_raises_when_empty`, and
`test_algolia_query_raises_when_api_key_missing` from `test_yc.py`, so the
"missing key fails loudly" guarantee is preserved at its new home rather than
dropped.

Then update the 5 `Config(database_url=...)` sites in
`tests/elt/ingestion/test_main.py` (lines 47, 71, 101, 129, 142) to pass
`yc_algolia_api_key`.

#### Collision with the database isolation guard, and how it is resolved

This task was originally specified without noticing that a new
`tests/test_config.py` trips
`test_no_test_module_derives_its_connection_from_the_environment`. Recording the
resolution here because the constraint is invisible from the task text alone.

The guard is a text grep forbidding the string `HUGINN_DATABASE_URL` in any
module under `tests/` except itself, deliberately absolute because an earlier,
looser version of it was caught being vacuous. But `load_config()` reads the
database variable before the Algolia key, so testing either branch requires
setting and asserting on both names. There is no way to test `load_config()`
without naming the database variable, so the two requirements genuinely
conflict and something has to give.

Resolution: the guard gains an `_ALLOWED_FILES` frozenset naming
`test_config.py`, and the exemption is bounded rather than bare. A third test,
`test_allowlisted_files_still_cannot_reach_a_database`, asserts no allowlisted
file names `psycopg`, `testcontainers`, or `integration_database_url`, which
between them are the only routes to a connection available. That closes the
exemption's weakness, which is that a text grep cannot see intent and would
exempt a file that later grew a connection. `_ALLOWED_FILES` is held to one
file on purpose; widening it is a decision to review, not a convenience.

Data safety is unaffected by this choice and was verified rather than assumed:
`test_the_suite_database_was_provisioned_by_this_suite` passes, so the
integration suite is running against a testcontainer database it provisioned
itself and not the developer's. Every connection-shaped literal under `tests/`
uses `example.invalid`, which RFC 6761 reserves so it cannot resolve,
`test_config.py` included, since it was switched to `example.invalid` during
review precisely so the file the guard now exempts holds no exception to that
rule.

The bounding test narrows the exemption but does not close it, and the earlier
draft of this plan overstated that by saying it closed the weakness. It greps
for `psycopg`, `testcontainers`, and `integration_database_url`; a file that
reached a database by some other import, such as
`huginn.ops.postgres_job_run_writer`, would still pass it.

The residual gap the guard does not cover, recorded so it is not forgotten: a
test that hardcoded a real database URL as a bare literal, with no variable name,
would pass the grep, and the stamp test would not notice because it checks the
suite's own database rather than what other tests connect to.

### Task 2: `connectors/algolia.py`

New module. `AlgoliaConnector`:

```python
ALGOLIA_MAX_HITS_PER_QUERY = 1000

class AlgoliaConnector:
    def __init__(self, app_id: str, index: str, api_key: str, timeout: float = 10.0) -> None
    def query(self, body: dict) -> dict
    def discover_batches(self) -> list[str]
    def fetch_batch(self, batch: str) -> list[dict]
    def total_hit_count(self) -> int
```

All four methods move from `yc.py` with their bodies and docstrings unchanged
apart from the additions below. The `ycdc_public` warning moves onto the
constructor, because it describes the secured key, not the query strategy:

> Never pass `tagFilters` in a `body`: the `ycdc_public` restriction is already
> signed into the secured key. See `architecture-notes/yc-fetch-plan.md`
> section 2.

`ALGOLIA_APP_ID`, `ALGOLIA_INDEX`, `ALGOLIA_QUERY_URL`, and
`ALGOLIA_API_KEY_ENV_VAR` all leave `yc.py`. `app_id` and `index` become
constructor parameters, because Algolia has many indexes and that is genuinely
per-consumer configuration, unlike Firebase's single public REST endpoint. The
query URL is derived from `app_id` and `index` inside the connector.

`ALGOLIA_MAX_HITS_PER_QUERY` moves here with its existing comment, since
`fetch_batch` now lives here.

Tests, in a new `tests/elt/ingestion/connectors/test_algolia.py`, 10 cases, all
retargeted from `test_yc.py` at methods rather than module functions:
`query` posts the expected URL, headers, and body; `query` raises on non-2xx;
`discover_batches` requests the `batch` facet with zero hits; `discover_batches`
returns facet keys; `discover_batches` returns an empty list when there are no
facet values; `fetch_batch` requests the filtered query; `fetch_batch` handles a
batch value containing an apostrophe; `fetch_batch` returns the raw hits list;
`fetch_batch` returns an empty list when there are no hits; `total_hit_count`
requests zero hits and returns `nbHits`.

### Task 3: `adapters/yc.py` takes an injected connector

`YcDirectoryAdapter.__init__(self, algolia: AlgoliaConnector)`. The adapter
keeps `YC_ALGOLIA_APP_ID` and `YC_ALGOLIA_INDEX` as its own identity constants,
since which index to query is YC's fact, not the connector's. It keeps
`MAX_CONCURRENT_FETCHES = 8`, because the adapter drives the pool. It keeps the
fetch-time reconciliation against `total_hit_count` and the WARNING it logs on
mismatch, verbatim.

`fetch()` reduces to: discover batches, `executor.map(self._algolia.fetch_batch,
batches)`, build `RawRecord`s, reconcile, log, return. `_discover_batches`,
`_fetch_batch`, and `_total_hit_count` are deleted from `yc.py`, having become
connector methods. `import os` and `import requests` both go.

`test_yc.py` settles at 9 tests: the two `ApiSourcePort`/attribute tests, and
the 7 `fetch()` tests. The `fetch()` tests that stub all three policy methods
now pass a fake connector that raises if called, which is a stronger assertion
than the stub alone, since it proves the connector is unused when policy is
stubbed.

### Task 4: `build_service` injects it

`src/huginn/elt/ingestion/__main__.py`:

```python
YcDirectoryAdapter(
    algolia=AlgoliaConnector(
        app_id=yc.YC_ALGOLIA_APP_ID,
        index=yc.YC_ALGOLIA_INDEX,
        api_key=config.yc_algolia_api_key,
    )
),
```

Its existing property is preserved: constructible without a live database or
network call (`CLAUDE.md` code standard 4). One new test asserts the adapter
holds a real `AlgoliaConnector` with the configured key.

## Phase 2: Firebase

### Task 5: `connectors/firebase.py`

New module. `FirebaseConnector`:

```python
FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"

class FirebaseConnector:
    def __init__(self, timeout: float = 10.0) -> None
    def get_user(self, user_id: str) -> dict | None
    def get_item(self, item_id: int) -> dict | None
    def _get_json(self, path: str) -> dict | None
```

`FIREBASE_BASE_URL` stays a module constant here rather than becoming a
parameter, because the public Firebase REST API has exactly one address: it is a
property of the service, not per-consumer configuration. That is a real
asymmetry with Algolia's many indexes, not an inconsistency in the design.

`get_user` and `get_item` own the `user/{id}.json` and `item/{id}.json` URL
shapes, so the adapter no longer builds URL strings. `hn._fetch_item` is deleted,
its docstring and its `architecture-notes/hn-fetch-plan.md` section 2 citation
moving onto `get_item`, including the rule that a bare `null` returns `None`
while a `deleted: true` stub is returned as-is.

Tests, in a new `tests/elt/ingestion/connectors/test_firebase.py`, 7 cases: 4
relocated and 3 new. The relocation is 5 original `test_hn.py` tests collapsing
into 4, because `test_get_json_returns_none_for_bare_null_body` and
`test_fetch_item_returns_none_for_bare_null` test the same observable behaviour
once the transport is behind `get_item` and merged into one. This plan first
described 2 of them as new tests, which was wrong; they already existed. The 3
new ones exist because URL construction moved from the adapter into the
connector and was never asserted before: one pins the exact item URL and the
timeout as a literal rather than as the module constant, so that changing the
constant fails the test, one pins the user URL, one covers a bare-null user
profile.

`test_hn.py` keeps 13: the `ApiSourcePort` and attribute tests, the 5
`_discover_thread_item` tests, and the 6 `fetch()` tests. `_discover_thread_item`
becomes a method rather than a module function, since it needs the connector,
and its 5 tests construct the adapter to call it. Every
`monkeypatch.setattr(hn, "_get_json", ...)` is replaced by a fake connector
keyed by full URL, so `FIREBASE_FIXTURES` stays byte-identical to before the
extraction.

### Task 6: `adapters/hn.py` takes an injected connector

`HackerNewsAdapter.__init__(self, firebase: FirebaseConnector)`. Keeps
`WHOISHIRING_USER`, `THREAD_TITLE_PATTERN`, and `MAX_CONCURRENT_FETCHES = 8`.
Keeps the `submitted[0]`-plus-title-check discovery policy, with the docstring
recording that there is no Algolia cross-check. Drops `import requests`,
`FIREBASE_BASE_URL`, `_get_json`, and `_fetch_item`.

### Task 7: wiring, package docstring, architecture doc

`build_service` injects `FirebaseConnector()`.

`connectors/__init__.py` gets a one-line docstring distinguishing it from
`adapters/`, whose existing docstring ("Per-source adapters. One adapter per
source, implementing `SourcePort`") stays true precisely because the connectors
are not in that package. `tests/elt/ingestion/connectors/` gets an
`__init__.py`, since every other test package directory under `tests/` has one.

`docs/architecture.md` section 5 gains the connectors layer in the diagram, a
paragraph on why an adapter and its connector are separate objects, and a
correction to the sentence saying the adapter queries Algolia "directly", which
is no longer accurate now that a connector does. Done in phase 2, when the
package is complete.

## Phase 3: startup config failure logging

Phase 3 exists because Global Constraint 9 was ratified with its observability
cost still open, and the cost turned out to be cheaper to close than to defer.

### Task 8: `main()` logs a config failure instead of raising

Adding the Algolia key to `Config` made a missing key abort the process before
any service was built, so it produced no log record at all: an unhandled
traceback on stderr, exit 1, nothing in `job_runs`, nothing for an aggregator
reading stdout. Verified by running the real entrypoint rather than reasoning
about it, and the first attempt at that check was itself wrong, because the
shell wrapper merges stdout and stderr and made the traceback look like stdout.
The measurement has to go through the venv python directly.

The fix belongs in `main()` and not in `config.py`, per ADR-0005: the
entrypoint is application code and owns logging, `config.py` is library code
and only raises, and a `logger.error` there would both double-report against
the exception and put a logging concern in the wrong layer.

```python
try:
    config = load_config()
except RuntimeError as error:
    logger.error("%s", error)
    sys.exit(1)
```

The handler catches `RuntimeError` only, which is what `_require_env` raises.
Anything else `load_config` raises is a defect and must keep propagating,
otherwise a later widening of the handler would quietly turn a crash into a
clean exit 1, which is the opposite of what this task is for. A test pins that.

Result, measured on the real entrypoint with the key blank: stderr goes from a
1143-byte traceback to one 151-byte line
`__main__ ERROR HUGINN_YC_ALGOLIA_API_KEY is not set. Copy .env.example to .env.`
Exit code stays 1, so cron alerting is unaffected. The same now holds for
`HUGINN_DATABASE_URL`, which has always failed this way and finally does so
through the same path as the new variable.

`job_runs` still records nothing, and that gap is unchanged and still real: no
service means no writer, and there is no database to write to anyway. What
changed is that the failure is now a log record rather than a bare traceback,
so the observability cost named in Global Constraint 9 is narrowed rather than
removed. The remainder stays tech debt for Jira KAN-16.

## Verification

1. `uv run pytest` green, at 352 after all three phases, up from a 344
   baseline. The
   movement: 4 config tests, 10 Algolia connector tests, 7 Firebase connector
   tests, 2 wiring tests, 1 new bounding test, 1 new HN attribute test, and 2
   new `main()` config-failure tests from phase 3, less the 14 YC and 5 HN tests
   that moved into the connector suites.
2. `uv run ruff check .` and `uv run ruff format --check .` clean.
3. No AST-equivalence claim. The adapters' bodies genuinely change from
   module-function calls to injected-method calls, so unlike the 2026-09-25 docs
   commit there is no identical-AST evidence to offer. The honest evidence is
   that every pre-existing assertion still passes with only the seam re-plumbed,
   and that the request bodies, URLs, headers, and timeouts are asserted
   unchanged in the moved tests. The timeouts are pinned as literals rather than
   as the module constants, because a test that asserts against the constant
   passes unchanged when the constant changes and so proves nothing.
4. A sweep confirming no module under `src/huginn/elt/ingestion/` reads
   `os.environ` for the Algolia key, the static analogue of the invariant
   `tests/test_integration_database_isolation.py` already asserts for the
   database. Scoped to the key rather than to `os.environ` outright, because
   `adapters/opencorporates.py:51` still reads its own token from the
   environment. That module is out of scope here, and it is the one remaining
   place the pattern survives, so the broader version of this check cannot pass
   yet. Closing it is the natural next ticket if the invariant is ever meant to
   hold across the whole package.
