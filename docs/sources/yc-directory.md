# Y Combinator — Company Directory

## Access

`ycombinator.com/companies` is a JS app shell (React via Inertia.js — confirmed by the `X-Inertia` response header and a `data-page="{&quot;component&quot;:&quot;ycdc_new/pages/Companies/IndexPage&quot;...}"` attribute) that server-renders only an empty shell plus two props (`env`, `currentBatch`, e.g. `"Summer 2026"` as of this check). **The actual company list, search, and filters are not in the initial HTML** — they're populated client-side against a public Algolia index. This was verified directly by fetching the live page (2026-09-05):

```
window.AlgoliaOpts = {"app":"45BWZJ1SGC","key":"<base64 secured-key blob>"};
```

Decoding the `key` value (base64) yields an Algolia **secured API key**: a signature followed by URL-encoded restriction params —

```
analyticsTags=ycdc
restrictIndices=YCCompany_production,YCCompany_By_Launch_Date_production
tagFilters=["ycdc_public"]
```

So the key embedded in every page load is scoped read-only to two indices (`YCCompany_production`, `YCCompany_By_Launch_Date_production`) and can only return records tagged `ycdc_public` — i.e. YC deliberately exposes a public-safe slice of a larger internal Algolia dataset (Bookface presumably holds the rest) via a key anyone loading the page already has. This matches what community projects report using (see below) and is not a secret/leaked credential — it's shipped to every browser that loads the directory page.

**No official YC API exists.** No CSV/bulk export button was found on the directory page. The only "API" is this client-side Algolia access pattern.

**`robots.txt`** (fetched directly, 2026-09-05):

```
User-Agent: *
Disallow: /verify/*
Disallow: /library?categories=*&*
Allow: /library?categories=*
Disallow: /library?*
Disallow: /companies?*
Allow: /
```

`/companies?*` (i.e. any query-string variant of the directory, which is how batch/industry/tag filters are expressed in the UI) is disallowed for crawlers; the bare `/companies` path and `Allow: /` otherwise leave the base page fetchable. This says nothing about direct Algolia REST calls (a different host, `*.algolia.net`/`*.algolianet.com`), which robots.txt does not and cannot govern.

**Terms of Service** (`ycombinator.com/legal/`, last updated February 2024, fetched 2026-09-05) explicitly prohibits automated extraction, independent of what robots.txt allows:

> "you will not engage in or use any data mining, robots, scraping or similar data gathering or extraction methods"

and separately:

> "If you are blocked by Y Combinator from accessing the Site (including by blocking your IP address), you agree not to implement any measures to circumvent such blocking"

**This is a real constraint, not a technicality.** The Algolia key being publicly loadable does not mean querying it programmatically/on a schedule is authorized — the ToS scraping clause reads broadly enough to cover exactly that. This should be treated as a genuine access-risk item for Huginn (personal project or not) rather than waved off because "the data is public."

**Community precedent** (found, not verified beyond their own claims — treat as informative, not authoritative):
- [`yc-oss/api`](https://github.com/yc-oss/api) — publishes YC company data as static JSON via GitHub Pages, refreshed daily via GitHub Actions, explicitly built against the Algolia index rather than scraping rendered HTML. No ToS/legal discussion found in its README.
- Multiple Apify actors (`devilscrapes/y-combinator-companies-scraper`, `haketa/ycombinator-companies-scraper` — described as "Algolia Startup Directory", `jungle_synthesizer/y-combinator-scraper`, `michael.g/y-combinator-scraper`, `memo23/y-combinator-scraper`) and `corralm/yc-scraper` (Python) — commercial/hobby scrapers, corroborate the same Algolia-backed access pattern independently.
- These are secondary confirmation that the app ID / index names are stable and commonly relied upon, not proof that doing so is sanctioned by YC.

## Response shape

Confirmed against a live record pulled from `yc-oss/api`'s published JSON (which mirrors the Algolia record shape) — example (PlanGrid, W12):

```json
{
  "id": 8,
  "name": "PlanGrid",
  "slug": "plangrid",
  "former_names": [],
  "small_logo_thumb_url": "https://bookface-images.s3.amazonaws.com/small_logos/....png",
  "website": "http://plangrid.com",
  "all_locations": "San Francisco, CA, USA",
  "long_description": "PlanGrid is the leader in construction productivity software...",
  "one_liner": "Mobile applications for the construction industry.",
  "team_size": 355,
  "industry": "Real Estate and Construction",
  "subindustry": "Real Estate and Construction -> Construction",
  "launched_at": 1322045547,
  "tags": ["Construction"],
  "tags_highlighted": [],
  "top_company": true,
  "isHiring": false,
  "nonprofit": false,
  "batch": "Winter 2012",
  "status": "Acquired",
  "industries": ["Real Estate and Construction", "Construction"],
  "regions": ["United States of America", "America / Canada"],
  "stage": "Growth",
  "app_video_public": false,
  "demo_day_video_public": false,
  "app_answers": null,
  "question_answers": false,
  "url": "https://www.ycombinator.com/companies/plangrid",
  "api": "https://yc-oss.github.io/api/batches/winter-2012/plangrid.json"
}
```

Field notes:
- **Name / one-liner / description**: `name`, `one_liner` (short pitch), `long_description` (fuller free text, may include funding/founding narrative as prose — not structured funding data).
- **Website/domain**: `website` — present on essentially every launched company record; this is the one field that's *reliably* a real, checkable company URL, unlike (per prior HN research) sources where domain has to be inferred.
- **Batch/stage**: `batch` (e.g. `"Winter 2012"`, human-readable "Season Year" — API elsewhere uses short codes like `W12`/`S21`/`X25`/`F24`) and a separate `stage` field (observed values include `"Growth"`; likely also `"Early"`/`"Growth"`/`"Public"`-type buckets reflecting company maturity, not funding round per se).
- **Status**: `status` — observed values `"Active"`, `"Acquired"`; also expected `"Public"`/`"Inactive"` per community docs (not directly observed in the two records pulled, so treat as inferred, not confirmed).
- **Industry/tags**: `industry` (single primary), `subindustry`, `industries` (array), `tags` (freeform array, e.g. `["B2B", "Payroll", "Health Insurance"]`), `tags_highlighted`.
- **Team size**: `team_size` (integer headcount, self-reported by the company — freshness/accuracy unclear, no observed "as of" date on this field).
- **Location**: `all_locations` (free-text string, e.g. `"San Francisco, CA, USA"`), `regions` (array of coarser geographic buckets, e.g. `["United States of America", "America / Canada", "Remote", "Partly Remote"]`).
- **Flags**: `top_company` (boolean — YC's own "notable/top company" designation), `isHiring` (boolean), `nonprofit` (boolean), `former_names` (array — renamed companies, e.g. Gusto was `["ZenPayroll"]`).
- **Job postings**: `isHiring` is a boolean flag only — the directory does not appear to embed actual job listing data in this record; YC's separate "Work at a Startup" (`workatastartup.com`) product presumably holds structured listings but that's a distinct source not covered here.
- **Identifiers/links**: `id` (YC's internal numeric ID), `slug`, `url` (canonical `ycombinator.com/companies/<slug>` profile page), `launched_at` (Unix timestamp — appears to be "launch" date on the directory, not necessarily founding or funding date).
- Other fields of unclear use for Huginn: `app_answers` (null in samples — likely YC-application-specific, probably never public), `question_answers` (boolean), `app_video_public`/`demo_day_video_public` (booleans re: video visibility), `small_logo_thumb_url`.

## Freshness / cadence

- **Batch cadence changed in 2024–2025**: YC ran two batches/year (Winter, Summer) from 2005 through Fall 2024, then expanded to **four batches per year** — Winter (W), Spring/"X" (X, to avoid colliding with Summer's "S"), Summer (S), Fall (F) — starting in 2025. The live page confirms this: `currentBatch` returned `"Summer 2026"` on 2026-09-05, consistent with the four-batch calendar continuing.
- **Directory-wide refresh**: batch announcements happen on YC's own program calendar (now quarterly-ish), but individual company fields (`status`, `team_size`, `isHiring`, `tags`, description text) are **updated continuously/independently** — a company's status can change (e.g. to `"Acquired"`) at any time, unrelated to batch cycles. There is no visible "last updated" timestamp per record.
- `yc-oss/api` (third-party) refreshes its mirrored JSON **daily** via a scheduled GitHub Actions job and separately publishes a daily diff/changelog (`changes/latest.json`, `changes/latest.md`) — useful precedent for how often *practical* value is gained from re-polling, though it says nothing about how often YC itself actually changes underlying data.

## Signal mapping (proposed Bronze fields)

| Bronze field | Source value | Notes |
|---|---|---|
| `source_name` | `"yc_directory"` | |
| `source_url` | `url` (`ycombinator.com/companies/<slug>`) | canonical per-company profile link |
| `entity_name_raw` | `name` | also capture `former_names` for entity-resolution history |
| `domain_raw` | `website` | reliably present — strongest domain signal of any source evaluated so far |
| `description_raw` | `one_liner` + `long_description` | keep both distinctly; `one_liner` is closer to a pitch, `long_description` may embed stale/self-reported funding narrative as prose, not structured data |
| `stage_batch_raw` | `batch` | e.g. `"Winter 2012"` — treat as a *cohort/vintage* signal, not a funding-round signal |
| `stage_raw` | `stage` | separate maturity bucket (e.g. `"Growth"`) — confirm full value set before relying on it |
| `status_raw` | `status` | observed: `Active`, `Acquired`; expect `Public`/`Inactive` — confirm full enum before Silver mapping |
| `sector_raw` | `industry`, `subindustry`, `industries`, `tags` | YC's own taxonomy — will need mapping to Huginn's canonical sector taxonomy in Silver |
| `location_raw` | `all_locations`, `regions` | free text + coarse region buckets, not normalized geo |
| `team_size_raw` | `team_size` | self-reported headcount, no freshness timestamp — use cautiously as a growth proxy |
| `flags` | `top_company`, `isHiring`, `nonprofit` | booleans, cheap high-signal filters |
| `yc_id` | `id` | stable numeric ID from YC — good natural key for this source |
| `launched_at_raw` | `launched_at` (Unix ts) | ambiguous semantics (directory "launch," not founding/funding) — do not treat as founding date without more verification |
| `ingested_at` | Bronze ingestion timestamp | source has no per-record "last modified" field, so Bronze must stamp its own snapshot time and diff over time to detect changes (status flips, new batches, etc.) |
| `raw_payload` | full Algolia record (or full `yc-oss/api` JSON, if that's the actual ingestion path chosen) | keep raw for reprocessing since YC's schema is undocumented/unversioned |

## Open questions / risks

- **ToS conflict is the primary open risk, not a footnote.** YC's Terms of Service (`ycombinator.com/legal/`) explicitly bar "data mining, robots, scraping or similar data gathering or extraction methods," and separately forbid circumventing an IP block. This applies regardless of whether the Algolia key is technically public. Before building any scheduled ingestion against this source, this should be resolved deliberately (e.g., decide whether a personal/low-volume/non-commercial use case changes the risk calculus, whether to rely on a third-party mirror like `yc-oss/api` instead of hitting Algolia directly, and whether to rate-limit/identify the client honestly) — not assumed away.
- **`robots.txt` only disallows `/companies?*`** (query-string variants of the HTML page) for crawlers — it does not address direct Algolia API calls to `*.algolia.net`, which is a different host entirely and outside robots.txt's scope. Relying on "robots.txt allows it" would be an incomplete read of YC's actual position; the ToS clause is the binding constraint to weigh, not robots.txt.
- **Batch/stage alone is a weak, and now more granular, funding-recency proxy.** With YC now running four batches/year instead of two, batch resolution improved (roughly quarterly instead of semiannual), but `batch` reflects YC's own investment cohort — not a company's most recent external funding round, valuation, or round size. A company batch-tagged `"Winter 2012"` (like PlanGrid, later acquired) tells you nothing about funding recency 13 years later. `stage` (`"Growth"` observed) is a secondary, YC-assigned bucket whose full value range and update cadence are unconfirmed — needs more sampling before being trusted as a recency signal.
- **`status`, `stage`, and `team_size` enums/semantics are only partially observed** — two sample records is not enough to enumerate all values or confirm how/when YC updates them. Before finalizing Silver-layer mapping, pull a larger sample (e.g. via a chosen ingestion path) to enumerate actual `status`/`stage` value sets.
- **Community scraper claims need independent verification before build-time reliance.** The Algolia app ID (`45BWZJ1SGC`), index names (`YCCompany_production`, `YCCompany_By_Launch_Date_production`), and tag filter (`ycdc_public`) were **directly confirmed** by fetching the live page and decoding the embedded secured key on 2026-09-05 — this is primary evidence, not just trust in third-party writeups. However, the *stability* of this key (whether YC rotates it, rate-limits it, or changes index names) is unverified and should be re-checked at actual build time, not assumed to remain constant from this research pass.
- **No job-posting data in this record shape.** `isHiring` is boolean-only in the directory record; actual job listings would require a separate source (YC's Work at a Startup product) not evaluated here.
- **`long_description` is unstructured prose that may embed stale/self-reported funding figures** (e.g. "$69 million in funding from Sequoia...") — tempting to regex-extract, but this is uncontrolled free text from company-submitted profiles, not a structured, source-of-truth funding field. Should not be treated as reliable funding data without heavy caveats.
