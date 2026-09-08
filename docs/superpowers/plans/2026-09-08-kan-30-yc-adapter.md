# KAN-30: YC Adapter `fetch()` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `YcDirectoryAdapter.fetch()` so it discovers YC's current
`batch` facet values and returns one `RawRecord` per company hit, querying
YC's public search-only Algolia key directly, exactly per the fully-resolved
KAN-39 (`architecture-notes/yc-fetch-plan.md`) fetch plan.

**Architecture:** Four stateless, module-level helper functions in
`src/huginn/ingestion/adapters/yc.py` (`_algolia_api_key`, `_algolia_query`,
`_discover_batches`, `_fetch_batch`), layered under
`YcDirectoryAdapter.fetch()`, which fans per-batch queries out through a
bounded `concurrent.futures.ThreadPoolExecutor`, mirroring KAN-29's HN
adapter shape. No new dependency: `requests` (already a dependency) for
HTTP, stdlib `concurrent.futures` for bounded concurrency, stdlib `logging`
per ADR-0005 (unlike KAN-29, which predates that ADR and carries its
retrofit as tracked debt, KAN-30 must ship with logging from its first
commit).

**Tech Stack:** Python 3.14, `requests`, stdlib `concurrent.futures.ThreadPoolExecutor`,
`logging`, `time`, `os`, pytest with its built-in `monkeypatch` fixture (no
added mocking library).

**Spec:** `architecture-notes/yc-fetch-plan.md` (KAN-39, the binding
fetch-plan decisions, including its "Confirmed by a live test call
(2026-09-08)" section), `docs/sources/yc-directory.md` (underlying API
research), `src/huginn/ingestion/ports.py` (`RawRecord`, `ApiSourcePort`
this adapter implements), `CLAUDE.md` and `BEST_PRACTICES.md` (project
conventions), `adr/0003-thread-pool-for-adapter-concurrency.md`,
`adr/0005-logging-required-from-day-one.md`.

## Global Constraints

1. **Endpoint**: `POST https://45BWZJ1SGC-dsn.algolia.net/1/indexes/YCCompany_production/query`.
   App ID `45BWZJ1SGC`, index `YCCompany_production` (not the
   `_By_Launch_Date_production` replica). (`yc-fetch-plan.md` section 2)
2. **Headers**: `X-Algolia-Application-Id: 45BWZJ1SGC` and
   `X-Algolia-API-Key: <the full base64 secured-key blob, sent opaque, exactly
   as vended>`. Never decode or reconstruct the key's restriction params
   (`analyticsTags`, `restrictIndices`, `tagFilters`) as a substitute
   credential. (`yc-fetch-plan.md` section 2)
3. **Never pass `tagFilters` in the request body.** The `ycdc_public`
   restriction is already baked into the key's signature; resending it risks
   a conflicting/redundant-restriction error. (`yc-fetch-plan.md` section 2)
4. **Pagination is resolved: split by the `batch` facet, one query per batch
   value, never plain `page`/`hitsPerPage` pagination and never `browse`.**
   Confirmed live 2026-09-08: `hitsPerPage=1000,page=0` silently caps at 1000
   of 6204 total hits (`nbPages: 1`, not `nbPages: 7`); requesting further
   pages returns `nbHits: 0` and an explicit "you can only fetch the 1000
   hits for this query" error; `browse` returns HTTP 403 "Method not allowed
   with this API key" for this key's ACL. `fetch()` must first discover the
   current set of `batch` values, then issue one query per batch value, each
   comfortably under the 1000-hit ceiling. (`yc-fetch-plan.md` section 2,
   "Confirmed by a live test call" bullets 1-3)
5. **`stable_id = str(hit["id"])`.** `id` and `objectID` are confirmed
   equivalent live; use `id`, not `objectID`, per the Signal mapping table's
   naming. (`yc-fetch-plan.md` section 2 bullet 4, section 3)
6. **`payload` is the raw Algolia hit dict, verbatim**, exactly as returned
   in the response's `hits` array entry, including any Algolia-added
   envelope fields (`objectID`, `_highlightResult` if present). No
   pre-selection, no flattening, no derived fields. (`yc-fetch-plan.md`
   section 3; `CLAUDE.md` design standard 2, "Bronze stays exactly
   as-fetched")
7. **A genuine request failure must always propagate** (timeout, non-2xx,
   malformed JSON) — never silently swallowed. (`BEST_PRACTICES.md` section
   6.1, "a real failure must surface somewhere, always"; mirrors KAN-29's
   `_get_json` behavior)
8. **Concurrency**: bounded `ThreadPoolExecutor`, never `asyncio`
   (ADR-0003), 5-10 workers. This plan's ruling: `max_workers=8`, matching
   KAN-29's `MAX_CONCURRENT_FETCHES`, fanning out per-batch queries instead
   of per-comment fetches.
9. **Logging is required from this ticket's first commit, not deferred**
   (ADR-0005, `CLAUDE.md` code standard 9). One module logger
   (`logger = logging.getLogger(__name__)`), no handler configuration in
   this module. `fetch()` logs batch-discovery count, and final record
   count plus duration, per ADR-0005's own worked example ("an adapter's
   `fetch()` logs record counts and duration"). No `logger.exception(...)`
   call belongs in this adapter: `fetch()` never catches the failures it
   must propagate (Constraint 7), so there is no point in this module that
   actually *handles* an exception; catching-just-to-log would be the
   "log and throw" anti-pattern (`BEST_PRACTICES.md` section 6.2).
10. **The Algolia key's literal value is not recorded in any tracked doc**
    (`docs/sources/yc-directory.md` shows `<base64 secured-key blob>` as a
    redacted placeholder, not the real string) and the ticket requires a
    direct Algolia call with **no HTML scraping**, so `fetch()` cannot
    self-discover the key by fetching `ycombinator.com/companies` at
    runtime. **Ruling for this plan**: load the key from a new environment
    variable, `HUGINN_YC_ALGOLIA_API_KEY`, read at call time the same way
    `src/huginn/config.py` already loads `HUGINN_DATABASE_URL` (architecture
    document section 10: "secrets behind an abstracted provider ...
    currently backed by environment variables and a local `.env`"). The key
    itself is not a secret (`docs/sources/yc-directory.md`, Access: "shipped
    to every browser that loads the directory page"), but its value can
    still rotate and must not be hardcoded as a source literal. Missing the
    env var raises `RuntimeError` immediately, mirroring `load_config`'s
    existing behavior. `.env.example` gets a new line for it. This is a
    build-time judgment call, not something the fetch plan or ports.py
    decided; flag it in review.
11. **App ID and index name ARE hardcoded module constants** (unlike the
    key): they are stable identifiers, not rotating credentials, and the
    fetch plan gives their literal values directly (Constraint 1).
12. **This ticket does not touch KAN-7.** The module docstring must stop
    saying "do not ship this adapter's real implementation until KAN-7 is
    closed" (that line predates this ticket's explicit build-now decision)
    and instead note that KAN-7 (ToS-vs-robots.txt legal exposure) is
    accepted-but-unresolved, not resolved by this work, and stays open.
13. **No linter, formatter, or type checker is configured.** Don't add one
    as part of this task. (`CLAUDE.md` code standard 7)
14. **Tests are plain pytest functions**, pytest's built-in `monkeypatch`
    fixture only (including `monkeypatch.setenv`/`delenv` for the API-key
    env var) — no `unittest.mock`, no added mocking library. Mirror
    `tests/ingestion/test_hn.py`'s pattern exactly: no live network calls in
    tests. (`CLAUDE.md` code standard 4)
15. **TDD is mandatory**: failing test first, watch it fail, minimal code to
    pass. (`CLAUDE.md` code standard 5)
16. **Docstrings cite, they don't restate.** Point at
    `architecture-notes/yc-fetch-plan.md` by section. (`CLAUDE.md` code
    standard 3)

---

## Task 1: Module setup and `_algolia_api_key`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py` (replace file contents —
  full file given in Step 3)
- Modify: `.env.example` (add one line)
- Test: `tests/ingestion/test_yc.py` (new file)

**Interfaces:**
- Produces: `_algolia_api_key() -> str` — module-level function in
  `huginn.ingestion.adapters.yc`. Reads `HUGINN_YC_ALGOLIA_API_KEY` from the
  environment; raises `RuntimeError` if unset or empty. Task 2's
  `_algolia_query` calls this directly.
- Produces module constants: `ALGOLIA_APP_ID`, `ALGOLIA_INDEX`,
  `ALGOLIA_QUERY_URL`, `ALGOLIA_API_KEY_ENV_VAR`,
  `ALGOLIA_MAX_HITS_PER_QUERY`, `REQUEST_TIMEOUT_SECONDS`,
  `MAX_CONCURRENT_FETCHES` — consumed by Tasks 2-5.

- [ ] **Step 1: Write the failing tests**

Create `tests/ingestion/test_yc.py` with:

```python
from __future__ import annotations

from huginn.ingestion.adapters import yc


def test_algolia_api_key_reads_env_var(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    assert yc._algolia_api_key() == "test-secured-key"


def test_algolia_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv(yc.ALGOLIA_API_KEY_ENV_VAR, raising=False)

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)


def test_algolia_api_key_raises_when_empty(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "")

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.yc' has
no attribute 'ALGOLIA_API_KEY_ENV_VAR'` (the current stub has none of these
names).

- [ ] **Step 3: Write the minimal implementation**

Replace `src/huginn/ingestion/adapters/yc.py` with:

```python
"""YC directory adapter. See architecture document section 5.

No official API. Queries the public, search-only Algolia key exposed in
the directory's frontend JS directly, rather than parsing rendered pages.
Mechanism: "api" (a direct structured query, not HTML scraping).
Fetch-plan decisions: architecture-notes/yc-fetch-plan.md (KAN-39).

KAN-7 (YC's Terms of Service vs. robots.txt legal exposure) is
accepted-but-unresolved, not a build blocker: this adapter's real
implementation was built per an explicit decision to proceed while that
question stays open. See Jira KAN-7 and docs/sources/yc-directory.md,
Open questions/risks. Nothing here resolves KAN-7.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from huginn.ingestion.ports import ApiSourcePort, RawRecord

logger = logging.getLogger(__name__)

ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_INDEX = "YCCompany_production"
ALGOLIA_QUERY_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
ALGOLIA_API_KEY_ENV_VAR = "HUGINN_YC_ALGOLIA_API_KEY"
ALGOLIA_MAX_HITS_PER_QUERY = 1000
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_CONCURRENT_FETCHES = 8


def _algolia_api_key() -> str:
    """Read YC directory's public, search-only Algolia key from
    `HUGINN_YC_ALGOLIA_API_KEY`.

    The key is not a secret (shipped to every browser that loads the
    directory page), but its literal value is not recorded in any tracked
    doc and can rotate, so it is supplied as config rather than hardcoded.
    See architecture-notes/yc-fetch-plan.md section 2 and
    `src/huginn/config.py` for the equivalent env-var pattern.
    """
    api_key = os.environ.get(ALGOLIA_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{ALGOLIA_API_KEY_ENV_VAR} is not set. Copy .env.example to .env "
            "and fill in YC's current Algolia secured-key blob."
        )
    return api_key


class YcDirectoryAdapter(ApiSourcePort):
    source = "yc"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """TODO (KAN-30, Tasks 2-5): batch discovery and per-batch fetching
        not yet implemented.
        """
        raise NotImplementedError
```

Add to `.env.example`:

```
HUGINN_DATABASE_URL=postgresql://localhost:5432/huginn
HUGINN_YC_ALGOLIA_API_KEY=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py .env.example
git commit -m "feat(yc): add Algolia API key env-var loading"
```

---

## Task 2: `_algolia_query`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py`
- Test: `tests/ingestion/test_yc.py`

**Interfaces:**
- Consumes: `_algolia_api_key()` (Task 1), module constants `ALGOLIA_APP_ID`,
  `ALGOLIA_QUERY_URL`, `REQUEST_TIMEOUT_SECONDS`.
- Produces: `_algolia_query(body: dict) -> dict` — module-level function.
  POSTs `body` as JSON to `ALGOLIA_QUERY_URL` with
  `X-Algolia-Application-Id`/`X-Algolia-API-Key` headers, returns the parsed
  JSON response body. Raises `requests.RequestException` (or a subclass) on
  a genuine request failure. Tasks 3 and 4 call this and monkeypatch it
  directly in their own tests, exactly as `_discover_thread_item`/
  `_fetch_item` monkeypatch `_get_json` in `tests/ingestion/test_hn.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_yc.py`:

```python
import requests


def test_algolia_query_posts_expected_url_headers_and_body(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": [], "nbHits": 0}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(yc.requests, "post", fake_post)
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    result = yc._algolia_query({"query": ""})

    assert captured["url"] == yc.ALGOLIA_QUERY_URL
    assert captured["json"] == {"query": ""}
    assert captured["headers"] == {
        "X-Algolia-Application-Id": yc.ALGOLIA_APP_ID,
        "X-Algolia-API-Key": "test-secured-key",
    }
    assert captured["timeout"] == yc.REQUEST_TIMEOUT_SECONDS
    assert result == {"hits": [], "nbHits": 0}


def test_algolia_query_raises_on_non_2xx_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("403 Forbidden")

        def json(self):
            raise AssertionError("json() must not be called after raise_for_status raises")

    monkeypatch.setattr(yc.requests, "post", lambda url, json, headers, timeout: FakeResponse())
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    try:
        yc._algolia_query({"query": ""})
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass


def test_algolia_query_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv(yc.ALGOLIA_API_KEY_ENV_VAR, raising=False)

    try:
        yc._algolia_query({"query": ""})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.yc' has
no attribute '_algolia_query'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/yc.py`, add this function after
`_algolia_api_key`:

```python
def _algolia_query(body: dict) -> dict:
    """POST one query to YC's Algolia index and return the parsed response.

    Never pass `tagFilters` in `body`: the `ycdc_public` restriction is
    already signed into the secured key. See architecture-notes/yc-fetch-plan.md
    section 2.
    """
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": _algolia_api_key(),
    }
    response = requests.post(
        ALGOLIA_QUERY_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py
git commit -m "feat(yc): add Algolia query POST helper"
```

---

## Task 3: `_discover_batches`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py`
- Test: `tests/ingestion/test_yc.py`

**Interfaces:**
- Consumes: `_algolia_query(body: dict) -> dict` (Task 2).
- Produces: `_discover_batches() -> list[str]` — module-level function.
  Issues a `facets`-only, zero-hit query for the `batch` facet and returns
  its observed values. Task 5's `fetch()` calls this to learn which batch
  values to fan queries out over.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_yc.py`:

```python
def test_discover_batches_requests_batch_facet_with_zero_hits(monkeypatch):
    captured = {}

    def fake_algolia_query(body):
        captured["body"] = body
        return {"facets": {"batch": {}}}

    monkeypatch.setattr(yc, "_algolia_query", fake_algolia_query)

    yc._discover_batches()

    assert captured["body"] == {"query": "", "facets": ["batch"], "hitsPerPage": 0}


def test_discover_batches_returns_facet_keys(monkeypatch):
    facets_response = {"facets": {"batch": {"Summer 2026": 120, "Spring 2026": 95}}}
    monkeypatch.setattr(yc, "_algolia_query", lambda body: facets_response)

    batches = yc._discover_batches()

    assert set(batches) == {"Summer 2026", "Spring 2026"}


def test_discover_batches_returns_empty_list_when_no_facet_values(monkeypatch):
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"facets": {"batch": {}}})

    assert yc._discover_batches() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.yc' has
no attribute '_discover_batches'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/yc.py`, add this function after
`_algolia_query`:

```python
def _discover_batches() -> list[str]:
    """Discover the current set of `batch` facet values.

    Standard Algolia facet-count query (`hitsPerPage: 0` returns facet
    counts with no hit rows). Plain pagination and `browse` cannot reach
    the full ~6200-record directory (confirmed live, 1000-hit ceiling), so
    `fetch()` must split per-batch instead of paginating. See
    architecture-notes/yc-fetch-plan.md section 2, "Confirmed by a live
    test call" bullets 2-3.
    """
    response = _algolia_query({"query": "", "facets": ["batch"], "hitsPerPage": 0})
    return list(response["facets"]["batch"].keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py
git commit -m "feat(yc): discover current batch facet values"
```

---

## Task 4: `_fetch_batch`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py`
- Test: `tests/ingestion/test_yc.py`

**Interfaces:**
- Consumes: `_algolia_query(body: dict) -> dict` (Task 2), constant
  `ALGOLIA_MAX_HITS_PER_QUERY` (Task 1).
- Produces: `_fetch_batch(batch: str) -> list[dict]` — module-level
  function. Returns the raw `hits` list for one `batch` facet value,
  unmodified. Task 5's `fetch()` fans this out per discovered batch through
  a `ThreadPoolExecutor`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_yc.py`:

```python
def test_fetch_batch_requests_filtered_query(monkeypatch):
    captured = {}

    def fake_algolia_query(body):
        captured["body"] = body
        return {"hits": [{"id": 531}], "nbHits": 1}

    monkeypatch.setattr(yc, "_algolia_query", fake_algolia_query)

    yc._fetch_batch("Summer 2026")

    assert captured["body"] == {
        "query": "",
        "filters": "batch:'Summer 2026'",
        "hitsPerPage": yc.ALGOLIA_MAX_HITS_PER_QUERY,
        "page": 0,
    }


def test_fetch_batch_returns_raw_hits_list(monkeypatch):
    hits = [{"id": 531, "name": "A"}, {"id": 8, "name": "PlanGrid"}]
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"hits": hits, "nbHits": 2})

    assert yc._fetch_batch("Summer 2026") == hits


def test_fetch_batch_returns_empty_list_when_no_hits(monkeypatch):
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"hits": [], "nbHits": 0})

    assert yc._fetch_batch("Winter 2005") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.yc' has
no attribute '_fetch_batch'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/yc.py`, add this function after
`_discover_batches`:

```python
def _fetch_batch(batch: str) -> list[dict]:
    """Fetch every hit for one `batch` facet value, unmodified.

    Each batch is comfortably under the confirmed 1000-hit per-query
    ceiling (6204 total hits spread across all batches), so a single query
    per batch is sufficient; no further pagination within a batch. See
    architecture-notes/yc-fetch-plan.md section 2.
    """
    response = _algolia_query(
        {
            "query": "",
            "filters": f"batch:'{batch}'",
            "hitsPerPage": ALGOLIA_MAX_HITS_PER_QUERY,
            "page": 0,
        }
    )
    return response["hits"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py
git commit -m "feat(yc): fetch all hits for one batch facet value"
```

---

## Task 5: `YcDirectoryAdapter.fetch()`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py`
- Test: `tests/ingestion/test_yc.py`

**Interfaces:**
- Consumes: `_discover_batches()` (Task 3), `_fetch_batch(batch: str)`
  (Task 4), `RawRecord` (`huginn.ingestion.ports`, existing: `stable_id:
  str`, `payload: dict`), `MAX_CONCURRENT_FETCHES` (Task 1).
- Produces: `YcDirectoryAdapter.fetch(self) -> list[RawRecord]` — fulfills
  `ApiSourcePort` (`huginn.ingestion.ports.ApiSourcePort`, already
  explicitly implemented by this class since KAN-26). This is the final
  public entry point; nothing later in the current build order consumes it
  directly (KAN-32's `RawStorePort` consumes a `RawRecord` stream in
  general, not this adapter specifically).

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_yc.py`:

```python
def test_fetch_returns_one_record_per_hit_across_batches(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026", "Winter 2012"])

    def fake_fetch_batch(batch):
        if batch == "Summer 2026":
            return [{"id": 531, "name": "A", "batch": batch}]
        return [{"id": 8, "name": "PlanGrid", "batch": batch}]

    monkeypatch.setattr(yc, "_fetch_batch", fake_fetch_batch)

    records = yc.YcDirectoryAdapter().fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {"531", "8"}


def test_fetch_payload_is_exact_raw_hit(monkeypatch):
    hit = {"id": 8, "name": "PlanGrid", "objectID": "8", "batch": "Winter 2012"}
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Winter 2012"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [hit])

    records = yc.YcDirectoryAdapter().fetch()

    assert records == [RawRecord(stable_id="8", payload=hit)]


def test_fetch_stable_id_uses_id_not_object_id(monkeypatch):
    hit = {"id": 531, "objectID": "different-value"}
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [hit])

    records = yc.YcDirectoryAdapter().fetch()

    assert records[0].stable_id == "531"


def test_fetch_returns_empty_list_when_no_batches_discovered(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: [])

    def _unexpected_fetch_batch(batch):
        raise AssertionError("_fetch_batch should not be called with no batches")

    monkeypatch.setattr(yc, "_fetch_batch", _unexpected_fetch_batch)

    assert yc.YcDirectoryAdapter().fetch() == []


def test_fetch_propagates_a_genuine_batch_fetch_failure(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026", "Winter 2012"])

    def fake_fetch_batch(batch):
        if batch == "Winter 2012":
            raise RuntimeError("simulated timeout")
        return [{"id": 1}]

    monkeypatch.setattr(yc, "_fetch_batch", fake_fetch_batch)

    try:
        yc.YcDirectoryAdapter().fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    from huginn.ingestion.ports import ApiSourcePort

    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL — the `fetch`-based tests fail because
`YcDirectoryAdapter().fetch()` raises `NotImplementedError`; the last test
(`ApiSourcePort` conformance) already passes since KAN-26.

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/yc.py`, replace the `YcDirectoryAdapter`
class with:

```python
class YcDirectoryAdapter(ApiSourcePort):
    source = "yc"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current YC directory by querying one Algolia query per
        `batch` facet value, with bounded concurrency.

        Plain pagination and `browse` cannot reach the full directory
        (confirmed live: 1000-hit ceiling, `browse` returns 403 for this
        key); splitting by `batch` is the resolved approach. See
        architecture-notes/yc-fetch-plan.md section 2.
        """
        start = time.monotonic()
        batches = _discover_batches()
        logger.info("yc fetch: discovered %d batch values", len(batches))

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            batch_hits = list(executor.map(_fetch_batch, batches))

        records = [
            RawRecord(stable_id=str(hit["id"]), payload=hit)
            for hits in batch_hits
            for hit in hits
        ]

        duration = time.monotonic() - start
        logger.info(
            "yc fetch: fetched %d records across %d batches in %.2fs",
            len(records),
            len(batches),
            duration,
        )
        return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (18 passed)

Then run the full suite to confirm no regressions:

Run: `uv run pytest -q`
Expected: PASS, all tests green (64 pre-existing + 18 new = 82 passed, 1
skipped). Confirm the actual output matches before reporting this number as
fact.

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py
git commit -m "feat(yc): implement YcDirectoryAdapter.fetch() with per-batch Algolia queries"
```

---

## Post-plan note

This plan implements KAN-30 only. It does not touch `IngestionService`
(KAN-28), `RawStorePort`'s Postgres implementation (KAN-32), or Silver's
staging loader (KAN-34) — `YcDirectoryAdapter` returns raw `RawRecord`s and
nothing downstream is built or modified here. It does not resolve, close,
or otherwise touch KAN-7 (YC ToS-vs-robots.txt legal exposure): that ticket
stays open regardless of this plan's outcome, per the ticket description
and `architecture-notes/yc-fetch-plan.md`'s own framing.
