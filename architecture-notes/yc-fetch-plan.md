# YC Adapter Fetch Plan (KAN-39)

Translates `docs/sources/yc-directory.md` into the concrete choices `src/huginn/ingestion/adapters/yc.py`'s `fetch()` needs to be implemented against (KAN-30). Cites that document by section rather than restating its research.

**KAN-7 (YC ToS legal exposure) is not resolved by this note.** It stays open regardless of which access path is chosen below, per architecture document section 5 ("the legal exposure underneath that choice has not been closed out") and `docs/sources/yc-directory.md`'s Open questions/risks section, bullet 1. Nothing here is a legal judgment; it is a build-plan decision made on the assumption that KAN-7 will be resolved (or explicitly risk-accepted) separately before `fetch()` ships to a schedule.

## 1. Access path: direct Algolia call, not `yc-oss/api`

Decision: query Algolia directly with the frontend's secured search key. Do not route through the `yc-oss/api` mirror.

Reasons:

1. Architecture document section 5 already names this as the Phase 0 design ("YC: direct Algolia search-key query" in the adapter diagram, and the adjoining prose). This note keeps that design rather than reopening it; it does not introduce a second decision-maker for the same call.
2. The access primitives needed for a direct call (app ID, both index names, the tag filter) were independently confirmed against the live page on 2026-09-05, not just inferred from third-party writeups (`docs/sources/yc-directory.md`, Access, and Open questions/risks bullet 4). The mirror adds a dependency on top of research Huginn has already verified firsthand.
3. `yc-oss/api` refreshes once a day (`docs/sources/yc-directory.md`, Freshness/cadence). A direct call lets Huginn's own polling cadence be the freshness bound instead of inheriting someone else's schedule.
4. `yc-oss/api`'s README documents no ToS/legal analysis of its own (`docs/sources/yc-directory.md`, Access, community precedent bullet). Routing through it does not launder the legal question: per that same section, `yc-oss/api` is "explicitly built against the Algolia index rather than scraping," meaning it does the same kind of programmatic Algolia access this adapter would do directly, just from a different IP under a different name. Choosing the mirror over a direct call is not a way to sidestep KAN-7, and this note does not treat it as one.
5. Cost of the alternative: a third-party GitHub Pages JSON mirror with no SLA, undocumented update guarantees beyond "daily," and a schema that could drift or the project could go stale/disappear without notice. Direct access removes that dependency at the price of owning the Algolia call itself.

This does not touch the ToS-vs-robots.txt question (`docs/sources/yc-directory.md`, Open questions/risks bullets 1-2). It only picks which technical path the adapter uses once/if that question clears.

## 2. Algolia query parameters

Endpoint: `POST https://45BWZJ1SGC-dsn.algolia.net/1/indexes/YCCompany_production/query`

- App ID: `45BWZJ1SGC` (`docs/sources/yc-directory.md`, Access).
- Index: `YCCompany_production`, not the `_By_Launch_Date_production` replica. `fetch()` needs the full directory, not a specific sort order; `IngestionService`/`StatePort` own change detection downstream (`src/huginn/ingestion/ports.py`, `StatePort`), so which replica returns hits first does not matter here.
- Auth: send the entire base64 secured-key string exactly as vended in `window.AlgoliaOpts.key` as the `X-Algolia-API-Key` header, alongside `X-Algolia-Application-Id: 45BWZJ1SGC`. Use the opaque signed blob, not the decoded restriction params (`analyticsTags`, `restrictIndices`, `tagFilters`); those are Algolia's own reading of the key, not a separate credential to reconstruct.
- Request body: `{"query": ""}` plus pagination params (below). An empty `query` string matches all records in scope, not a keyword search; that's what's needed for a full-directory pull rather than the search-box behavior the frontend uses this same key for.
- Do not also pass `tagFilters` in the request body. The `ycdc_public` restriction is already baked into the secured key's signature (`docs/sources/yc-directory.md`, Access); resending it risks a conflicting/redundant-restriction error rather than adding safety.
- Pagination: **plain `page`/`hitsPerPage` pagination cannot reach the full directory, confirmed live (2026-09-08)** — see below. `fetch()` must split by the `batch` facet instead: one query per batch value, each well under Algolia's per-query ceiling.

**Confirmed by a live test call (2026-09-08), replacing this section's prior unverified status:**

1. **Request/response contract confirmed exactly as documented above.** `POST https://45BWZJ1SGC-dsn.algolia.net/1/indexes/YCCompany_production/query` with `X-Algolia-Application-Id`/`X-Algolia-API-Key` headers and `{"query": "", "hitsPerPage": N, "page": N}` returns HTTP 200 with the expected envelope (`hits`, `nbHits`, `page`, `nbPages`, `hitsPerPage`). Live `nbHits` as of this call: **6204**.
2. **Pagination ceiling is real and is hit.** At `hitsPerPage=1000, page=0`, Algolia returns exactly 1000 hits with `nbPages: 1` (it silently caps at 1000 total reachable hits, not 6204/1000 pages). Requesting `page=6` at `hitsPerPage=1000` returns `nbHits: 0` and this exact error: `"you can only fetch the 1000 hits for this query. You can extend the number of hits returned via the paginationLimitedTo index parameter or use the browse method."` Since 6204 > 1000, plain pagination cannot retrieve the full directory.
3. **`browse` is not permitted with this key, confirmed live**: `POST .../browse` returns **HTTP 403, `"Method not allowed with this API key"`**. The public secured key's ACL does not include browse. This resolves the fork in this section's prior version decisively: **use per-facet split queries** (one query per `batch` facet value — e.g. `filters: "batch:'Summer 2026'"` — each comfortably under 1000 hits), not the browse endpoint. `fetch()` needs to first discover the set of batch values (a `facets` query, or a hardcoded/updated batch list) before issuing one query per batch.
4. **`id` and `objectID` match.** Live response's first hit had `id: 531` and `objectID: 531`, identical. The mapping ambiguity in section 3 below is resolved: extract `stable_id` from `id` (matches the Signal mapping table's naming), `objectID` being present and equal is incidental, not a separate source of truth.

None of this touches KAN-7 (ToS legal exposure, still open) — this was one manual test call made with the user's explicit, informed acceptance of that risk, not a resolution of the legal question, and not something to repeat routinely before KAN-7 is actually closed.

## 3. RawRecord field mapping

Per `src/huginn/ingestion/ports.py`, `RawRecord` is `stable_id: str` plus `payload: dict`, and `payload` is documented as "the raw, unmodified data as fetched."

- `stable_id`: `str(hit["id"])`. `docs/sources/yc-directory.md`'s Signal mapping table already names `id` as the `yc_id` source value and "a good natural key for this source." `RawRecord.stable_id` is typed `str`, so cast the integer.
- `payload`: the raw Algolia hit dict, unmodified, exactly as returned in the response's `hits` array entry (including any Algolia-added envelope fields such as `objectID`, `_highlightResult` if present). This matches the Signal mapping table's `raw_payload` row: "full Algolia record ... keep raw for reprocessing since YC's schema is undocumented/unversioned." Do not pre-select or flatten fields here; Silver's staging loader (KAN-34) is where field selection happens, not `fetch()`.

Confirmed live (2026-09-08, section 2 above): a raw Algolia hit's `id` and `objectID` fields match one-for-one. `stable_id = str(hit["id"])` is safe to build against.

## Reference

`docs/sources/yc-directory.md` (Access, Response shape, Signal mapping, Open questions/risks). `src/huginn/ingestion/ports.py` (`RawRecord`, `SourcePort`). `src/huginn/ingestion/adapters/yc.py` (current stub). Architecture document section 5 (Ingestion). Jira KAN-30 (consumes this note), KAN-7 (stays open, not addressed here).
