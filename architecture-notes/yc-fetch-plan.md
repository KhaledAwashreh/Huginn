# YC Adapter Fetch Plan (KAN-39)

Translates `sources/yc-directory.md` into the concrete choices `src/huginn/ingestion/adapters/yc.py`'s `fetch()` needs to be implemented against (KAN-30). Cites that document by section rather than restating its research.

**KAN-7 (YC ToS legal exposure) is not resolved by this note.** It stays open regardless of which access path is chosen below, per architecture document section 5 ("the legal exposure underneath that choice has not been closed out") and `sources/yc-directory.md`'s Open questions/risks section, bullet 1. Nothing here is a legal judgment; it is a build-plan decision made on the assumption that KAN-7 will be resolved (or explicitly risk-accepted) separately before `fetch()` ships to a schedule.

## 1. Access path: direct Algolia call, not `yc-oss/api`

Decision: query Algolia directly with the frontend's secured search key. Do not route through the `yc-oss/api` mirror.

Reasons:

1. Architecture document section 5 already names this as the Phase 0 design ("YC: direct Algolia search-key query" in the adapter diagram, and the adjoining prose). This note keeps that design rather than reopening it; it does not introduce a second decision-maker for the same call.
2. The access primitives needed for a direct call (app ID, both index names, the tag filter) were independently confirmed against the live page on 2026-09-05, not just inferred from third-party writeups (`sources/yc-directory.md`, Access, and Open questions/risks bullet 4). The mirror adds a dependency on top of research Huginn has already verified firsthand.
3. `yc-oss/api` refreshes once a day (`sources/yc-directory.md`, Freshness/cadence). A direct call lets Huginn's own polling cadence be the freshness bound instead of inheriting someone else's schedule.
4. `yc-oss/api`'s README documents no ToS/legal analysis of its own (`sources/yc-directory.md`, Access, community precedent bullet). Routing through it does not launder the legal question: per that same section, `yc-oss/api` is "explicitly built against the Algolia index rather than scraping," meaning it does the same kind of programmatic Algolia access this adapter would do directly, just from a different IP under a different name. Choosing the mirror over a direct call is not a way to sidestep KAN-7, and this note does not treat it as one.
5. Cost of the alternative: a third-party GitHub Pages JSON mirror with no SLA, undocumented update guarantees beyond "daily," and a schema that could drift or the project could go stale/disappear without notice. Direct access removes that dependency at the price of owning the Algolia call itself.

This does not touch the ToS-vs-robots.txt question (`sources/yc-directory.md`, Open questions/risks bullets 1-2). It only picks which technical path the adapter uses once/if that question clears.

## 2. Algolia query parameters

Endpoint: `POST https://45BWZJ1SGC-dsn.algolia.net/1/indexes/YCCompany_production/query`

- App ID: `45BWZJ1SGC` (`sources/yc-directory.md`, Access).
- Index: `YCCompany_production`, not the `_By_Launch_Date_production` replica. `fetch()` needs the full directory, not a specific sort order; `IngestionService`/`StatePort` own change detection downstream (`src/huginn/ingestion/ports.py`, `StatePort`), so which replica returns hits first does not matter here.
- Auth: send the entire base64 secured-key string exactly as vended in `window.AlgoliaOpts.key` as the `X-Algolia-API-Key` header, alongside `X-Algolia-Application-Id: 45BWZJ1SGC`. Use the opaque signed blob, not the decoded restriction params (`analyticsTags`, `restrictIndices`, `tagFilters`); those are Algolia's own reading of the key, not a separate credential to reconstruct.
- Request body: `{"query": ""}` plus pagination params (below). An empty `query` string matches all records in scope, not a keyword search; that's what's needed for a full-directory pull rather than the search-box behavior the frontend uses this same key for.
- Do not also pass `tagFilters` in the request body. The `ycdc_public` restriction is already baked into the secured key's signature (`sources/yc-directory.md`, Access); resending it risks a conflicting/redundant-restriction error rather than adding safety.
- Pagination: `hitsPerPage` and `page`, incrementing `page` until the response's `page >= nbPages - 1`, accumulating `hits` across calls.

Two things about this section are unverified and need a live confirmation call before KAN-30 is built out, not assumed from `sources/yc-directory.md` alone:

1. The source doc confirmed the key's *existence and scope* by decoding it, but did not report actually issuing a query against the Algolia REST endpoint and inspecting a raw response (`sources/yc-directory.md`, Access, and Response shape; the latter is sourced from `yc-oss/api`'s published JSON, not a raw Algolia hit). The exact request/response contract above (body shape, header names) should be confirmed with one live test call, not shipped from this note untested.
2. Algolia's standard search endpoint has a practical pagination ceiling (commonly 1000 results reachable via `page`/`hitsPerPage` on a stock index configuration); YC's directory almost certainly exceeds that across all batches. If the total hit count returned in a first call exceeds what plain pagination can reach, `fetch()` needs either the Algolia `browse` endpoint (if this key's ACL permits browsing, unconfirmed) or a split into multiple faceted queries (e.g. one query per `batch` facet value, each well under any per-query cap). This note flags the fork; it does not resolve which branch applies, since that depends on a live count `sources/yc-directory.md` doesn't report.

## 3. RawRecord field mapping

Per `src/huginn/ingestion/ports.py`, `RawRecord` is `stable_id: str` plus `payload: dict`, and `payload` is documented as "the raw, unmodified data as fetched."

- `stable_id`: `str(hit["id"])`. `sources/yc-directory.md`'s Signal mapping table already names `id` as the `yc_id` source value and "a good natural key for this source." `RawRecord.stable_id` is typed `str`, so cast the integer.
- `payload`: the raw Algolia hit dict, unmodified, exactly as returned in the response's `hits` array entry (including any Algolia-added envelope fields such as `objectID`, `_highlightResult` if present). This matches the Signal mapping table's `raw_payload` row: "full Algolia record ... keep raw for reprocessing since YC's schema is undocumented/unversioned." Do not pre-select or flatten fields here; Silver's staging loader (KAN-34) is where field selection happens, not `fetch()`.

One mapping detail needs the same live-call confirmation as section 2: whether a raw Algolia hit's `id` field matches the mirror's `id` field one-for-one, or whether Algolia's `objectID` is the field that actually carries YC's numeric ID in the live index (`sources/yc-directory.md`'s Response shape section is sourced from the `yc-oss/api` mirror, not a raw Algolia hit, so the exact raw envelope is inferred, not directly observed). Confirm `stable_id` extraction against one real response before relying on it.

## Reference

`sources/yc-directory.md` (Access, Response shape, Signal mapping, Open questions/risks). `src/huginn/ingestion/ports.py` (`RawRecord`, `SourcePort`). `src/huginn/ingestion/adapters/yc.py` (current stub). Architecture document section 5 (Ingestion). Jira KAN-30 (consumes this note), KAN-7 (stays open, not addressed here).
