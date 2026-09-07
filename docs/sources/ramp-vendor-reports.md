# Ramp Vendor/Spend Reports

## Access

Ramp publishes spend-trend content in **two distinct forms**, which matter for Bronze design because they have different granularity and different access mechanics:

1. **"Leading Indicators" blog series** — narrative blog posts at URLs like `ramp.com/leading-indicators/top-saas-vendors-on-ramp-<month>-<year>` (monthly, e.g. `top-saas-vendors-on-ramp-june-2026`) and periodic deep-dive reports like `ramp.com/reports/2026-spring-spending-benchmarks` ("Business Spending Report", seasonal). These are **plain webpages/blog posts**, not PDFs, though some reports also offer a PDF/gated download (e.g. "Spring 2026 Spending Report" download link). Free to read, no login wall on the blog posts themselves; some reports promote a Substack-style email signup but don't hard-gate the content.
2. **"Ramp Rate" vendor directory** — a standing, continuously-updated directory at `ramp.com/vendors` and per-category pages like `ramp.com/vendors/categories/crm`, `.../devops`, `.../data-warehouses`, etc. This is a **live webpage (not a periodic post)**, freely browsable, no signup/paywall observed on the pages checked.

**No public API** was found for either form. No CSV/bulk export was found on the Ramp Rate pages checked. Everything is presentation-layer HTML — any ingestion would mean scraping structured elements off the page, which is fragile (subject to markup changes, rate limiting, and ToS considerations that should be checked before building a scraper).

## Response shape

- **Leading Indicators blog posts**: mostly narrative/editorial text with embedded stats (e.g., "AI token spend per firm is up 13x since January 2025", "0.3% business adoption"). Some named vendors are called out as trending (e.g., DeepSeek, Fireworks AI, fal AI, DeepInfra, Figma) but **not in a consistent structured table** — mentions are anecdotal within prose, not a clean per-company record set every month.
- **Ramp Rate directory pages** (the more structurally useful one): per-category pages list a **ranked set of vendors** (data shown for the CRM category included Salesforce, HubSpot, Zoho, Attio, Pipedrive, with a "see more" for additional vendors). Per-vendor fields observed:
  - Vendor name + logo
  - **Adoption Rate** — % of businesses in that category (on Ramp) that purchased from this vendor in trailing 12 months
  - **Growth Rate** — period-over-period change in Adoption Rate
  - **New Adopter Rate** — % of companies adopting the vendor for the first time in trailing 12 months
  - Segment breakdowns (SMB / mid-market / enterprise adoption)
  - Implied rank/position within category

This is the closest thing to a structured, per-entity dataset Ramp publishes.

## Freshness / cadence

- Leading Indicators blog: **monthly** cadence is explicit in the text ("Every month, Ramp processes...") and confirmed by the URL pattern (`-january-2026`, `-february-2026`, `-april-2026`, `-may-2026`, `-june-2026`, `-july-2026`, etc. all exist).
- Seasonal "Business Spending Report" / benchmark reports: appear **quarterly/seasonal** (e.g., "Spring 2026 Spending Report").
- Ramp Rate directory: appears to be a **continuously updated live page**, not a dated snapshot — most recent fetch showed a date reference "as of September 2026" embedded in vendor commentary, suggesting it's refreshed on an ongoing basis rather than published as discrete periodic editions.

## Signal mapping (proposed Bronze fields)

Important caveat first: Ramp's data is fundamentally about **vendor adoption among Ramp's ~70,000+ card-holding customers**, not about the vendor companies' own growth, funding, or headcount. It is a **demand-side proxy signal** — useful for "which SaaS category/vendor is gaining share among Ramp's customer base" — not a general startup-discovery or funding signal, and it says nothing about companies that aren't themselves SaaS vendors being purchased by other businesses.

If ingested (Ramp Rate directory pages only — the blog narrative is not structured enough to map cleanly):

| Bronze field | Source value | Notes |
|---|---|---|
| `source_name` | `"ramp_vendor_directory"` | distinguish from `"ramp_leading_indicators"` if blog narrative is ever scraped |
| `source_url` | category page URL | e.g. `ramp.com/vendors/categories/crm` |
| `entity_name_raw` | vendor name as shown | needs entity resolution against canonical company records later |
| `category_raw` | Ramp's category label | e.g. "CRM", "DevOps" — Ramp's taxonomy, not necessarily Huginn's |
| `adoption_rate_pct` | Adoption Rate value | proxy for market penetration among Ramp customers only |
| `growth_rate_pct` | Growth Rate value | period-over-period signal — closest thing to a "momentum" indicator |
| `new_adopter_rate_pct` | New Adopter Rate value | leading indicator of new customer acquisition |
| `segment_breakdown_raw` | SMB/mid-market/enterprise splits, if present | optional, for later filtering by target customer segment |
| `snapshot_date` | date of scrape (page has no visible "as of" date consistently) | Bronze must stamp its own ingestion timestamp since Ramp doesn't clearly version these pages |
| `raw_payload` | full scraped HTML/DOM snippet for the vendor row | keep raw for reprocessing since layout may change |

## Open questions / risks

- **No API confirmed** — this would be scrape-only. Before building anything, check Ramp's `robots.txt` and Terms of Service for scraping restrictions; this is a commercial company's marketing property, not an open data source.
- **Coverage is SaaS/software-vendor-specific and Ramp-customer-biased.** Ramp Rate only reflects vendors purchased by companies that use Ramp's card — this skews toward venture-backed, US-based, tech-forward SMBs/mid-market companies. It is not a representative sample of the broader economy, and definitely not usable as a general "list of growing startups" — it only signals which *SaaS vendors* are gaining adoption, and only among Ramp's customer base.
- **Not a per-startup growth signal in the sense Huginn needs.** A company appearing high on Ramp Rate tells you that company (as a *vendor*) is gaining traction among other businesses' spend — this is genuinely useful for a specific slice of leads (SaaS/software companies), but it is **not usable at all** for identifying growth in companies that don't sell software Ramp customers expense (e.g., non-SaaS startups, pre-revenue startups, hardware companies, etc.). This should be scoped explicitly as a "SaaS vendor momentum" signal, not a general company-growth signal.
- **No stable per-record IDs.** Vendor names are free text; entity resolution against a canonical company table will require fuzzy matching (e.g., "Attio" -> which legal entity/domain).
- **Snapshot instability.** Since Ramp Rate looks like a live/continuously-updated page rather than dated editions, Bronze ingestion must snapshot-and-diff on its own schedule; there's no natural "edition ID" from the source to key off of, unlike the monthly blog posts which at least have a stable per-month URL slug.
- **Blog narrative form (Leading Indicators) is likely not worth structured ingestion** — it's prose with occasional named vendors, not a consistent table. If ingested at all, treat it as unstructured text for later NLP extraction, not as a first-class structured Bronze record type.
- Recommend treating Source A as **deferred and narrow-scope**: only the Ramp Rate directory pages have enough structure to be worth a scraper; the broader monthly reports are better handled (if ever) as qualitative/contextual signal rather than a per-company feed.
