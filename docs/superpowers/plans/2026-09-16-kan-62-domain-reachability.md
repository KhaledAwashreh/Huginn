# KAN-62: Domain reachability check before DOMAIN_NORMALIZED

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `resolve_signal()` (`src/huginn/elt/silver/signal_resolution.py`)
currently grants `DOMAIN_NORMALIZED` to any domain that parses and isn't
denylisted, with zero network check. A domain that doesn't resolve, or whose
site is dead, becomes a real `gold.company` row. Add
`check_domain_reachable()` and wire it into `resolve_signal()`'s decision
chain so an unreachable domain routes to `UNRESOLVED` instead.

**Architecture:** One new function, `check_domain_reachable(domain: str,
timeout: float = 5.0) -> bool`, added to `src/huginn/elt/silver/resolution.py`
next to `normalize_domain`. `resolve_signal()` in `signal_resolution.py`
calls it after the existing normalize + denylist checks pass, before
returning `DOMAIN_NORMALIZED`.

**Tech Stack:** Python 3.14, `requests` (already a dependency, see
`opencorporates.py`), stdlib `socket`/`ipaddress` for the SSRF guard, pytest
with `monkeypatch` mocking `requests.head`/`requests.get` at module level
(same convention as `tests/elt/ingestion/test_opencorporates.py`), no
mocking framework.

**Spec:** Jira KAN-62 (fetch live with `mcp__atlassian__getJiraIssue`,
`issueIdOrKey: "KAN-62"`, `cloudId: "kawashreh.atlassian.net"` for the
authoritative current text before starting; the description below is a
faithful summary as of 2026-09-16 but the ticket is the binding source).
`src/huginn/elt/silver/resolution.py` and `signal_resolution.py` (existing
code this plan extends). `tests/elt/silver/test_signal_resolution.py`
(existing test suite this plan must keep passing, updated for the new
dependency). `src/huginn/elt/ingestion/adapters/opencorporates.py` (the
`requests`-based adapter pattern to match: module-level function, `try`/
`except requests.RequestException`, a sanitized custom exception where the
raw exception shouldn't leak, `REQUEST_TIMEOUT_SECONDS`-style module
constant). `CLAUDE.md` code standards 1, 3, 4, 5, 9 (frozen dataclasses,
docstrings cite don't restate, DB-free plain-pytest tests, TDD mandatory,
logging at pipeline-stage boundaries).

KAN-62's own decided design (quoting the ticket): HEAD request to
`https://{domain}`, falling back to GET if HEAD is rejected (many servers
405 on HEAD). Any 2xx/3xx response is reachable; connection errors,
timeouts, DNS failures, and 4xx/5xx are not. Plain monkeypatchable
module-level function, matching this codebase's established requests-
mocking test style. Content verification (does the site actually belong to
the claimed company) is explicitly out of scope, reachability only.
Per-run re-check of every already-resolved domain is an accepted,
named cost (redundant network I/O), not a blocker for this ticket;
optimizing it away (e.g. skip domains checked recently) is deferred debt
for Jira KAN-16, not built here.

## Global Constraints

1. **SSRF guard is in scope, TOCTOU-limited by design, and that limit is
   accepted debt, not silently ignored.** `domain` ultimately comes from
   external signal data (HN/YC post text), so nothing today stops
   `check_domain_reachable("169.254.169.254")` or a domain that resolves to
   an internal address from firing a live request at infrastructure the
   caller never intended to reach. Before making the HTTP request, resolve
   the hostname (`socket.getaddrinfo(domain, 443)` or equivalent) and reject
   as not-reachable (return `False`, log at WARNING) if every resolved
   address is private, loopback, link-local, or otherwise reserved per
   `ipaddress.ip_address(...).is_private / .is_loopback / .is_link_local /
   .is_reserved`. This is a pre-connect check, not a pinned-IP connection:
   a DNS answer could still change between this check and `requests`' own
   resolution inside the same call (a rebind attack), and this plan
   explicitly does not close that gap (doing so needs a custom transport
   adapter connecting directly to a pinned IP, real added complexity this
   ticket's "plain monkeypatchable module-level function" framing doesn't
   want). Document this limitation in the function's docstring, citing this
   ticket, and leave closing it as follow-up debt for Jira KAN-16. This is
   the same shape of explicit-cost-acceptance the ticket itself already
   uses for the redundant-recheck cost, applied to a security cost instead
   of a performance one.
2. **Set a real browser `User-Agent` header on every request.** Confirmed
   live this session (`docs/sources/eu-startups.md`, verified 2026-09-16):
   a real, legitimate site returned HTTP 403 via Cloudflare to a request
   with no/default `User-Agent`, on the very first request, every time, and
   returned a clean 200 the instant an ordinary desktop browser
   `User-Agent` string was set, no other change needed. Without this, this
   function will misclassify real, live companies as unreachable purely
   because their host has basic bot mitigation, which is exactly the
   failure mode this ticket exists to avoid causing (a wrongly-unreachable
   real company routes to manual review, the opposite problem from the
   ticket's stated one, but the same class of harm: a wrong signal instead
   of an honest "don't know"). Use:
   `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36`
   as a module constant, e.g. `REACHABILITY_USER_AGENT`.
3. **One bounded retry on a transient-looking failure before declaring
   unreachable, not on a confident negative.** `SignalResolver.resolve_all()`
   already re-processes every staged signal on every run (existing,
   documented behavior in `signal_resolution.py`'s own docstring). Wiring a
   live network check into `resolve_signal()` means a single transient
   blip (a timeout, a connection reset) on an otherwise-fine, already-
   `DOMAIN_NORMALIZED` company can silently flip it to `UNRESOLVED` on the
   very next run, with no distinction from a domain that is actually dead.
   `resolve_signal()` is a stateless pure function today (no access to the
   previous run's `key_derivation` for this row) and giving it that access
   would mean threading previous-state through `SignalResolutionRepositoryPort`
   and `resolve_all()`, real scope beyond this ticket's stated boundary
   (the ticket asks for a check wired into the existing decision chain, not
   a repository/port redesign). The in-scope mitigation: inside
   `check_domain_reachable()` itself, on a `requests.Timeout` or
   `requests.ConnectionError` specifically (not on a completed HTTP
   response, and not on a DNS resolution failure, both of which are
   confident negative signals), retry once, immediately, before returning
   `False`. This does not fully solve the problem (two consecutive blips
   still read as unreachable) but meaningfully reduces single-blip false
   negatives without expanding scope into state-tracking. Document this as
   a mitigation, not a full fix, in the function's docstring, and note that
   a fully correct fix (comparing against prior resolved state) is
   follow-up debt for Jira KAN-16.
4. **Parking pages are explicitly out of scope, not a gap to fix.** The
   ticket's own text draws this line: reachability only, content
   verification (including "is this actually a live company site or a
   registrar parking page") is a materially harder, separate problem,
   explicitly deferred. A parking page returning HTTP 200 counts as
   reachable under this ticket's definition. Do not build parking-page
   detection. One sentence in the function's docstring naming this as a
   known, accepted limitation is enough, citing this ticket.
5. **HEAD-then-GET-fallback, exactly as specified.** Try `requests.head`
   first (with the UA header, Constraint 2). If the response status is
   `405` (Method Not Allowed) or the head request itself raises
   `requests.RequestException` in a way that a plain GET might not (many
   servers reject HEAD outright), retry the same URL with `requests.get`.
   Both calls share the SSRF pre-check (Constraint 1), the UA header
   (Constraint 2), and the transient-retry mitigation (Constraint 3).
6. **Docstrings cite, don't restate** (`CLAUDE.md` code standard 3). Point
   at Jira KAN-62 and this plan's Global Constraints 1, 3, 4 for the SSRF/
   retry/parking-page decisions, not a paraphrase of the reasoning inline.
7. **TDD mandatory, DB-free/network-free tests** (`CLAUDE.md` code
   standards 4, 5). Every test in this plan mocks `requests.head`/
   `requests.get` and, where the SSRF guard is under test, the DNS
   resolution call, at module level via `monkeypatch.setattr`, matching
   `test_opencorporates.py`'s convention exactly (e.g.
   `monkeypatch.setattr(resolution.requests, "head", fake_head)`). No test
   in this plan makes a real network call.
8. **Every existing test in `tests/elt/silver/test_signal_resolution.py`
   must still pass, updated for the new dependency.** Adding a network
   check inside `resolve_signal()`'s call chain means every existing test
   that currently calls `resolve_signal(...)` expecting `DOMAIN_NORMALIZED`
   for a normalizable, non-denylisted domain (see Task 2's file list) will,
   unmodified, attempt a real network call and fail/hang. Each such test
   needs `monkeypatch.setattr(signal_resolution, "check_domain_reachable",
   lambda domain, timeout=5.0: True)` (or the module path
   `huginn.elt.silver.signal_resolution.check_domain_reachable`, whichever
   `signal_resolution.py` actually imports it as, see Task 2) added, not a
   change to their assertions. This keeps their original intent (testing
   denylist/normalization logic) isolated from the new reachability
   dependency, the same isolation principle `test_opencorporates.py` uses
   between `_search_companies`-level tests and `fetch()`-level tests.
9. **Scope.** Only `resolution.py`, `signal_resolution.py`, and their two
   test files. No changes to `SignalResolutionRepositoryPort`, no
   persistence of a reachability-check watermark or history, no
   concurrency (ADR-0003 bounded thread pools are not needed, this ticket
   processes one domain per `resolve_signal()` call, don't add a thread
   pool speculatively), no parking-page detection (Constraint 4), no
   changes to `gold/`.

---

## Task 1: `check_domain_reachable()` in `resolution.py`

**Files:**
- Modify: `src/huginn/elt/silver/resolution.py`
- Test: `tests/elt/silver/test_resolution.py` (existing file, add tests)

**Interfaces:**
- Produces: `check_domain_reachable(domain: str, timeout: float = 5.0) -> bool`,
  a plain module-level function, importable from
  `huginn.elt.silver.resolution`. This is the only new public symbol Task 2
  consumes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/elt/silver/test_resolution.py` (check its existing imports
first, this file currently tests `normalize_domain`; add `requests` and
`check_domain_reachable` imports, and a `resolution` module import for
`monkeypatch.setattr(resolution.requests, ...)` style patching):

```python
import ipaddress
import socket

import requests

from huginn.elt.silver import resolution
from huginn.elt.silver.resolution import check_domain_reachable


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _patch_dns(monkeypatch, ip: str):
    """Point getaddrinfo at a fixed IP so the SSRF pre-check and the
    reachability call see a deterministic address."""
    monkeypatch.setattr(
        resolution.socket,
        "getaddrinfo",
        lambda host, port: [(None, None, None, None, (ip, port))],
    )


def test_check_domain_reachable_true_on_head_2xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")  # public IP, example.com-range
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(200)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_true_on_head_3xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(301)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_head_4xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(404)
    )

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_falls_back_to_get_on_405(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(405)
    )
    monkeypatch.setattr(
        resolution.requests, "get", lambda url, timeout, headers: _FakeResponse(200)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_dns_failure(monkeypatch):
    def _raise(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(resolution.socket, "getaddrinfo", _raise)

    assert check_domain_reachable("this-does-not-exist.invalid") is False


def test_check_domain_reachable_retries_once_on_timeout_then_succeeds(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    calls = {"n": 0}

    def flaky_head(url, timeout, headers):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.Timeout("slow")
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", flaky_head)

    assert check_domain_reachable("example.com") is True
    assert calls["n"] == 2


def test_check_domain_reachable_false_after_two_consecutive_timeouts(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")

    def always_timeout(url, timeout, headers):
        raise requests.Timeout("slow")

    monkeypatch.setattr(resolution.requests, "head", always_timeout)

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_sends_a_browser_user_agent(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    seen_headers = {}

    def fake_head(url, timeout, headers):
        seen_headers.update(headers)
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", fake_head)

    check_domain_reachable("example.com")

    assert "Mozilla" in seen_headers.get("User-Agent", "")


def test_check_domain_reachable_false_for_loopback_address(monkeypatch):
    _patch_dns(monkeypatch, "127.0.0.1")

    assert check_domain_reachable("localhost") is False


def test_check_domain_reachable_false_for_link_local_metadata_address(monkeypatch):
    _patch_dns(monkeypatch, "169.254.169.254")

    assert check_domain_reachable("metadata.internal.invalid") is False


def test_check_domain_reachable_false_for_private_rfc1918_address(monkeypatch):
    _patch_dns(monkeypatch, "10.0.0.5")

    assert check_domain_reachable("internal.invalid") is False
```

Run `uv run pytest tests/elt/silver/test_resolution.py -v` and confirm every
new test fails (the function doesn't exist yet / does nothing yet). This is
the required "watch it fail" step, don't skip it.

- [ ] **Step 2: Implement `check_domain_reachable`**

Add to `src/huginn/elt/silver/resolution.py`. Exact behavior, not just a
sketch:

1. Add `import ipaddress`, `import socket`, `import requests` at module top
   (alongside the existing `from urllib.parse import urlparse`).
2. Module constant: `REACHABILITY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"`
   (Global Constraint 2).
3. A private helper `_resolves_to_public_address(domain: str) -> bool`:
   call `socket.getaddrinfo(domain, 443)`, catch `socket.gaierror` and
   return `False` (DNS failure = not reachable, per the ticket). For every
   resolved address in the result, parse it with `ipaddress.ip_address`
   and reject (return `False`) if any is `.is_private`, `.is_loopback`,
   `.is_link_local`, or `.is_reserved` (Global Constraint 1). Return `True`
   only if at least one resolved address is a normal public address.
4. `check_domain_reachable(domain: str, timeout: float = 5.0) -> bool`:
   - Call `_resolves_to_public_address(domain)` first; return `False`
     immediately if it returns `False` (covers both DNS failure and the
     SSRF guard in one path).
   - Otherwise attempt `requests.head(f"https://{domain}", timeout=timeout, headers={"User-Agent": REACHABILITY_USER_AGENT})`.
   - On a `requests.Timeout` or `requests.ConnectionError`: retry the same
     call once (Global Constraint 3). If the retry also raises either of
     those, return `False`. Any other `requests.RequestException` on
     either attempt: return `False`, no retry (a confident negative, not a
     transient one).
   - If the HEAD response's `status_code` is `405`, retry with
     `requests.get` at the same URL, same headers, same timeout, same
     one-retry-on-timeout/connection-error handling.
   - Return `True` if the final response status is in `200..399`
     (2xx or 3xx), `False` otherwise (4xx/5xx).
5. Docstring on `check_domain_reachable` citing Jira KAN-62 for the overall
   design, and this plan's Global Constraints 1, 3, 4 by number for the
   SSRF-TOCTOU limitation, the transient-retry mitigation, and the
   parking-page exclusion, each in one sentence, not restated in full.

Run the tests again, confirm all pass. Run `uv run ruff check
src/huginn/elt/silver/resolution.py tests/elt/silver/test_resolution.py &&
uv run ruff format --check src/huginn/elt/silver/resolution.py
tests/elt/silver/test_resolution.py` and fix anything it flags.

- [ ] **Step 3: Commit**

One commit, message describing what was added and why (KAN-62), no
Claude/Anthropic attribution (repo CLAUDE.md).

---

## Task 2: Wire `check_domain_reachable` into `resolve_signal()`

**Depends on:** Task 1 (`check_domain_reachable` must exist and be
imported).

**Files:**
- Modify: `src/huginn/elt/silver/signal_resolution.py`
- Modify: `tests/elt/silver/test_signal_resolution.py` (existing file,
  update every test listed below, add new ones)

**Interfaces:**
- Consumes: `check_domain_reachable(domain: str, timeout: float = 5.0) -> bool`
  from `huginn.elt.silver.resolution` (Task 1).
- `resolve_signal()`'s public signature
  (`resolve_signal(source: str, source_stable_id: str, website: str | None) -> tuple[str, str]`)
  does not change. Its behavior does: a domain must now also pass
  `check_domain_reachable` to earn `DOMAIN_NORMALIZED`.

- [ ] **Step 1: Update the import and write the new failing tests**

In `signal_resolution.py`, change:
```python
from huginn.elt.silver.resolution import KeyDerivation, normalize_domain
```
to:
```python
from huginn.elt.silver.resolution import (
    KeyDerivation,
    check_domain_reachable,
    normalize_domain,
)
```

In `tests/elt/silver/test_signal_resolution.py`, add these new tests
(alongside the existing ones, don't replace the file):

```python
def test_resolve_signal_returns_unresolved_when_domain_is_not_reachable(
    monkeypatch,
):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: False
    )

    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_normalizes_when_domain_is_reachable(monkeypatch):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "acme.com"
    assert confidence == KeyDerivation.DOMAIN_NORMALIZED


def test_resolve_signal_checks_reachability_on_the_normalized_domain(monkeypatch):
    """The domain passed to check_domain_reachable must be the normalized
    host (no scheme/path), not the raw website string."""
    seen = {}

    def fake_check(domain, timeout=5.0):
        seen["domain"] = domain
        return True

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fake_check)

    resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert seen["domain"] == "acme.com"


def test_resolve_signal_does_not_check_reachability_for_a_denylisted_host(
    monkeypatch,
):
    """A denylisted host is rejected before reachability is ever checked,
    no network call should be attempted for it at all."""

    def fail_if_called(domain, timeout=5.0):
        raise AssertionError("check_domain_reachable should not be called")

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fail_if_called)

    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com/jobs/view/42"
    )

    assert confidence == KeyDerivation.UNRESOLVED
```

Add `from huginn.elt.silver import signal_resolution` to this test file's
imports if not already present (needed for `monkeypatch.setattr(signal_resolution, ...)`).

Run `uv run pytest tests/elt/silver/test_signal_resolution.py -v` now.
The four new tests above should pass or fail meaningfully (the
"does-not-check" and "checks-the-normalized-domain" ones can only be
written meaningfully once Step 2 wires the call in, it's fine if they fail
for the right reason at this point). Every **existing** test that calls
`resolve_signal` with a normalizable, non-denylisted website and expects
`DOMAIN_NORMALIZED` will now attempt a real network call once Step 2 lands
the wiring, unless patched. Those tests, by name, are:
- `test_resolve_signal_normalizes_a_normalizable_domain`
- `test_resolve_signal_still_normalizes_a_real_company_domain`
- `test_resolve_all_combines_hn_and_yc_staged_signals_into_the_upsert_count`
- `test_resolve_all_upserts_a_record_wired_to_what_resolve_signal_computed`
- `test_resolve_all_returns_the_total_written_count`
- `test_resolve_all_opens_the_repository_scope_once_for_the_whole_batch`

For each, add `monkeypatch` as a parameter if it doesn't already have one,
and add this as the test's first line:
```python
monkeypatch.setattr(
    signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
)
```
Do not change any of these tests' existing assertions, only add the patch
line and the `monkeypatch` parameter (Global Constraint 8). Tests that
already only exercise denylisted/None/empty-website paths (e.g.
`test_resolve_signal_returns_unresolved_when_website_is_none`,
`test_resolve_signal_rejects_a_denylisted_ats_host`, and the other
denylist tests) do not need this patch, `check_domain_reachable` should
never be called for those inputs once Step 2 lands (see the
`test_resolve_signal_does_not_check_reachability_for_a_denylisted_host`
test above, which asserts exactly that).

- [ ] **Step 2: Wire the check into `resolve_signal`**

Change `resolve_signal`'s body from:
```python
    if website:
        domain = normalize_domain(website)
        if domain and not _is_non_company_host(domain):
            return domain, KeyDerivation.DOMAIN_NORMALIZED
    return (
        unresolved_placeholder_key(source, source_stable_id),
        KeyDerivation.UNRESOLVED,
    )
```
to:
```python
    if website:
        domain = normalize_domain(website)
        if (
            domain
            and not _is_non_company_host(domain)
            and check_domain_reachable(domain)
        ):
            return domain, KeyDerivation.DOMAIN_NORMALIZED
    return (
        unresolved_placeholder_key(source, source_stable_id),
        KeyDerivation.UNRESOLVED,
    )
```
Update `resolve_signal`'s docstring: add one sentence noting the domain
must now also pass `check_domain_reachable` (cite Jira KAN-62), and one
sentence citing this plan's Global Constraint 3 for why a transient
network failure is retried once inside `check_domain_reachable` rather
than distinguished at this layer (don't restate the reasoning, cite it).

Run `uv run pytest tests/elt/silver/test_signal_resolution.py -v` again,
confirm every test (old and new) passes. Run
`uv run pytest` (full suite) to confirm nothing else broke. Run
`uv run ruff check . && uv run ruff format --check .` and fix anything
flagged.

- [ ] **Step 3: Commit**

One commit, message describing the wiring change (KAN-62), no
Claude/Anthropic attribution.
