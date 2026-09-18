# EU-Startups (eu-startups.com)

Source of truth for Bronze-layer ingestion design. Verified live against the
site on 2026-09-16, via both the Chrome browser and plain `curl`.

Historical context: an earlier session investigated this source and reached
several conclusions, but that session was cut off by rate limiting before
anything was committed (no ticket, no doc, no code). Those findings were
recovered from a local transcript file and treated as unverified claims, not
fact, until re-checked here (KAN-63). Several turned out to be wrong or
incomplete — corrections are called out explicitly below rather than silently
folded in, so the record of what changed isn't lost.

## Access

- **Base URL**: `https://www.eu-startups.com/`. Standard WordPress site
  running the WP Business Directory Plugin (WPBDP) for the startup database,
  Yoast SEO for sitemaps.
- **`robots.txt`**: `https://www.eu-startups.com/robots.txt` — wide open
  (`Disallow:` empty for `User-agent: *`), declares
  `Sitemap: https://www.eu-startups.com/sitemap_index.xml`. Confirmed live.
- **Auth**: none. No API — this is HTML-only, no JSON endpoint discovered.
- **Bot mitigation — corrected finding**: the prior session concluded this
  site needed real browser navigation because plain `curl` got progressively
  blocked (403s, a Cloudflare "Managed Challenge") after repeated automated
  requests. Re-tested live: bare `curl` (default UA) gets an immediate `403`
  with a `cf-mitigated: challenge` header on the **very first request**, for
  every URL tried (`robots.txt`, `sitemap_index.xml`, a listing sitemap, a
  listing page) — not something that builds up after repetition. But adding
  one ordinary browser `User-Agent` header to the exact same `curl` call gets
  a clean `200` immediately, every time, no JS execution, no browser, no
  repetition needed:
  ```
  curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36" <url>
  ```
  This is a Cloudflare rule gating on request headers (missing/default UA),
  not real bot-behavior or TLS-fingerprint detection. **Implication for
  design**: an ordinary `requests` call with a standard desktop browser
  `User-Agent` set is sufficient. No headless browser, no agentic navigation,
  no new port — this fits `WebScrapeSourcePort` as already defined, using
  the same kind of client every other web-scrape adapter would use.

## Two distinct access surfaces

The prior session only looked at the XML sitemaps. Live exploration surfaced
a second, arguably better, surface: the directory's own search/browse UI.
Discovery and enrichment map onto two different entry points on the same
plugin, matching the split actually used in the original design discussion:

### 1. Discovery — browse `/directory/` per country

`https://www.eu-startups.com/directory/` is the live "Startup Database"
landing page: a per-country breakdown with counts (confirmed live 2026-09-16,
e.g. Germany 4563, UK 7242, France 2940, Spain 2757, Netherlands 1889,
Switzerland 1125), each country name linking to a filtered, paginated listing
view. This is the actual product surface, not a sitemap-only artifact — plain
HTML, deterministic to paginate and parse the same way `hn_staging.py` walks
HN or `yc_staging.py` walks Algolia pages.

- **Sort options** (confirmed via the "Sort By" control): Default, Business
  Name, Total Funding, Founded. No "date added"/"newest" sort is exposed in
  the UI — `Founded` is the company's founding year, not when it was listed
  on the site, so it's not usable as an incremental-crawl watermark.
- Individual listing cards on this page show Category, Based in, Tags,
  Founded — no per-card "date listed" timestamp either.
- **Pagination, confirmed live**: clicking a country (e.g. Germany) navigates
  to `https://www.eu-startups.com/directory/wpbdp_category/german-startups/`
  — a clean, predictable `wpbdp_category/<country-slug>-startups/` pattern.
  Each page holds **11 listings**; a `Next` link (when present) points to
  `.../page/2/`, `.../page/3/`, etc. With counts like Germany (4563) and UK
  (7242), that's several hundred pages per country — a real, sizeable crawl,
  not a handful of requests. **Do not compute a fixed page count from the
  live number shown on `/directory/`** (it grows over time) — walk pages
  until a page has no `Next` link.

### 2. Discovery watermark — the XML sitemaps

Since the browse UI has no listing-date field, the `wpbdp_listing-sitemap*.xml`
files (declared in `sitemap_index.xml`, Yoast-generated) remain the right
source for a `lastmod`-based incremental watermark, analogous to Bronze's
content-hash watermark but keyed on `lastmod` instead:

- **Corrected count**: 165 files confirmed live (`wpbdp_listing-sitemap.xml`
  through `wpbdp_listing-sitemap165.xml`), matching the prior session's count
  exactly.
- **Corrected size claim**: the prior session claimed "up to ~2000 URLs per
  file." Verified live, this is wrong — **200 URLs is the cap** (Yoast's own
  default sitemap page size), confirmed on `#1` (exactly 200 URLs). Not every
  file is full: `#165`, the newest at the time of this check, contains only
  **87 URLs** (it's a partial, still-filling batch). With 165 files at up to
  200 URLs each, total listings are on the order of ~30-something thousand,
  not into the hundreds of thousands the ~2000/file figure would imply.
- File #165 (newest) still spans 2026-09-01 through 2026-09-09 as of this
  check (2026-09-16) — confirms files are chunked in upload-batch order, not
  strictly one-file-per-fixed-time-window; the site simply hadn't produced
  enough new listings since 2026-09-09 to roll over to a 166th file yet as of
  this check.
- Each entry: `<url>`, `<image:image>` count, and `<lastmod>`. Example row
  from `#165`: `https://www.eu-startups.com/directory/brightroom/`, 1 image,
  `2026-09-01 07:37 +00:00`.

## Enrichment — Advanced Search by business name

`/directory/` includes an "Advanced Search" modal exposing structured filter
fields, confirmed live: **Business Name**, **Category** (dropdown, country),
**Business Description** (free text), **Based in**, **Founded** (dropdown).

**Real request shape, confirmed live** (a plain `GET`, no auth, no JS
execution needed to submit it):

```
GET /directory/?dosrch=1&q=&wpbdp_view=search&listingfields[1]=<name>&listingfields[2]=-1&listingfields[7]=&listingfields[6]=&listingfields[4]=-1
```

Field-ID mapping (WPBDP internal field IDs, confirmed by submitting the real
form): `[1]` = Business Name, `[2]` = Category, `[7]` = Business Description,
`[6]` = Based in, `[4]` = Founded. Unset dropdown fields are `-1`, unset text
fields are empty string. The plain keyword search bar on the same page hits
a simpler variant: `GET /directory/?wpbdp_view=search&kw=<term>`.

**Corrected finding — this is not an exact-match search.** Both the keyword
bar and the Advanced Search Business Name field do **substring matching**,
confirmed live: searching `Minut` via either path returns the same 9 results
("Minutes 90", "MinutesLink", "Uma Minuta", "Minutemailer", "Feminutes",
"3 Minutes Job", "3MinutesJob.com", "Minutedrone", "Minut" itself) — not
a single exact hit. The prior/initial design writeup assumed this would
behave like OpenCorporates' exact-match search API; it does not. **The
adapter must fetch the substring-matched result set and apply its own
exact-name filter client-side**, then run the "exactly one match enriches,
zero or multiple skip" rule against the filtered set, not the raw search
results. Deterministic HTML parsing either way, no LLM/agentic step needed.

## Field set on an individual listing page

Confirmed live across three real listings (`brightroom`, `minut`, `varm`) —
`https://www.eu-startups.com/directory/<slug>/`:

| Field | Presence | Notes |
|---|---|---|
| Category | Always | Country name, e.g. "Germany", "Sweden". |
| Business Description | Always | Short description. |
| Long Business Description | Usually | Longer prose version; absent on some older listings. |
| Based in | Always | City. |
| Founded | Always | Year. |
| Website | Always | Full URL, e.g. `https://thebrightroom.de`. |
| Tags | **Sometimes** | Present on newer/self-submitted listings (`brightroom`, `varm`); **absent** on older, editorially-curated listings (`minut`). Corrected finding: the prior session implied a uniform field set — it isn't uniform, treat every field past Category/Description/Based in/Founded/Website as optional. |
| Total Funding | **Sometimes** | Same pattern as Tags — present on newer listings, absent on `minut`. Free text, e.g. "Between €500K-€1 million", "No funding announced yet". |
| Company Status | **Sometimes** | e.g. "Active". Absent on `minut`. |
| Articles about `<company>` | **Sometimes** | A cross-linked list of EU-Startups news articles mentioning the company (seen on `minut`, `varm`; absent on `brightroom`). Not on the prior session's radar at all — this is effectively free related-content/funding-history signal for companies that have been covered editorially. |
| **LinkedIn** | **Not observed on any of 3 samples** | The prior session claimed a LinkedIn field existed. Not found on `brightroom`, `minut`, or `varm`. Either rare, gated behind a different listing tier, or the prior claim was simply wrong. Do not build a field mapping assuming this exists without more samples. |

Markup itself (the WPBDP template structure) is consistent across all
samples — this is what makes deterministic parsing viable — but *which
fields are populated* varies by listing age/submission path. A Silver
staging loader here should treat every field past the always-present five as
optional, the same posture `hn_staging.py` already takes toward HN's freeform
posts.

## Terms of Service

No dedicated Terms of Service / Terms and Conditions page was found: checked
the footer (no legal links present besides a cookie-consent control) and
common WordPress paths (`/terms-of-use/`, `/terms-and-conditions/` — both
404). A GDPR-style Privacy Policy exists at `/privacy-policy/`, but it
governs account-holder personal data (CLUB membership, newsletter, payment
info) — it says nothing about scraping or reuse of directory content. This
is the same shape of gap as YC's ToS question (KAN-7): robots.txt permits
crawling and no ToS was found restricting it, but "no ToS found" is not a
legal clearance — flag and move on, same posture as KAN-7, don't treat
silence as an answer.

## Design conclusion (resolves the open question from KAN-63)

Confirmed with the decision-maker (2026-09-16): discovery and enrichment are
both plain deterministic code, no new port and no agentic/LLM-assisted
browsing step for this source. `WebScrapeSourcePort` covers both:

1. **Discovery**: paginate `/directory/` by country (or use the sitemap
   listing-URL walk as the watermark source), parse listing cards/pages with
   fixed selectors — a new Silver staging loader in the same shape as
   `hn_staging.py`/`yc_staging.py`, not a new ingestion mechanism.
2. **Enrichment**: Advanced Search by business name, same shape as the
   existing OpenCorporates adapter's search-by-name-and-take-unambiguous-match
   pattern.
3. Either way, the HTTP client just needs an ordinary desktop browser
   `User-Agent` header — that alone clears the Cloudflare check confirmed
   above. No headless browser dependency needed for this source. `WebScrapeSourcePort`
   already exists (`src/huginn/elt/ingestion/ports.py`) but currently has
   **zero concrete implementations** — HN, YC, and OpenCorporates are all
   `ApiSourcePort`. This would be the first real adapter of this shape, not
   a case of reusing an already-proven pattern.
4. **Fetch mechanism: plain `requests` with a browser `User-Agent`, not
   Playwright/E2E-style navigation.** Considered explicitly and rejected for
   now: every other adapter in this codebase (HN, YC, OpenCorporates) is a
   plain HTTP client with no browser dependency, and the UA-header fix above
   was confirmed 100% reliable across every endpoint type tested (robots.txt,
   sitemap index, a listing sitemap, a listing page) with zero repetition or
   JS execution required. Adding Playwright now would be real complexity
   (a browser binary dependency, slower runs, a new failure mode) solving a
   problem a one-line header already solves — same "build it cheap now"
   posture as OpenCorporates/KAN-52. If Cloudflare later escalates past a
   header check to something that genuinely requires JS execution, that's
   the trigger to revisit this, not something to build preemptively.

## URL construction — do not guess slugs

Listing URLs are `https://www.eu-startups.com/directory/<slug>/`, where
`<slug>` is a WordPress post slug, not a deterministic function of the
company name. Confirmed live: slugs collide and WordPress disambiguates with
a numeric suffix — `logibot-2`, `offgen-2`, `aurea-hub-2`, `jobcrawls-2` all
appear in sitemap #165 alongside plain, unsuffixed slugs. A naive
`slugify(company_name)` will silently construct the wrong URL (or a
plausible-looking 404) whenever a name collision happened before this one.
**Never construct a listing URL — only ever follow one**, from a sitemap
entry, a `/directory/` pagination result, or an Advanced Search result link.
This also affects sitemap file numbering itself: the first file is
`wpbdp_listing-sitemap.xml` (no digit), not `wpbdp_listing-sitemap1.xml` —
confirmed live (the guessed `...sitemap1.xml` 301-redirects to the correct
undigited URL). Discover the real file list from `sitemap_index.xml` at
runtime; don't assume a `1..165` numeric range.

## Fetch reliability under volume

Re-tested with 20 rapid sequential `/directory/<slug>/` requests (real
listings pulled from sitemap #165), same browser `User-Agent`, no delay
between requests: all 20 returned `200`, zero escalation to a Cloudflare
challenge. This directly contradicts the historical "gets progressively
flagged after repeated requests" claim — at least at this volume, it really
is just the UA header, not a rate-sensitive rule. A production crawl should
still self-throttle out of politeness (same posture as HN's community
etiquette norms), but there's no live evidence this site's bot mitigation
escalates with request volume the way the prior session assumed.

## Open questions / risks

- **No incremental-watermark mechanism exists yet for this shape of
  adapter.** The `lastmod`-based discovery approach above assumes a
  persisted "highest sitemap file / max `lastmod` already processed" cursor,
  but Bronze's only existing watermark (`bronze/ports.py` `StatePort`,
  `bronze/watermark.py`) is a per-entity content-hash dedup keyed on
  `(source, stable_id)`, not a crawl-level cursor. Nothing in the current
  ports supports persisting that cursor across runs. This needs an explicit
  decision (extend `StatePort`, or a new mechanism) before or during KAN-64,
  not an assumption that it already exists.
- **Enrichment source conflict, not yet resolved.** `gold/ports.py`'s
  `read_unenriched_company_names` (built for OpenCorporates, KAN-53/54)
  gates on `business_sector IS NULL`, and its own docstring states that
  column "doubles as never-enriched... designed for exactly one enrichment
  source." A second enrichment source (EU-Startups, KAN-65) reusing this
  as-is would race with OpenCorporates: whichever adapter runs first and
  sets `business_sector` hides the company from the other, permanently, with
  no way to tell "enriched by OpenCorporates" from "enriched by EU-Startups"
  apart. This needs a real design decision (a per-source enrichment-status
  column, a different gating field, or an explicit priority order) before
  KAN-65 can be built as scoped, the same shape of problem the original
  build plan split into a design ticket (KAN-42) before its build ticket
  (KAN-43) rather than leaving to an implementer's judgment call.
- **Zero-overlap claim against HN/YC unverified**: the prior session claimed
  zero overlap between EU-Startups listings and 30 real companies from
  `resolved_signals`, used to argue this is a discovery source rather than an
  enrichment source. Not re-verified in this pass (would need a live DB
  query against current `resolved_signals` data) — treat as still open,
  not confirmed.
- **No ToS found is not legal clearance** (see above) — same open posture as
  KAN-7 for YC.
- **Field sparsity**: Tags/Total Funding/Company Status/Articles are all
  conditionally present; a staging loader must not assume any of them exist.
- **LinkedIn field unconfirmed**: don't build a field mapping for it without
  more samples turning it up.
- **Sitemap file count will keep growing**: 165 today; a discovery job
  should discover the sitemap index's own file list at runtime, not hardcode
  a max file number.
