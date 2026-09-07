# KAN-29: HN Adapter `fetch()` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `HackerNewsAdapter.fetch()` so it discovers the current
month's "Who's Hiring" thread and returns a `RawRecord` for the root post and
one for each of its top-level comments, exactly per the fully-resolved KAN-38
fetch plan.

**Architecture:** Three stateless, module-level helper functions in
`src/huginn/ingestion/adapters/hn.py` (`_get_json`, `_discover_thread_item`,
`_fetch_item`), layered under `HackerNewsAdapter.fetch()`, which fans the
top-level `kids` fetches out through a bounded `concurrent.futures.ThreadPoolExecutor`.
No new dependency: `requests` (already a dependency) for HTTP, stdlib
`concurrent.futures` for bounded concurrency.

**Tech Stack:** Python 3.14, `requests`, stdlib `concurrent.futures.ThreadPoolExecutor`
and `re`, pytest with its built-in `monkeypatch` fixture (no added mocking
library).

**Spec:** `architecture-notes/hn-fetch-plan.md` (KAN-38, the binding fetch-plan
decisions), `docs/sources/hn-who-is-hiring.md` (underlying API research),
`src/huginn/ingestion/ports.py` (`RawRecord`, `SourcePort` this adapter
implements), `CLAUDE.md` and `BEST_PRACTICES.md` (project conventions).

## Global Constraints

1. **Thread discovery**: `GET /v0/user/whoishiring.json`, take `submitted[0]`,
   fetch that item, and require its `title` to match
   `^Ask HN: Who is hiring\? \(`. No Algolia cross-check. If the title does
   not match, raise — the Algolia fallback is a documented escalation path,
   not code, per `hn-fetch-plan.md` section 1.
2. **Recursion depth**: root item plus its direct `kids` only. Never walk a
   kid's own `kids`. (`hn-fetch-plan.md` section 2)
3. **Dead items** (`dead: true`): fetched and stored as-is, unfiltered.
   `fetch()` never inspects the `dead` field. (`hn-fetch-plan.md` section 2)
4. **Deleted items** (`deleted: true`): fetched and stored as-is, exactly like
   any other item, no special-case code. (`hn-fetch-plan.md` section 2)
5. **Bare `null` responses** (id never existed): produce no `RawRecord` for
   that id. Silent skip, not an error. (`hn-fetch-plan.md` section 2)
6. **A genuine request failure** (timeout, non-2xx status, malformed JSON) is
   a different failure axis than case 5 and must always propagate as an
   exception — never silently treated as "id doesn't exist" and never
   swallowed. (`hn-fetch-plan.md` section 2; `BEST_PRACTICES.md` section 6.1,
   "a real failure must surface somewhere, always")
7. **RawRecord mapping**: `stable_id = str(item["id"])`; `payload` = the
   fetched item dict, completely verbatim, no added/removed/renamed keys, no
   derived fields. (`hn-fetch-plan.md` section 3; `CLAUDE.md` design standard
   2, "Bronze stays exactly as-fetched")
8. **Concurrency**: fetch top-level kids with a small bounded concurrency cap
   (5-10 in flight), never an unbounded loop. This plan's ruling: stdlib
   `ThreadPoolExecutor(max_workers=8)` with the existing synchronous
   `requests` dependency, not `asyncio`/`httpx`. Reason: `requests` is already
   the project's only HTTP dependency, no other code in the project is async
   yet, and a thread pool meets the bounded-concurrency requirement with zero
   new dependencies. (`hn-fetch-plan.md` section 2 leaves the exact mechanism
   to this task; `BEST_PRACTICES.md` section 9 flags the async-vs-thread
   choice as open — this plan closes it for KAN-29 specifically, not
   project-wide.)
9. **No linter, formatter, or type checker is configured.** Don't add one as
   part of this task. (`CLAUDE.md` code standard 7)
10. **Tests are plain pytest functions.** Use pytest's built-in `monkeypatch`
    fixture only — it ships with pytest itself, not an added mocking
    framework — since HTTP genuinely cannot be avoided for this adapter's
    tests. No `unittest.mock`, no `responses`/`requests-mock`. (`CLAUDE.md`
    code standard 4)
11. **TDD is mandatory**: failing test first, watch it fail, minimal code to
    pass. (`CLAUDE.md` code standard 5)
12. **Docstrings cite, they don't restate.** Point at
    `architecture-notes/hn-fetch-plan.md` by section, not at a paraphrase of
    it. (`CLAUDE.md` code standard 3)

---

## Task 1: `_get_json` HTTP helper

**Files:**
- Modify: `src/huginn/ingestion/adapters/hn.py` (replace file contents — see
  Step 3 for the full file at the end of this task)
- Test: `tests/ingestion/test_hn.py` (new file)

**Interfaces:**
- Produces: `_get_json(url: str) -> dict | None` — module-level function in
  `huginn.ingestion.adapters.hn`. Raises `requests.RequestException` (or a
  subclass, e.g. `requests.HTTPError`) on a genuine request failure. Returns
  `None` when the response body is the JSON literal `null`. Returns a `dict`
  otherwise. Tasks 2 and 3 call this function and monkeypatch it directly in
  their own tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/ingestion/test_hn.py` with:

```python
from __future__ import annotations

import requests

from huginn.ingestion.adapters import hn


def test_get_json_returns_none_for_bare_null_body(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return None

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    assert hn._get_json("https://example.invalid/item/1.json") is None


def test_get_json_returns_parsed_dict_body(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 1, "type": "story"}

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    assert hn._get_json("https://example.invalid/item/1.json") == {"id": 1, "type": "story"}


def test_get_json_raises_on_non_2xx_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

        def json(self):
            raise AssertionError("json() must not be called after raise_for_status raises")

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    try:
        hn._get_json("https://example.invalid/item/1.json")
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.hn' has no
attribute '_get_json'` (or `ModuleNotFoundError` if `hn.py` doesn't import
`requests` yet as a module-level name for monkeypatching).

- [ ] **Step 3: Write the minimal implementation**

Replace `src/huginn/ingestion/adapters/hn.py` with:

```python
"""HN "Who's Hiring" adapter. See architecture document section 5.

Official Firebase API, no auth, no rate limit. Mechanism: "api".
Fetch-plan decisions: architecture-notes/hn-fetch-plan.md (KAN-38).
"""

from __future__ import annotations

import requests

from huginn.ingestion.ports import RawRecord

FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"
REQUEST_TIMEOUT_SECONDS = 10.0


def _get_json(url: str) -> dict | None:
    """GET a Firebase URL and return its parsed JSON body.

    A genuine request failure (timeout, non-2xx, malformed JSON) raises; a
    body of the JSON literal `null` returns `None`. See
    architecture-notes/hn-fetch-plan.md section 2.
    """
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


class HackerNewsAdapter:
    source = "hn"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        TODO (KAN-29, Task 2/3): thread discovery and kid fetching not yet
        implemented.
        """
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/hn.py tests/ingestion/test_hn.py
git commit -m "feat(hn): add Firebase JSON GET helper with null/error semantics"
```

---

## Task 2: `_discover_thread_item`

**Files:**
- Modify: `src/huginn/ingestion/adapters/hn.py`
- Test: `tests/ingestion/test_hn.py`

**Interfaces:**
- Consumes: `_get_json(url: str) -> dict | None` (Task 1).
- Produces: `_discover_thread_item() -> dict` — module-level function.
  Returns the root thread item dict (already fetched, ready to reuse — no
  second fetch of the same id). Raises `RuntimeError` when `submitted[0]`'s
  title doesn't match the Who's Hiring pattern. Task 3's `fetch()` calls this
  directly and reuses its return value as the root item, avoiding a
  redundant fetch of the same id.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_hn.py`:

```python
ROOT_ID = 49522897

WHOISHIRING_USER_JSON = {"submitted": [ROOT_ID, ROOT_ID - 1]}
ROOT_ITEM = {
    "id": ROOT_ID,
    "type": "story",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [],
}


def test_discover_thread_item_returns_matching_submission(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    assert hn._discover_thread_item() == ROOT_ITEM


def test_discover_thread_item_raises_when_title_does_not_match(monkeypatch):
    mismatched_item = {"id": ROOT_ID, "title": "Ask HN: Something else", "kids": []}
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": mismatched_item,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    try:
        hn._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)


def test_discover_thread_item_raises_when_candidate_is_bare_null(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": None,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    try:
        hn._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.hn' has no
attribute '_discover_thread_item'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/hn.py`, add near the top (after the
existing imports):

```python
import re
```

Add module-level constants after `REQUEST_TIMEOUT_SECONDS`:

```python
WHOISHIRING_USER = "whoishiring"
THREAD_TITLE_PATTERN = re.compile(r"^Ask HN: Who is hiring\? \(")
```

Add this function after `_get_json`:

```python
def _discover_thread_item() -> dict:
    """Find and return the current "Who's Hiring" root thread item.

    `submitted[0]` plus a title check, no Algolia cross-check. See
    architecture-notes/hn-fetch-plan.md section 1.
    """
    user = _get_json(f"{FIREBASE_BASE_URL}/user/{WHOISHIRING_USER}.json")
    candidate_id = user["submitted"][0]
    item = _get_json(f"{FIREBASE_BASE_URL}/item/{candidate_id}.json")
    title = item.get("title", "") if item else ""
    if not THREAD_TITLE_PATTERN.match(title):
        raise RuntimeError(
            f"whoishiring's latest submission (id {candidate_id}) does not "
            f"look like a Who's Hiring thread (title: {title!r})"
        )
    return item
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/hn.py tests/ingestion/test_hn.py
git commit -m "feat(hn): discover the current Who's Hiring thread by title match"
```

---

## Task 3: `_fetch_item` and `HackerNewsAdapter.fetch()`

**Files:**
- Modify: `src/huginn/ingestion/adapters/hn.py`
- Test: `tests/ingestion/test_hn.py`

**Interfaces:**
- Consumes: `_get_json` (Task 1), `_discover_thread_item` (Task 2),
  `RawRecord` (`huginn.ingestion.ports`, existing: `stable_id: str`,
  `payload: dict`).
- Produces: `_fetch_item(item_id: int) -> dict | None` — module-level
  function, thin wrapper over `_get_json` for one item id.
  `HackerNewsAdapter.fetch(self) -> list[RawRecord]` — fulfills the
  `SourcePort` protocol (`huginn.ingestion.ports.SourcePort`); this is the
  final public entry point, nothing later in the plan consumes it (KAN-29 is
  a leaf in the current build order — KAN-32 consumes a `RawRecord` stream
  in general, not this adapter specifically).

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_hn.py`:

```python
KID_A_ID = 49573833
KID_B_ID = 49524098  # deleted stub
KID_C_ID = 49999999  # bare null, never existed

ROOT_ITEM_WITH_KIDS = {
    "id": ROOT_ID,
    "type": "story",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [KID_A_ID, KID_B_ID, KID_C_ID],
}
KID_A_ITEM = {
    "id": KID_A_ID,
    "type": "comment",
    "parent": ROOT_ID,
    "by": "srikanthkasa",
    "text": "Supero | Cloud / Platform Engineer | REMOTE",
}
KID_B_DELETED_ITEM = {
    "id": KID_B_ID,
    "deleted": True,
    "parent": ROOT_ID,
    "time": 1788279499,
    "type": "comment",
}

FIREBASE_FIXTURES = {
    f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
    f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM_WITH_KIDS,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_A_ID}.json": KID_A_ITEM,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_B_ID}.json": KID_B_DELETED_ITEM,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_C_ID}.json": None,
}


def _fake_get_json(url):
    return FIREBASE_FIXTURES[url]


def test_fetch_item_returns_none_for_bare_null(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    assert hn._fetch_item(KID_C_ID) is None


def test_fetch_item_returns_deleted_stub_as_is(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    assert hn._fetch_item(KID_B_ID) == KID_B_DELETED_ITEM


def test_fetch_returns_root_and_top_level_kids(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {str(ROOT_ID), str(KID_A_ID), str(KID_B_ID)}


def test_fetch_skips_bare_null_kids(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    assert str(KID_C_ID) not in {record.stable_id for record in records}


def test_fetch_stores_deleted_stub_verbatim(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    deleted_record = next(r for r in records if r.stable_id == str(KID_B_ID))
    assert deleted_record.payload == KID_B_DELETED_ITEM


def test_fetch_payload_is_exact_root_item(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    root_record = next(r for r in records if r.stable_id == str(ROOT_ID))
    assert root_record.payload == ROOT_ITEM_WITH_KIDS


def test_fetch_root_with_no_kids_returns_single_record(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    records = hn.HackerNewsAdapter().fetch()

    assert [r.stable_id for r in records] == [str(ROOT_ID)]


def test_fetch_propagates_a_genuine_kid_fetch_failure(monkeypatch):
    def _raising_get_json(url):
        if url == f"{hn.FIREBASE_BASE_URL}/item/{KID_A_ID}.json":
            raise RuntimeError("simulated timeout")
        return _fake_get_json(url)

    monkeypatch.setattr(hn, "_get_json", _raising_get_json)

    try:
        hn.HackerNewsAdapter().fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.adapters.hn' has no
attribute '_fetch_item'` (and `HackerNewsAdapter().fetch()` raises
`NotImplementedError` for the `fetch`-based tests).

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/hn.py`, add near the top imports:

```python
from concurrent.futures import ThreadPoolExecutor
```

Add a constant after `THREAD_TITLE_PATTERN`:

```python
MAX_CONCURRENT_FETCHES = 8
```

Add this function after `_discover_thread_item`:

```python
def _fetch_item(item_id: int) -> dict | None:
    """Fetch one HN item by id.

    Returns `None` for a bare `null` response (id never existed); a
    `deleted: true` stub is returned as-is like any other item. See
    architecture-notes/hn-fetch-plan.md section 2.
    """
    return _get_json(f"{FIREBASE_BASE_URL}/item/{item_id}.json")
```

Replace the `HackerNewsAdapter` class with:

```python
class HackerNewsAdapter:
    source = "hn"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        Root plus direct kids only, no nested-reply walk; kids are fetched
        with bounded concurrency. See architecture-notes/hn-fetch-plan.md
        section 2.
        """
        root_item = _discover_thread_item()
        records = [RawRecord(stable_id=str(root_item["id"]), payload=root_item)]

        kid_ids = root_item.get("kids", [])
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            kid_items = list(executor.map(_fetch_item, kid_ids))

        for kid_item in kid_items:
            if kid_item is None:
                continue
            records.append(RawRecord(stable_id=str(kid_item["id"]), payload=kid_item))

        return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: PASS (14 passed)

Then run the full suite to confirm no regressions:

Run: `uv run pytest -q`
Expected: PASS, all tests green (17 pre-existing + 14 new = 31)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/hn.py tests/ingestion/test_hn.py
git commit -m "feat(hn): implement HackerNewsAdapter.fetch() with bounded concurrency"
```

---

## Post-plan note

This plan implements KAN-29 only. It does not touch `IngestionService`
(KAN-28), `RawStorePort`'s Postgres implementation (KAN-32), or the port
split (KAN-26) — `HackerNewsAdapter` continues to implement the current
undifferentiated `SourcePort` protocol in `ports.py` until KAN-26 lands, per
`architecture-notes/kan-21-build-plan.md`'s dependency chain, which lists
KAN-38 (this plan's spec) as the only blocker for KAN-29.
