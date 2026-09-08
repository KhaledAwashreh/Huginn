# KAN-26: Mechanism-Specific Source Port Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single generic `SourcePort` in `src/huginn/ingestion/ports.py`
with a slimmed `SourcePort` base plus `ApiSourcePort`, `WebScrapeSourcePort`, and
`NewsletterSourcePort` Protocols, mirroring Bronze's three mechanism-grouped
tables, then update `HackerNewsAdapter` and `YcDirectoryAdapter` to explicitly
implement `ApiSourcePort`.

**Architecture:** `ports.py` gains three mechanism-specific Protocols, each
extending a shared `SourcePort` base Protocol (`source`, `mechanism`,
`fetch()`, unchanged in shape). `ApiSourcePort` adds nothing beyond the base.
`WebScrapeSourcePort` adds `fetch_page(url: str) -> str`.
`NewsletterSourcePort` adds `fetch_issue(url: str) -> str`.
`IngestionService` keeps depending only on the base `SourcePort` shape and
does not change. `HackerNewsAdapter` and `YcDirectoryAdapter` switch from
implicit structural typing against `SourcePort` to explicit nominal
inheritance from `ApiSourcePort` (`class HackerNewsAdapter(ApiSourcePort):`).
`WebScrapeSourcePort` and `NewsletterSourcePort` get zero concrete
implementations in this ticket, that is the intended end state, not a gap.

**Tech Stack:** Python 3.14, stdlib `typing.Protocol`, pytest plain functions
(no mocking framework, no `runtime_checkable`, see Global Constraint 6 for why).

**Spec:** `architecture-notes/ingestion-port-contracts.md` (KAN-37, the
binding interface-contract note this plan implements verbatim), `CLAUDE.md`
(code/design standards), `src/huginn/ingestion/ports.py`,
`src/huginn/ingestion/adapters/hn.py`, `src/huginn/ingestion/adapters/yc.py`,
`src/huginn/ingestion/service.py` (current state, all read in full before
this plan was written).

## Global Constraints

1. **Exact contract, no re-derivation.** `ports.py`'s new `SourcePort`,
   `ApiSourcePort`, `WebScrapeSourcePort`, `NewsletterSourcePort` — class
   bodies, method signatures, and docstrings — must match
   `architecture-notes/ingestion-port-contracts.md`'s "Contract" code block
   verbatim, except for the module docstring which the note also specifies
   verbatim in the same block. `RawRecord`, `RawStorePort`, `StatePort` in
   `ports.py` are untouched, copy them forward exactly as they exist today.
2. **Shared base, not three independent Protocols** (confirmed by the user,
   design note judgment call 1). `ApiSourcePort`, `WebScrapeSourcePort`,
   `NewsletterSourcePort` all extend `SourcePort`. `IngestionService`
   (`src/huginn/ingestion/service.py`) keeps `sources: list[SourcePort]` and
   its `.fetch()`/`.source`/`.mechanism` calls, unmodified, in this ticket.
3. **`mechanism` stays plain `str`** on the base, not narrowed to a
   `Literal` per port (design note judgment call 2). Do not add
   `Literal["api"]` etc. in this ticket.
4. **`WebScrapeSourcePort` and `NewsletterSourcePort` get zero concrete
   implementations.** This is correct per `CLAUDE.md` code standard 2 ("A
   Protocol with zero implementations is normal here"). Do not write a
   scrape or newsletter adapter, stub or otherwise, as part of this ticket.
5. **`HackerNewsAdapter` and `YcDirectoryAdapter` explicitly implement
   `ApiSourcePort`** via nominal inheritance: `class
   HackerNewsAdapter(ApiSourcePort):` and `class
   YcDirectoryAdapter(ApiSourcePort):`. `mechanism = "api"` and `source`
   stay as they are (`"hn"` / `"yc"`); only the class statement and the
   `ports` import change. Neither adapter's `fetch()` body changes.
6. **No `@runtime_checkable`, no `isinstance`/`issubclass` against Protocol
   classes.** Verified empirically during planning (Python 3.14, this repo):
   `issubclass(SubProtocol, BaseProtocol)` and `issubclass(ConcreteClass,
   SomeProtocol)` both raise `TypeError: Instance and class checks can only
   be used with @runtime_checkable protocols`, even when the subclass
   relationship is genuine nominal inheritance declared in the class
   statement, not just structural. The design note's contract block does
   not include `@runtime_checkable` on any Protocol and this plan does not
   add it (an undocumented deviation from the binding contract). Tests that
   need to check "does this Protocol extend that one" or "does this class
   explicitly implement that Protocol" use plain MRO membership instead:
   `BaseProtocol in SubProtocol.__mro__` / `ApiSourcePort in
   HackerNewsAdapter.__mro__`. This was confirmed working in a standalone
   interpreter check before writing this plan; `hasattr(ProtocolClass,
   "method_name")` was also confirmed to correctly report `True`/`False`
   for a Protocol's own declared methods without needing
   `runtime_checkable`.
7. **No linter, formatter, or type checker configured**, don't add one
   (`CLAUDE.md` code standard 7).
8. **Docstrings cite, they don't restate** (`CLAUDE.md` code standard 3).
   The contract block's docstrings already satisfy this; don't embellish
   them when transcribing.
9. **Tests are plain pytest functions**, no fixture/mocking framework
   (`CLAUDE.md` code standard 4).
10. **TDD is mandatory**: failing test first, watch it fail, minimal code to
    pass (`CLAUDE.md` code standard 5).
11. **Full suite baseline: 31 passed** (confirmed by running `uv run pytest
    -q` before this plan was written). Every task ends with the full suite
    still green, growing by exactly the new tests that task adds.

---

## Task 1: Rewrite `ports.py` with the mechanism-specific Protocols

**Files:**
- Modify: `src/huginn/ingestion/ports.py` (full rewrite of the module
  docstring and `SourcePort`, insert three new Protocols after it; `RawRecord`,
  `RawStorePort`, `StatePort` unchanged)
- Test: `tests/ingestion/test_ports.py` (new file)

**Interfaces:**
- Produces: `huginn.ingestion.ports.SourcePort` (slimmed base, same shape as
  today: `source: str`, `mechanism: str`, `fetch(self) -> list[RawRecord]`),
  `huginn.ingestion.ports.ApiSourcePort` (extends `SourcePort`, no new
  members), `huginn.ingestion.ports.WebScrapeSourcePort` (extends
  `SourcePort`, adds `fetch_page(self, url: str) -> str`), `huginn.ingestion
  .ports.NewsletterSourcePort` (extends `SourcePort`, adds
  `fetch_issue(self, url: str) -> str` and a redeclared `fetch(self) ->
  list[RawRecord]` per the contract). `RawRecord`, `RawStorePort`,
  `StatePort` keep their existing names, fields, and method signatures
  unchanged. Task 2 and Task 3 import `ApiSourcePort` from this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/ingestion/test_ports.py`:

```python
from __future__ import annotations

from huginn.ingestion import ports


def test_api_source_port_extends_source_port():
    assert ports.SourcePort in ports.ApiSourcePort.__mro__


def test_web_scrape_source_port_extends_source_port():
    assert ports.SourcePort in ports.WebScrapeSourcePort.__mro__


def test_newsletter_source_port_extends_source_port():
    assert ports.SourcePort in ports.NewsletterSourcePort.__mro__


def test_api_source_port_adds_no_new_methods_beyond_fetch():
    assert not hasattr(ports.ApiSourcePort, "fetch_page")
    assert not hasattr(ports.ApiSourcePort, "fetch_issue")
    assert hasattr(ports.ApiSourcePort, "fetch")


def test_web_scrape_source_port_declares_fetch_page():
    assert hasattr(ports.WebScrapeSourcePort, "fetch_page")
    assert hasattr(ports.WebScrapeSourcePort, "fetch")


def test_newsletter_source_port_declares_fetch_issue():
    assert hasattr(ports.NewsletterSourcePort, "fetch_issue")
    assert hasattr(ports.NewsletterSourcePort, "fetch")


def test_source_port_base_shape_unchanged():
    assert hasattr(ports.SourcePort, "fetch")
    assert not hasattr(ports.SourcePort, "fetch_page")
    assert not hasattr(ports.SourcePort, "fetch_issue")


def test_raw_record_unchanged():
    record = ports.RawRecord(stable_id="1", payload={"a": 1})
    assert record.stable_id == "1"
    assert record.payload == {"a": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_ports.py -v`
Expected: FAIL — `AttributeError: module 'huginn.ingestion.ports' has no
attribute 'ApiSourcePort'` (the last two tests, `test_source_port_base_shape_unchanged`
and `test_raw_record_unchanged`, will pass already since `SourcePort` and
`RawRecord` already exist in their target shape; that's fine, TDD's "watch
it fail" applies to the tests exercising the new behavior).

- [ ] **Step 3: Write the minimal implementation**

Replace `src/huginn/ingestion/ports.py` in full with:

```python
"""Port contracts for ingestion. See architecture document section 5.

The core (`IngestionService`) depends on `SourcePort` and holds a single
`list[SourcePort]` mixing sources across mechanisms (see `service.py`).
Adapters implement one mechanism-specific port per source: HN and YC
implement `ApiSourcePort`; later sources implement `WebScrapeSourcePort`
or `NewsletterSourcePort`. Outbound concerns (writing to Bronze, tracking
cursor/watermark state) are their own ports so the core never depends on
Postgres directly.

Three sub-protocols exist, one per Bronze mechanism table (architecture
document section 4.1): `bronze.api_ingest`, `bronze.web_scrape_ingest`,
`bronze.newsletter_ingest`. Each shares `SourcePort`'s shape and adds the
one raw-content-fetch method its mechanism actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawRecord:
    """One fetched record, prior to any Bronze-side hashing or storage.

    `stable_id` is the source-native identifier used for the
    `(source, stable_id)` uniqueness key at Bronze (see architecture
    document section 4.1). `payload` is the raw, unmodified data as
    fetched, stored as-is in Bronze's `payload` column.
    """

    stable_id: str
    payload: dict


class SourcePort(Protocol):
    """Common shape every source port has, regardless of mechanism.

    `IngestionService` calls `.fetch()`, `.source`, and `.mechanism` on
    every configured source uniformly; it does not need to know which
    mechanism-specific port a given adapter actually implements. Adapters
    implement one of `ApiSourcePort`, `WebScrapeSourcePort`, or
    `NewsletterSourcePort` below, never this protocol directly.
    """

    source: str
    """Short source identifier stored in Bronze's `source` column, e.g. "hn" or "yc"."""

    mechanism: str
    """Which Bronze table this source's rows land in: "api", "web_scrape", or "newsletter"."""

    def fetch(self) -> list[RawRecord]:
        """Fetch current records from the source. No ingestion policy here:
        pagination, retry, and rate-limit handling belong to the adapter,
        but *what to do* with the results (dedup, scheduling) is the
        `IngestionService`'s job, not this method's.
        """
        ...


class ApiSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data comes from a structured API
    or API-shaped backend: an official JSON API (HN's Firebase API) or a
    directly-queried structured backend (YC's Algolia search-only key).
    `mechanism` is always "api" for implementations of this port. See
    architecture document section 5. Bronze destination:
    `bronze.api_ingest` (section 4.1).

    No method beyond `fetch()`. An API response is already the structured
    shape `fetch()` needs, so there is no separate raw-content step worth
    exposing at the port boundary here, unlike `WebScrapeSourcePort` and
    `NewsletterSourcePort` below. This is deliberately not a bare alias for
    `SourcePort`: a future API-only need (an auth-header method, a
    rate-limit attribute) has a home on this port without forcing
    `WebScrapeSourcePort` or `NewsletterSourcePort` to carry it too.
    """


class WebScrapeSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data is extracted from rendered
    HTML with no structured API underneath (the VC-board, Ramp, and
    Harmonic candidates named in the concept doc, section 7). `mechanism`
    is always "web_scrape" for implementations of this port. See
    architecture document section 5. Bronze destination:
    `bronze.web_scrape_ingest` (section 4.1).
    """

    def fetch_page(self, url: str) -> str:
        """Fetch one page's rendered content and return it as HTML.
        Separated from `fetch()` so a slow or failed network call and the
        parsing logic that turns HTML into `RawRecord`s are independently
        testable: a parsing bug should be reproducible from a saved HTML
        fixture without re-fetching a live page, and a fetch failure should
        be retriable without re-running extraction.
        """
        ...

    def fetch(self) -> list[RawRecord]:
        """Fetch and parse current records from the source. Calls
        `fetch_page` for whichever URLs the source needs (a listing page,
        per-listing detail pages, or however the source's pagination is
        shaped) and extracts `RawRecord`s from the returned HTML. Which
        URLs to fetch and how to paginate is adapter-specific and not part
        of this contract: sites differ too much in structure to standardize
        past "you get a per-page fetch primitive."
        """
        ...


class NewsletterSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data arrives as periodic
    newsletter issues (the four Substack feeds named in the concept doc,
    section 7). `mechanism` is always "newsletter" for implementations of
    this port. See architecture document section 5. Bronze destination:
    `bronze.newsletter_ingest` (section 4.1).
    """

    def fetch_issue(self, url: str) -> str:
        """Fetch one newsletter issue's raw content by its feed-provided
        URL or GUID (an RSS/Atom item's `<link>` or `<guid>`). Returns the
        issue body as delivered by the source: HTML for the Substack feeds,
        since Substack's RSS exposes issue content as HTML in
        `<content:encoded>`. Separated from `fetch()` for the same reason
        as `WebScrapeSourcePort.fetch_page`: a slow or failed fetch and a
        parsing bug should be independently reproducible and retriable.
        """
        ...

    def fetch(self) -> list[RawRecord]:
        """Fetch current issues and extract one `RawRecord` per company
        signal found inside each issue's content. Not a 1:1 issue-to-record
        mapping: a single issue routinely mentions more than one company.
        Issue discovery (which issue URLs currently exist, via the feed's
        own index) and the per-issue call to `fetch_issue` both happen
        here; no ingestion policy beyond that, same as the other two ports.
        """
        ...


class RawStorePort(Protocol):
    """Writes fetched records to Bronze. See architecture document section 4.1
    for the mechanism-grouped table layout and the hash-based write behavior.
    """

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> None:
        """Write records to the appropriate Bronze table. Implementations must
        apply the skip-on-hash-match behavior: a record whose content hash
        matches the last stored hash for its `(source, stable_id)` should not
        insert a new row, only bump `last_checked_at` on the existing one.
        """
        ...


class StatePort(Protocol):
    """Per-entity content-hash watermark, replacing a source-provided cursor.
    See architecture document section 4.1: neither HN's Firebase API nor
    YC's Algolia backend offers a reliable "give me only what changed" cursor.
    """

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """The last stored content hash for this entity, or None if never seen."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_ports.py -v`
Expected: PASS (8 passed)

Then run the full suite:

Run: `uv run pytest -q`
Expected: PASS (39 passed: 31 pre-existing + 8 new)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/ports.py tests/ingestion/test_ports.py
git commit -m "feat(ingestion): split SourcePort into mechanism-specific ports"
```

---

## Task 2: `HackerNewsAdapter` explicitly implements `ApiSourcePort`

**Files:**
- Modify: `src/huginn/ingestion/adapters/hn.py`
- Test: `tests/ingestion/test_hn.py` (append)

**Interfaces:**
- Consumes: `huginn.ingestion.ports.ApiSourcePort` (Task 1).
- Produces: `HackerNewsAdapter` now explicitly subclasses `ApiSourcePort`.
  No change to `HackerNewsAdapter.fetch()`'s behavior, `source`, or
  `mechanism` values.

- [ ] **Step 1: Write the failing test**

Append to `tests/ingestion/test_hn.py`:

```python
from huginn.ingestion.ports import ApiSourcePort


def test_hacker_news_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in hn.HackerNewsAdapter.__mro__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ingestion/test_hn.py -v -k api_source_port`
Expected: FAIL — `AssertionError` (`HackerNewsAdapter` does not yet inherit
from `ApiSourcePort`).

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/hn.py`, change the import line:

```python
from huginn.ingestion.ports import ApiSourcePort, RawRecord
```

Change the class declaration:

```python
class HackerNewsAdapter(ApiSourcePort):
    source = "hn"
    mechanism = "api"
```

(`fetch()`'s body is unchanged; only the import and class statement move.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_hn.py -v`
Expected: PASS (15 passed: 14 pre-existing + 1 new)

Then run the full suite:

Run: `uv run pytest -q`
Expected: PASS (40 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/hn.py tests/ingestion/test_hn.py
git commit -m "feat(hn): implement ApiSourcePort explicitly"
```

---

## Task 3: `YcDirectoryAdapter` explicitly implements `ApiSourcePort`

**Files:**
- Modify: `src/huginn/ingestion/adapters/yc.py`
- Test: `tests/ingestion/test_yc.py` (new file)

**Interfaces:**
- Consumes: `huginn.ingestion.ports.ApiSourcePort` (Task 1).
- Produces: `YcDirectoryAdapter` now explicitly subclasses `ApiSourcePort`.
  No change to `YcDirectoryAdapter.fetch()`'s behavior (still raises
  `NotImplementedError`, per KAN-7 block noted in the module docstring), or
  to `source`/`mechanism`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ingestion/test_yc.py`, mirroring `tests/ingestion/test_hn.py`'s
existing import style (direct submodule import, confirmed by reading that
file: `from huginn.ingestion.adapters import hn`):

```python
from __future__ import annotations

import pytest

from huginn.ingestion.adapters import yc
from huginn.ingestion.ports import ApiSourcePort


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__


def test_yc_directory_adapter_source_and_mechanism_unchanged():
    adapter = yc.YcDirectoryAdapter()
    assert adapter.source == "yc"
    assert adapter.mechanism == "api"


def test_yc_directory_adapter_fetch_still_not_implemented():
    adapter = yc.YcDirectoryAdapter()
    with pytest.raises(NotImplementedError):
        adapter.fetch()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: FAIL on `test_yc_directory_adapter_explicitly_implements_api_source_port`
(`AssertionError`, `YcDirectoryAdapter` does not yet inherit from
`ApiSourcePort`). The other two tests may already pass against current
`yc.py`, that's fine, they lock in behavior this task must not break.

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/adapters/yc.py`, change the import line:

```python
from huginn.ingestion.ports import ApiSourcePort, RawRecord
```

Change the class declaration:

```python
class YcDirectoryAdapter(ApiSourcePort):
    source = "yc"
    mechanism = "api"
```

(`fetch()`'s body, including its `NotImplementedError` and its docstring,
is unchanged; only the import and class statement move.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_yc.py -v`
Expected: PASS (3 passed)

Then run the full suite:

Run: `uv run pytest -q`
Expected: PASS (43 passed: 40 from Task 2 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/adapters/yc.py tests/ingestion/test_yc.py
git commit -m "feat(yc): implement ApiSourcePort explicitly"
```

---

## Task 4: Confirm `IngestionService` is unaffected

**Files:**
- None modified. This task is a verification-only checkpoint, per Global
  Constraint 2 and the design note's contract section 4 ("`IngestionService
  .run_once` does not change").
- Test: none new. Re-run existing `tests/ingestion` suite plus a manual
  read-through.

**Interfaces:**
- Consumes: `huginn.ingestion.ports.SourcePort` (Task 1, unchanged shape),
  `HackerNewsAdapter`/`YcDirectoryAdapter` (Tasks 2/3, now `ApiSourcePort`
  subclasses, which are also `SourcePort`s via Global Constraint 2).
- Produces: nothing new; this task only confirms no regression.

- [ ] **Step 1: Re-read `src/huginn/ingestion/service.py` in full**

Confirm `IngestionService.__init__(self, sources: list[SourcePort], ...)`
and `run_once`'s `source.fetch()` / `source.source` / `source.mechanism`
calls are still exactly as they were before this plan started (no edits
were made to this file in Tasks 1-3). If any diff exists against the
version quoted in `architecture-notes/ingestion-port-contracts.md`'s
"Reference" section, stop and flag it, don't silently edit it, this
ticket's scope is the port split, not `IngestionService`.

- [ ] **Step 2: Confirm the adapters still satisfy `list[SourcePort]` usage**

Since `ApiSourcePort` extends `SourcePort` (Global Constraint 2),
`HackerNewsAdapter` and `YcDirectoryAdapter` instances remain valid
elements of a `list[SourcePort]`-typed argument with no code change needed
in `service.py`. There is no existing `tests/ingestion/test_service.py` to
run; this is confirmed by inspection (Protocol structural typing plus the
explicit `ApiSourcePort` inheritance from Task 2/3), not by a new test,
since `service.py` has no test file to extend and this ticket does not
introduce one (`IngestionService` behavior is out of scope, per the ticket
description and Global Constraint 2).

- [ ] **Step 3: Run the full suite one final time**

Run: `uv run pytest -q`
Expected: PASS (43 passed)

- [ ] **Step 4: No commit for this task**

This task makes no file changes, there is nothing to commit. Proceed
directly to the final whole-branch review.

---

## Post-plan note

This plan implements KAN-26 only: the `ports.py` mechanism split and the
two existing adapters' explicit `ApiSourcePort` inheritance. It does not
add a web-scrape or newsletter adapter (no such ticket exists yet, and
`CLAUDE.md` code standard 2 says not to invent one), does not touch
`IngestionService` (KAN-28's territory, confirmed unaffected in Task 4),
and does not add a `Literal` narrowing for `mechanism` (design note
judgment call 2, left as future work if ever revisited).
