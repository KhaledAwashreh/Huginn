# HN Fetch Plan (KAN-38)

Resolves the three open build questions for KAN-29 (`HackerNewsAdapter.fetch()`) from `docs/sources/hn-who-is-hiring.md`. Does not restate that document; cited by section. Blocks KAN-29 per `architecture-notes/kan-21-build-plan.md` section 1.

## 1. Thread discovery: `submitted[0]` only, no Algolia cross-check

Use `docs/sources/hn-who-is-hiring.md`'s Freshness method 1 only: `GET /v0/user/whoishiring.json`, take `submitted[0]`, fetch that item, confirm `title` matches `/^Ask HN: Who is hiring\? \(/`.

Reasons:

1. The title regex check is what makes this method correct, not the assumption that `submitted[0]` is the hiring thread. It already handles the "wants to be hired" companion sitting at the same or an adjacent index (Freshness section, confirmed ordering example).
2. Method 2 (Algolia) is there as a cross-check for `submitted` ordering/size, but the same section confirms live that ordering is descending-by-recency. There's no observed failure mode Algolia would catch that the title check doesn't already catch.
3. Staying on the official Firebase API keeps `fetch()` single-dependency, matching the adapter header comment ("Official Firebase API, no auth, no rate limit") and avoids taking on Algolia's separate, unofficial usage norms (Access section) for a discovery step that doesn't need them.

Judgment call, flagged: if `submitted[0]`-based discovery ever comes back empty or with a non-matching title for several consecutive scheduled runs, fall back to Algolia (method 2) rather than failing the job outright. This fallback is not built in KAN-29; it's a documented escalation path, not a code path, until it's actually needed.

Do not hardcode a day-of-month; poll (daily) per Freshness section point 3.

## 2. Recursion depth: root + top-level kids only, no nested-reply walk

`fetch()` returns one `RawRecord` for the root thread item and one `RawRecord` per direct child in the root's `kids` array. It does not recurse into any child's own `kids`.

Reasons:

1. The stub's own docstring already scopes this: "fetch the current Who's Hiring thread and its top-level comments" (`src/huginn/ingestion/adapters/hn.py`).
2. Open questions section "Top-level vs nested replies": only items whose `parent` equals the root id are company posts; anything nested under a comment is applicant Q&A / banter, explicitly "should not be treated as its own signal source." Walking deeper buys nothing and multiplies request volume for no signal (a root can have 300+ descendants once nested replies are included, vs ~300 top-level kids alone).
3. Keeps request volume aligned with the Access section's etiquette guidance (pace/cap concurrency, tens of req/s not hundreds) without needing to build a depth-limit parameter into the walk.

**Dead items** (`dead: true`): fetch and store as-is, unfiltered. Bronze is schema-on-read with no field mapping or cleaning (Arch doc section 4.1 point 2); filtering non-company noise out of `kids` is explicitly Silver's job per Open questions ("Filter/flag `dead: true` items"), not the adapter's. `fetch()` does not inspect the `dead` field at all.

**Deleted items and hard-nonexistent ids, resolved as one decision.** Two distinct API responses both mean "content `fetch()` expected is gone," at different severities: a `deleted: true` stub (`{id, deleted, parent, time, type}`, `by`/`text`/`kids` dropped) still exists as an object; a completely nonexistent id returns the bare JSON value `null`, no object at all. Treating these as two separate open questions was the wrong split; they resolve together.

1. **`deleted: true`**: fetch and store the stub as-is, same as any other item, no special-case code. This resolves the source doc's tombstone-vs-data-loss question as **tombstone, by default of the existing Bronze write behavior**: a previously-captured full item and a later-fetched deleted stub hash differently, so `RawStorePort.write()` inserts a new row rather than silently overwriting (Arch doc section 4.1 points 3-4; `ports.py` `RawStorePort.write` docstring).
2. **Bare `null`**: `fetch()` produces no `RawRecord` for that id, there's no content to store, nothing to skip-with-a-marker either. If the id was never previously captured, this is fully benign, exactly what "obviously skip it" gets right. If the id *was* previously captured (it's in Bronze from an earlier run), that row simply stops receiving `write()` calls, so its `last_checked_at` stops advancing while other ids in the same run keep getting fresh timestamps. That staleness is the tombstone signal, the same distinguishing mechanism Arch doc section 4.1 point 4 already relies on for "nothing changed" vs. "job stopped running," applied here at the single-id level instead of the whole-source level, rather than inventing a second tombstone mechanism for what is structurally the same event as case 1.

This only applies to a genuine, successful API response whose body is the JSON literal `null`. A request that fails outright (timeout, non-200, connection error, malformed JSON) is a different failure axis and must still surface as an error, never silently treated the same as "id doesn't exist."

**Concurrency**: fetch the root item first, then the top-level kids with bounded concurrency (a small cap, e.g. a semaphore around 5-10 concurrent in-flight requests), not a tight unbounded loop, per the Access section's etiquette note. Exact mechanism (async batch vs thread pool) is an implementation choice for KAN-29, not a design constraint from this note.

## 3. RawRecord field mapping

| HN item field | RawRecord field | Rule |
|---|---|---|
| `id` | `stable_id` | `str(item["id"])`. Applies identically to the root item and every top-level kid. |
| entire fetched item dict | `payload` | Stored verbatim, unmodified: no added, removed, or renamed keys, no per-post derived fields. |

No other mapping exists. This is a deliberate, narrower choice than `docs/sources/hn-who-is-hiring.md`'s "Signal mapping (proposed Bronze fields)" section, which proposes adding cheap derived fields (has-URL boolean, keyword-match flags) at ingest time. That conflicts with Arch doc section 4.1 point 2, which defines Bronze's `payload` as "close to as-fetched, no field mapping or cleaning." **Resolved in favor of the arch doc, no exception for HN**: `payload` is the raw item exactly as returned by `GET /v0/item/<id>.json`, full stop. Chosen for consistency across sources over the source doc's HN-specific proposal, since nothing is lost either way, the derived fields the source doc proposes can still be computed later at Silver from the same raw payload, and a source-specific carve-out from Bronze's "no field mapping" rule would invite the same exception for every source after HN. All of the source doc's proposed derived fields (has-URL flag, role/location substrings, keyword flags) move to Silver staging (KAN-34), not into `fetch()`.

No `stable_id`/`payload` distinction is needed to tell the root story apart from a company post: the root item has no `parent` key, every top-level kid does, and `payload` carries that verbatim.

## References

1. `docs/sources/hn-who-is-hiring.md`: Access, Response shape, Freshness / cadence, Signal mapping, Open questions / risks sections.
2. `src/huginn/ingestion/ports.py`: `RawRecord`, `SourcePort.fetch`, `RawStorePort.write`.
3. `src/huginn/ingestion/adapters/hn.py`: current stub, scope comment, KAN-21 TODO.
4. `docs/architecture.md` section 4.1 (Bronze), section 5 (Ingestion).
5. `architecture-notes/kan-21-build-plan.md` section 1 (Ingestion breakdown, KAN-38 blocks KAN-29).
6. Jira KAN-38 (this note), KAN-29 (consumer).
