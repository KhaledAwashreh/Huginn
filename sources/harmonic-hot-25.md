# Harmonic "Hot 25"

## Access

Published as a **webpage** (marketing/editorial page), not a PDF or blog post in Harmonic's main blog — lives at a dedicated URL pattern: `harmonic.ai/hot-25-startups/<quarter>-<year>` (e.g. `q3-2025`, `q4-2025`, `q1-2026`, `q2-2026`, `q3-2026`), with a parallel/alternate slug pattern also observed (`harmonic.ai/hot-25-companies/<quarter>-<year>`). Historical editions back to at least Q1 2025 are browsable via on-page navigation.

**Partially gated**: the page displays some content openly, but full current-quarter rankings are gated behind an email signup ("Sign up to access this quarter's rankings before anyone else"). Older/past-quarter editions appear more fully visible without gating based on what was fetched.

**No dedicated API for the Hot 25 itself.** Harmonic's core product does have a real, full-featured API (REST + GraphQL, base URL `api.harmonic.ai`, plus a hosted MCP server with 40+ tools per public docs) covering company search, enrichment, saved searches, lists, and bulk data export/warehouse sync. However, nothing found indicates the Hot 25 list specifically is exposed as an API endpoint or dataset — it reads as a **marketing artifact built from Harmonic's internal platform data**, not a first-class API resource. The Hot 25 is described as being derived from "aggregated investor interest from thousands of VCs using Harmonic" — i.e., it's a proprietary internal ranking output, published editorially on a cadence, not a queryable object.

Harmonic's core API/platform access is **not free**: no public self-serve pricing, no free tier, no free trial found. Third-party sources estimate entry pricing around $25,000/year with a 3-seat minimum, sold via demo + custom quote. This matters even for the Hot 25 use case — if Huginn ever wanted to go beyond the public marketing page to pull structured "hot company" signals from Harmonic's actual platform, that would mean paying for enterprise API/console access, not a lightweight integration.

## Response shape

Per-company fields observed on the Hot 25 page:

- Rank number + company name (linked externally, e.g. to company site or Harmonic profile)
- Tagline / short description (1–2 sentences)
- Founder name(s), with LinkedIn links
- Approximate headcount
- Latest funding: amount, round type, and date
- Rank change vs. previous quarter (e.g., "↑11", i.e. momentum/delta signal built into the list itself)
- Company logo/image

This is a genuinely rich, structured-looking per-company record — but it exists only as **rendered HTML on a marketing page**, not as an API response or downloadable file. Any ingestion is scrape-only, and scraping a specific gated marketing page is a much thinner attack surface than a general API (higher chance of layout drift, and it's explicitly designed as a lead-gen/marketing surface, so it may include anti-scraping friction or throttling not present on a documented API).

## Freshness / cadence

**Quarterly.** Confirmed by both the URL slugs (`q1-2025` through `q3-2026` observed) and on-page copy referring to "this quarter's rankings." This is a much lower cadence than most other Bronze sources under consideration (compare to a live/continuous feed) — good for a "notable companies this quarter" enrichment signal, not for near-real-time monitoring.

## Signal mapping (proposed Bronze fields)

If ingested (scrape of the public Hot 25 page — assuming ToS allows it and the gated portion isn't circumvented):

| Bronze field | Source value | Notes |
|---|---|---|
| `source_name` | `"harmonic_hot25"` | |
| `source_url` | edition URL, e.g. `harmonic.ai/hot-25-startups/q3-2026` | stable per-quarter URL is a nice natural "edition key" |
| `edition_period` | quarter+year parsed from URL, e.g. `2026-Q3` | use as the natural partition/versioning key for Bronze snapshots |
| `rank` | position in list (1–25) | |
| `rank_change_raw` | delta vs. prior quarter, e.g. "+11" | Harmonic already computes momentum for you — nice enrichment signal, but arrives as some as opaque changes if list membership changed (new entrant vs. numeric shift) |
| `entity_name_raw` | company name as shown | entity-resolve later against canonical company table |
| `entity_url_raw` | outbound link target (company site / Harmonic profile) | may itself require a resolution/redirect-following step |
| `description_raw` | tagline text | free text |
| `founders_raw` | founder name(s) + LinkedIn URLs | useful for entity resolution / people-graph later |
| `headcount_approx` | approximate headcount shown | Harmonic-estimated, treat as approximate not authoritative |
| `latest_funding_amount_raw` | amount as shown | currency/units need parsing — likely inconsistent formatting across entries |
| `latest_funding_round_raw` | round type (Seed, Series A, etc.) | |
| `latest_funding_date_raw` | date as shown | |
| `snapshot_date` | date of scrape | Bronze ingestion timestamp — treat `edition_period` as the "as-of" business date, and `snapshot_date` as when Huginn captured it |
| `raw_payload` | full scraped block per company | preserve raw HTML/text for reprocessing |

## Open questions / risks

- **The Hot 25 list itself is not API-accessible** — confirm this doesn't change before building anything; worth a direct check of Harmonic's API reference docs (`console.harmonic.ai/docs/api-reference/introduction`) once actual API credentials/access exist, since the docs page could not be rendered without an authenticated session during this research pass.
- **Partial gating** (email signup for "this quarter's" full list) means a naive scraper may only reliably get **past-quarter** editions in full; the current quarter may require providing an email address, which raises a policy question (is Huginn willing to sign up with an email to unlock data — and if so, is that even compatible with an automated/scheduled scraper, or does it require a one-time manual unlock per quarter?).
- **Small volume, low frequency**: only 25 companies per quarter (100/year) — this is a curated "highlight reel," not a comprehensive dataset. It's a good enrichment/credibility signal ("this company was independently flagged as hot by a VC-facing platform") layered onto other sources, not a primary lead-generation feed on its own.
- **Selection bias**: the list reflects "aggregated investor interest from thousands of VCs using Harmonic" — i.e., it's downstream of which companies venture investors are already searching for on Harmonic's platform. This skews toward venture-backable, hype-cycle-aligned companies (a lot of AI-native startups in the observed editions) and will systematically miss bootstrapped, non-VC-track companies — worth noting since Huginn's actual lead-gen use case may care about a broader company set than "what VCs are currently hot on."
- **No stable company IDs** — same entity-resolution burden as Ramp: names/URLs need matching against canonical records, and companies can reappear across quarters under the same or slightly different display name.
- **ToS / scraping risk**: this is explicitly a lead-gen/marketing page for Harmonic's paid product; scraping it programmatically (especially past an email-gate) should be checked against Harmonic's terms before implementation — flagging as a legal/compliance open question rather than assuming it's fine.
- **If budget ever allows full Harmonic platform access** (~$25k/yr class of spend), the *real* structured signal worth pursuing is Harmonic's actual company search/enrichment API (growth signals, funding, headcount trends across their whole database) — the Hot 25 marketing page would become redundant at that point, since editorial "Hot 25" picks are just a hand-picked subset of what the full platform already tracks.
