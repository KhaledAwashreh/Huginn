# VC Portfolio Boards (Sequoia, a16z, Index, Greylock)

## Access

**Headline finding: only 1 of the 4 firms is actually Getro-powered.** The prior assumption ("several of these run on Getro") does not hold up under direct inspection (checked live, 2026-09-05). Summary:

| Firm | Board URL (live, checked 2026-09-05) | Platform | Getro? |
|---|---|---|---|
| Sequoia | `jobs.sequoiacap.com/jobs` | **Consider** (consider.com) | No |
| a16z | `jobs.a16z.com` | Custom in-house (Next.js) | No |
| Index Ventures | `indexventures.getro.com/jobs` | **Getro** | **Yes** |
| Greylock | `jobs.greylock.com/jobs` → redirects to `greylock.com/jobs/portfolio-jobs/` | Custom in-house (Next.js/Vercel) | No |

Details per firm:

**Sequoia** (`jobs.sequoiacap.com/jobs`) — page metadata reads `<meta name="keywords" content="Consider, Talent Sourcing, Recruiting" />`, its `og:image` and legal links resolve to `consider.com` (`consider.com/legal/privacy`, `consider.com/legal/terms`, `product.consider.com/ctc/talent-circle`). This confirms the vendor is **Consider**, a separate VC-talent-network SaaS product, not Getro — the two are easy to conflate since both are white-label "VC portfolio jobs board" platforms with a similar look. The page's data is loaded via a per-board bundle at a path like `/mendel/<long-opaque-base64-ish-id>/boards` ("Mendel" appears to be Consider's internal engine/product name). This bundle is a browserify/CommonJS **JavaScript** payload (`content-type: application/javascript`, ~1.8MB), not clean JSON — grepping it for `graphql` and `algolia` turned up nothing, and no `/api/*` REST paths were found either in the page HTML or this bundle. `robots.txt` is permissive (`Allow: /`; only `LinkedInBot` is disallowed).

**a16z** (`jobs.a16z.com`) — a custom-built Next.js 14 app (`x-powered-by: Next.js`, `x-fah-adapter: nextjs-14.0.21`, `cache-tag: ...:frontier-jobs-a16z`). No `getro.com` or `consider.com` references appear anywhere in the full page source (checked the complete HTML, not just `<head>`). Notably, this is a **different** product from a16z's own recruiting/talent-network platform, "a16z Talentplace" (`talentplace.a16z.com`) — that one runs on AWS App Runner with its own S3-hosted profile-image buckets and is a distinct internal talent-matching tool, linked from the jobs board's nav but not the source of its job listings. `robots.txt` for `jobs.a16z.com` is fully permissive (`Allow: /`).

**Index Ventures** (`indexventures.getro.com/jobs`) — **confirmed Getro**, directly on a `getro.com` subdomain. Page pulls assets from `cdn.getro.com` (including a Next.js `_buildManifest.js`/chunk structure with `pages/jobs-*.js`), loads analytics via `an.getro.com/analytics.js`, uses Filestack-hosted icons (a common Getro asset pattern), and links to Getro's own marketing page `www.getro.com/vc` ("#1 Job Board & Warm Intro Solution for Venture Capital"). `robots.txt`: `Allow: /` but with `Crawl-delay: 1` and a published `Sitemap: https://indexventures.getro.com/sitemap.xml`.

**Greylock** (`jobs.greylock.com/jobs`) — returns a Cloudflare 301 to `greylock.com/jobs/portfolio-jobs` (then a Vercel 308 to the trailing-slash form). The resolved page is Next.js, hosted on Vercel (`server: Vercel`), and — like a16z — has **no** `getro.com`/`consider.com` references anywhere in its full page source. Unlike the other three, it's folded directly into Greylock's own marketing site rather than served from a vendor-branded subdomain. **Notable risk finding**: `greylock.com/robots.txt` explicitly disallows a list of named bots including **`ClaudeBot`**, plus `GPTBot`, `CCBot`, `Bytespider`, `Google-Extended`, `Amazonbot`, `Applebot-Extended`, `meta-externalagent`, and `CloudflareBrowserRenderingCrawler` — while a blanket `Content-Signal: search=yes, ai-train=no, use=reference` still allows generic search-engine indexing. This is a genuine, source-cited constraint for any Claude-Agent-SDK-based crawler and should be resolved deliberately, not assumed away.

**Aside — Getro's separate "Community Job Board":** `community.getro.com/companies/<slug>` (e.g. `.../andreessen-horowitz`, `.../greylock-2`, `.../index-ventures`) is a *different* Getro product — a cross-firm aggregator that a16z, Greylock, and Index Ventures (but seemingly not Sequoia) all appear to participate in, independent of whether the firm's own branded board runs on Getro. It uses the same `__NEXT_DATA__` JSON pattern described below. This is a potential alternate/supplementary access path but its coverage/completeness relative to each firm's official board is unverified in this pass — flagged as a follow-up, not relied on here.

## Response shape

Fully confirmed only for the one directly-Getro-powered board (Index Ventures); Sequoia/a16z/Greylock could not be characterized in this pass (see Open questions).

**Getro (Index Ventures) — access mechanism**: Getro's Next.js pages server-render the *entire* current page's data into a `<script id="__NEXT_DATA__">` JSON blob. No separate REST/GraphQL call is needed to read a page's data — fetch `https://indexventures.getro.com/jobs?page=N` (or `/companies?page=N`), parse that one script tag, and read `props.pageProps.initialState`. This matches independent community reporting found via search ("Getro's job data can be accessed through HTML scraping that parses `__NEXT_DATA__`, then `initialState.jobs.found`"). No distinct `/api/jobs`-style REST endpoint was found by direct probing (`/api/jobs`, `/api/v1/jobs`, `/jobs.json`, `/api/search/jobs` all 404).

Job record shape — `initialState.jobs.found[]` (live sample, trimmed):

```json
{
  "id": 92291872,
  "organization": {
    "id": 76746,
    "name": "Nourish",
    "slug": "nourish",
    "stage": "series_c",
    "headCount": 5,
    "logoUrl": "https://cdn.getro.com/companies/....png",
    "industryTags": ["AI Infrastructure", "Health Care", "Telehealth", "..."],
    "topics": []
  },
  "title": "Senior Revenue Accountant",
  "locations": ["Remote", "New York, NY, USA"],
  "searchableLocations": ["Remote", "New York, NY, USA", "United States", "North America"],
  "locationDetails": [{"name": "Remote", "areaType": "global", "point": null}, "..."],
  "workMode": "remote",
  "seniority": null,
  "skills": [],
  "compensationPublic": true,
  "compensationAmountMinCents": null,
  "compensationAmountMaxCents": null,
  "compensationCurrency": null,
  "compensationPeriod": "period_not_defined",
  "compensationOffersEquity": null,
  "createdAt": 1788601274,
  "source": "career_page",
  "url": "https://boards.greenhouse.io/usenourish/jobs/5415909008",
  "slug": "92291872-senior-revenue-accountant",
  "hasDescription": true,
  "featured": false
}
```

Key observations:
- **No portfolio-firm-attribution field on the job or organization record itself.** Attribution to "which VC firm" is implicit in *which network you queried* (`indexventures.getro.com`), surfaced separately at the top level as `props.pageProps.network` (`{id, name: "Index Ventures", label: "indexventures", domain: "indexventures.com", ...}`). An adapter must record which board it hit, not expect a per-job "investor" field.
- **No `domain` field on the job's `organization` object.** The job-list payload gives `organization.name`/`.slug`/`.id`/`.logoUrl` but not a company website domain. `url` is the *application* link and typically points at the company's ATS (Greenhouse, Lever, etc.), not its marketing domain.
- **`domain` only appears on the separate `/companies` directory page** (`initialState.companies.found[]`), which includes richer company-level fields: `domain` (e.g. `"1stdibs.com"`), `description`, `activeJobsCount`, `stage`, `headCount`, `locations[]`, `industryTags[]`. To get a company's real domain for a given job, you must join by `organization.id` between the `/jobs` and `/companies` payloads — it is not a single-request lookup.
- **`createdAt`** is a Unix timestamp; sampled values were close to the fetch date, consistent with an actively-refreshed board rather than a static snapshot.
- **`source: "career_page"`** indicates Getro sourced this listing from the company's own careers page/ATS feed (vs. e.g. manual entry), which is relevant to freshness reasoning below.
- A "job function"/department-style filter exists in the UI (`jobFunctionFilter`, `customFilters`, `jobFunctions` keys are present in `initialState`), implying department/function data exists somewhere in Getro's model, but it was not directly observed populated in the sampled job records — needs confirmation with a larger sample before relying on it.

**Sequoia (Consider) and a16z/Greylock (custom)**: no equivalent open, structured payload was found in this pass. Sequoia's data lives inside an opaque bundled-JS asset rather than JSON; a16z's and Greylock's Next.js apps almost certainly fetch data via internal RSC/API calls not resolvable from static HTML alone (would need browser devtools network capture or deeper JS reverse engineering to find, which is out of scope here). Treat their field shape as **unknown/TBD** pending a follow-up pass.

## Freshness / cadence

- **Index Ventures (Getro)**: the board is large and clearly actively maintained — **11,325** total open jobs reported by `initialState.jobs.total` at time of check, not a small hand-curated list. `createdAt` timestamps on sampled jobs were close to the check date, and `source: "career_page"` implies Getro polls each portfolio company's own careers page/ATS rather than relying on manual curation — consistent with a continuously/periodically re-crawled board rather than a batch-published one. The exact re-poll interval is not publicly documented and was not empirically measured here (would require repeat polling over multiple days).
- No network-level "last updated" timestamp was found, so per-record staleness can only be inferred from `createdAt`, not confirmed against a documented SLA.
- **Sequoia / a16z / Greylock**: no equivalent per-record timestamp was accessible in this pass (data not in a directly inspectable JSON shape), so cadence could not be characterized for these three. Flag as unknown pending deeper access work.

## Signal mapping (proposed Bronze fields)

Based on the confirmed Getro shape (Index Ventures); the same target schema should generalize to any future Getro-powered board, and — once their shapes are reverse-engineered — likely to Sequoia/a16z/Greylock too, since the underlying signal (a company hiring, backed by a specific firm) is the same regardless of vendor.

| Bronze field | Source value (Getro) | Notes |
|---|---|---|
| `source_name` | `"vc_portfolio_board_getro"` (or a per-firm variant) | distinguish from a future `vc_portfolio_board_consider` source once Sequoia is reverse-engineered |
| `source_url` | job's own detail page (`https://<network>.getro.com/jobs/<slug>`) | construct from `slug`; the `url` field is the *application* link (often a third-party ATS), keep both distinctly |
| `firm_name` | `network.name` (e.g. `"Index Ventures"`) | the investing/curating VC firm — comes from which board was polled, not a per-job field |
| `entity_name_raw` | `organization.name` | company name as Getro has it |
| `entity_getro_id` | `organization.id` | stable per-network numeric id; needed to join `/jobs` → `/companies` for domain |
| `domain_raw` | `companies.found[].domain` (join by `organization.id`, **not** present on the job record itself) | requires a second request/page against `/companies`; do not assume the job payload alone gives domain |
| `signal_type` | `"hiring"` | constant for this source family |
| `job_title_raw` | `title` | |
| `job_function_raw` | unconfirmed — likely present via `jobFunctions`/`customFilters` facets, not verified populated on sampled records | confirm with a larger sample before relying on it |
| `location_raw` | `locations[]`, `searchableLocations[]`, `locationDetails[]` | free text + limited structure (`areaType`, lat/long `point` when resolved) |
| `work_mode_raw` | `workMode` (e.g. `"remote"`) | |
| `seniority_raw` | `seniority` | frequently null in samples — confirm value distribution |
| `compensation_raw` | `compensationPublic`, `compensationAmountMinCents`/`MaxCents`, `compensationCurrency`, `compensationPeriod`, `compensationOffersEquity` | mostly null/undisclosed in samples; keep as-is for the rare populated case |
| `company_stage_raw` | `organization.stage` (job record) or `companies.found[].stage` (directory) | e.g. `"series_c"` — useful stage/sector proxy per the task's intent |
| `sector_raw` | `organization.industryTags[]` / `companies.found[].industryTags[]` | Getro's own taxonomy, needs mapping to Huginn's canonical taxonomy in Silver |
| `posted_at_raw` | `createdAt` (Unix ts) | semantics = when Getro surfaced/ingested the listing, not necessarily the company's original post date — treat as a proxy, not ground truth |
| `application_url_raw` | `url` | often a third-party ATS URL (Greenhouse/Lever/etc.), useful as a secondary corroboration signal (e.g. confirms which ATS a company uses) but not a domain source |
| `ingested_at` | Bronze ingestion timestamp | stamp on every fetch; no per-record "last modified" beyond `createdAt` |
| `raw_payload` | full `initialState.jobs.found[i]` object (plus the matching `companies.found[]` entry when joined) | keep both raw, unjoined and joined, since the join step is a Bronze-adjacent enrichment, not something Getro provides atomically |

## Open questions / risks

- **The "one generic Getro adapter for all four firms" premise does not hold as stated.** Only Index Ventures was confirmed Getro-powered in this pass; Sequoia runs on **Consider** (a different, structurally distinct vendor — opaque JS bundle, no JSON/GraphQL endpoint found), and a16z and Greylock both run **fully custom in-house** Next.js apps with no discovered public data contract. Recommendation for adapter design: build **one Getro-family adapter** (parameterized by network subdomain, e.g. `{network}.getro.com`) since it's genuinely generic and reusable — Getro claims 700+ VC platform teams as customers, so this pattern will likely recur for other firms beyond these four — but treat Sequoia/a16z/Greylock as **separate, lower-confidence backlog items** requiring their own reverse-engineering pass (or explicit deprioritization) rather than folding them into the same adapter.
- **Greylock's `robots.txt` explicitly disallows `ClaudeBot` by name** (alongside GPTBot, CCBot, Bytespider, Google-Extended, Amazonbot, Applebot-Extended, meta-externalagent, CloudflareBrowserRenderingCrawler), while still signaling `Content-Signal: ai-train=no, use=reference`. This is a genuine, source-cited constraint on a Claude-Agent-SDK-based crawler specifically and needs a deliberate decision before automated ingestion (e.g., different client identification policy, manual/human-triggered ingestion only for this one source, or excluding Greylock from automated Bronze ingestion entirely) — not something to route around silently.
- **ToS were not reviewed for any of the four sites in this pass**, only `robots.txt`. All four `robots.txt` files found were otherwise permissive for generic crawling (Sequoia: `Allow: /`, blocks only LinkedInBot; a16z: fully open; Index Ventures/Getro: open with `Crawl-delay: 1`). Per the pattern already established for the YC directory source (see `sources/yc-directory.md`), an open `robots.txt` does not imply an open ToS — this should be checked explicitly (Consider's, Getro's, a16z's, and Greylock's respective terms) before building scheduled ingestion, especially for Sequoia and Index Ventures where the vendor (Consider/Getro) rather than the firm itself technically operates the site.
- **Getro job records give no direct company domain** — `domain` only exists on the separate `/companies` directory payload, joined by `organization.id`. Any Getro adapter needs to plan for a two-request-type shape (jobs pages + companies pages) rather than assuming one page type is sufficient, which has implications for how "one generic Getro adapter" should be scoped (it needs both endpoints, not just `/jobs`).
- **Job function/department field existence is assumed, not confirmed** — the Getro UI exposes a job-function filter, implying the field exists in the underlying data model, but it wasn't observed populated in the small sample pulled here. Needs a larger sample before the Bronze schema commits to it as reliably present.
- **Freshness/cadence for Getro is inferred, not measured** — `createdAt` values looked recent and the board is large and clearly live, but no repeat-polling experiment was run to empirically determine how often a given company's listing changes on Getro's side. Should be measured directly once ingestion is built (e.g., diff two polls a week apart).
- **Sequoia's Consider-based `/mendel/<opaque-id>/boards` path returns bundled JS, not JSON** — extracting structured data would likely require either headless-browser network capture (to see what XHR/fetch calls the bundle makes once executed) or deeper static JS reverse engineering. No clean low-effort win was found here; flag as a higher-effort, lower-priority item relative to the confirmed-Getro path.
- **The Getro "Community Job Board" (`community.getro.com`) is a separate, unverified alternate path** — a16z, Greylock, and Index Ventures each have a company page there, aggregating across the wider Getro VC network rather than being scoped to one firm's own portfolio. Whether its data is a superset, subset, or just a differently-curated view of each firm's own board (and whether it includes firm-attribution as a field, which the per-firm boards notably lack) was not verified — worth a dedicated look before assuming the per-firm dedicated boards are the only or best path.
