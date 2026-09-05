# OpenCorporates API

Source: OpenCorporates Limited. Docs fetched 2026-09-05 from:
- https://api.opencorporates.com/ (landing page)
- https://api.opencorporates.com/documentation/API-Reference (v0.4.8 reference, fetched in full)
- https://opencorporates.com/pricing/ (current commercial pricing, live page)

## Access

- **Auth**: API key ("API token") required for every call, passed as a query parameter: `?api_token=your_token`. No auth = calls to documented example URLs return **503**. Token comes from your OpenCorporates account page after registering an API account.
- **Free tier exists, but is conditional, not unrestricted**: API accounts are free *only* if the resulting product/dataset is itself released under the same open, share-alike attribution licence as OpenCorporates data (attribution to OpenCorporates required, and your derived database must also be shared under that licence). This is a real constraint for Huginn: a private lead-gen database for a paying consultant is not an "open data project," so the free/open tier's licence terms likely don't fit the intended use — using it would require either releasing the ingested data openly (not viable) or paying.
- **Free-tier default limits** (per the reference doc, "Usage limits" section): **200 requests/month, 50 requests/day**. Daily quota resets midnight UTC; monthly quota resets midnight UTC on the last day of the month. Check consumption via `GET /account_status?api_token=...`.
- **Paid self-serve tiers** (from the live `/pricing/` page, commercial/non-open use — removes the share-alike restriction):

  | Plan | Price | Monthly calls | Daily calls |
  |---|---|---|---|
  | Essentials | £2,250/yr (£225/mo) | 500 | 200 |
  | Starter | £6,600/yr (£660/mo) | 2,500 | 500 |
  | Basic | £12,000/yr (£1,200/mo) | 5,000 | 1,000 |
  | Enterprise | Custom (bulk delivery + bespoke API) | custom | custom |

  Note the odd inversion: the cheapest **paid** tier (500/mo, 200/day) has a higher quota than the **free** open-data tier (200/mo, 50/day) — the free tier is capped low specifically to push commercial users to a paid plan.
- **Free-at-scale exception**: OpenCorporates offers free bulk-scale access to journalists, NGOs, universities, and anti-corruption research groups on request/application — not self-serve, and not applicable to a for-profit consulting use case.
- **Rate-limit error**: HTTP 403 is returned specifically when a request is refused due to rate limiting (distinct from 401 auth failures).
- Both HTTP and HTTPS are currently supported; docs recommend HTTPS since HTTP may be deprecated and exposes the API token in plaintext.
- **Versioning**: URL-based, e.g. `/v0.4/companies/...`; omitting a version uses the current default (which can change over time) — docs explicitly recommend always pinning a version.

## Response shape

Default format is JSON (XML available). Key endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /companies/:jurisdiction_code/:company_number` | Full company detail record |
| `GET /companies/search?q=...` | Search companies by name, with facet filters |
| `GET /companies/:jurisdiction_code/:company_number/filings` | Statutory filings |
| `GET /companies/:jurisdiction_code/:company_number/officers` (via company record's `officers` field) / `GET /officers/search?q=...` | Officer/director search |
| `GET /officers/:id` | Officer detail |
| `GET /industry_codes`, `/jurisdictions`, `/jurisdictions/match` | Reference/lookup data |
| `GET /account_status` | Quota usage |

**Company search filtering is genuinely powerful** — `companies/search` supports facet params including `jurisdiction_code`, `country_code`, `company_type`, `current_status`, `industry_codes`, `registered_address` (free-text), `inactive` (bool), `branch` (bool), `nonprofit` (bool), `identifier_uids`, and date-range filters on `created_at`, `incorporation_date`, `dissolution_date`, `updated_at` (ISO 8601, range syntax like `2013-12-03:2014-05-22`). Results can be sorted by `score`, `incorporation_date`, `created_at`, `updated_at`, `dissolution_date`. Pagination via `page`/`per_page` (default 30/page).

Example request:
```
https://api.opencorporates.com/v0.4/companies/search?q=barclays+bank&jurisdiction_code=gb&current_status=Active&api_token=...
```

**Company detail record** (`GET /companies/:jurisdiction_code/:company_number`) — verified field list from the live reference doc:
- `name`, `company_number`, `jurisdiction_code`, `company_type`, `current_status`
- `incorporation_date`, `dissolution_date`, `inactive` (bool)
- `registered_address_in_full` (string) and `registered_address` (structured object)
- `previous_names`, `alternative_names`, `alternate_registration_entities`, `previous_registration_entities`, `subsequent_registration_entities`
- `industry_codes` (array), `identifiers` (array, e.g. tax/business numbers)
- `branch` / `branch_status` / `home_company` (for foreign-registered branches)
- `controlling_entity`, `ultimate_beneficial_owners`, `ultimate_controlling_company` (when known)
- `officers` (array), `filings` (array), `data` (most-recent misc data items), `corporate_groupings`
- `source` object (`publisher`, `url`, `retrieved_at` — full provenance), `registry_url` (link back to the official register), `opencorporates_url`
- `created_at`, `updated_at`, `retrieved_at` (OpenCorporates' own bookkeeping timestamps, distinct from registry dates)
- `sparse=true` query param returns a smaller/faster response omitting filings and secondary data.

**Officer record** (`GET /officers/:id`): `name`, OpenCorporates id/url, associated company, plus when known: `position`, `uid` (registry-assigned officer ID), `start_date`, `end_date`, `address`, `date_of_birth`.

## Freshness / cadence

- Every record and every officer/filing carries its own `retrieved_at` and a `source` provenance block (publisher, source URL, retrieval timestamp) — freshness is per-record and traceable, not a single global "last updated" for the whole dataset.
- `updated_at` reflects any change to the company record or its associated data (not just registry changes), so it's a reasonable "has this changed recently" signal but not a precise registry-diff timestamp.
- No stated bulk re-crawl cadence in the docs; OpenCorporates aggregates from ~140+ national/regional registries which each have their own update frequency (some daily, some far slower) — expect uneven freshness across jurisdictions.

## Signal mapping (proposed Bronze fields)

| Bronze field | OpenCorporates source |
|---|---|
| `source_system` | `"opencorporates"` |
| `source_record_id` | `jurisdiction_code` + `company_number` |
| `raw_payload` | full JSON company object |
| `org_name` | `name` |
| `org_jurisdiction` | `jurisdiction_code` |
| `org_country` | derived from `jurisdiction_code` (or `country_code` facet on search) |
| `registration_number` | `company_number` |
| `org_status` | `current_status`, `inactive` |
| `incorporation_date` | `incorporation_date` |
| `registered_address` | `registered_address_in_full` / `registered_address` |
| `industry_codes` | `industry_codes` |
| `officers` | `officers` array (name, position, dates) |
| `signal_type` | `"company_registration"` |
| `provenance` | `source` object, `registry_url` |
| `ingested_at` | request/response timestamp |

## Open questions / risks

- **Licensing is the real gate, not just quota.** The genuinely free tier requires releasing derived data under a share-alike open licence with OpenCorporates attribution — almost certainly incompatible with a private, paid consulting tool. Realistic entry cost is the **Essentials plan at £2,250/year** for only 500 calls/month (≈16/day average, hard-capped at 200/day) — thin for anything beyond spot-checking a handful of leads per week, not for bulk discovery/enrichment at scale.
- **No open-ended "discover companies founded recently in country X" firehose** — `companies/search` requires a `q` name-search term; it is not a pure filter-only browse endpoint (though facets narrow a name search considerably, you can't retrieve "all new UK companies this month" without some search term or by iterating another axis such as `industry_codes` — worth testing whether an empty/wildcard `q` is accepted).
- **Bulk data delivery (SFTP) exists but is Enterprise/sales-quote only** — no self-serve bulk pricing published; would need to contact sales for volume-based lead sourcing.
- **Coverage and freshness vary significantly by jurisdiction** since data is sourced from ~140+ different national registries with different update cadences and depths (e.g., UK Companies House is rich/frequent; many other jurisdictions are sparser).
- **Officers endpoint privacy/PII considerations** — officer records include names, positions, sometimes dates of birth and addresses; worth flagging for later data-handling/retention policy even though this is a later-phase source.
- Rate-limit numbers (200/mo free, tiered paid plans) were confirmed directly from the live reference doc and pricing page on 2026-09-05, but OpenCorporates has changed its access model before (tightening free access around 2022) — re-verify before committing to a plan at implementation time.
