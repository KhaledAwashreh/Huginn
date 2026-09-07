# CORDIS (EU Research Results) Data Extraction API

Source: EU Publications Office / European Commission. Docs fetched 2026-09-05 from:
- https://cordis.europa.eu/about/dataextractions-api (overview / ToS)
- https://cordis.europa.eu/dataextractions/api-docs-ui (Swagger UI)
- https://cordis.europa.eu/dataextractions/api-docs (raw OpenAPI 3.0 spec, v1.1.0)
- https://cordis.europa.eu/about/dataextractions/en (equivalent UI feature)
- https://cordis.europa.eu/search (facet/filter reference)
- https://data.europa.eu/data/datasets/cordish2020projects (underlying dataset docs)

## Access

- **Auth**: API key ("DET API key"), obtained from the CORDIS DET API support page (`https://cordis.europa.eu/user/api/en`). That page requires being logged in — CORDIS accounts are provisioned via **EU Login** (`webgate.ec.europa.eu`), so onboarding is: create an EU Login account → create a CORDIS profile → generate API key. This is a real, if mild, friction step — not a self-serve instant API key.
  - Regenerating the key is possible but **destroys extraction history** tied to the old key.
- **Cost**: Free. CORDIS states the API "is completely free of use."
- **Important shape of this API — it is a job-based bulk extraction API, not a live per-record query API.** The OpenAPI spec (`v1.1.0`) exposes exactly five operations, all under `/api/dataextractions/`:

  | Method | Path | Purpose |
  |---|---|---|
  | GET | `getExtraction` | Kicks off (or retrieves) an extraction job. Params: `query` (required, free-text search string — see Querying below), `key` (required, API key), `outputFormat` (required, enum: `xml`, `csv`, `json`, `xlsx`, `summary`), `archived` (optional bool, include archived content) |
  | GET | `getExtractionStatus` | Poll job status. Params: `key`, `taskId`. Returns `progress`, `numberOfRecords`, `numberOfRecordsEstimated`, `numberOfProcessedRecords`, `remainingTime`, `averageSpeed`, and `destinationFileUri` (populated once the extract is ready to download) |
  | GET | `listExtractions` | List all extraction jobs for the API key |
  | GET | `cancelExtraction` | Cancel a running job (`key`, `taskId`) |
  | DELETE | `deleteExtraction` | Delete a completed/cancelled job (`key`, `taskId`) |

  In other words: you submit a search query and desired output format, CORDIS asynchronously builds a file (CSV/XML/JSON/XLSX/summary), and you poll until `destinationFileUri` appears, then download that file. There is no `GET /projects/:id` or `GET /organizations?country=DE` style endpoint — everything comes back as a bulk file matching your query, same mechanism as the "Extract all search results" button in the logged-in web UI.

- **Rate limits**: No published numeric quota. The ToS language is deliberately vague: "CORDIS sets and enforces limits on your use of all its APIs (e.g. limiting the number of API requests that you may make...) in our sole discretion," and the Publications Office "reserves the right to suspend temporarily or permanently" access for ToS violations. High-volume use beyond unstated standard limits "must obtain CORDIS express consent." Bottom line: treat this as an unspecified soft/fair-use limit enforceable at the provider's discretion — build in backoff and don't assume headroom.
- Non-logged-in / anonymous access exists only through the plain web UI (`cordis.europa.eu/search`), which caps at 50 records/page and only exports the current page (XML/CSV) — the full "extract all results" flow (any volume, JSON/XLSX included) requires being logged in, same as the API.

## Response shape

The API itself doesn't publish a data-model schema (its OpenAPI spec only documents the job-control endpoints above) — the payload schema is whatever CORDIS's underlying project/organisation dataset produces, in your chosen `outputFormat`. Based on the CORDIS data model exposed via the search UI facets and the parallel bulk-download dataset ("CORDIS - EU research projects under Horizon 2020," `data.europa.eu/data/datasets/cordish2020projects`), a project record includes at minimum:

- **Project-level**: internal CORDIS project ID / RCN, acronym, title, objective/abstract, status, start date, end date, total cost, EU/EC max contribution, framework programme (e.g. H2020, Horizon Europe), funding scheme (type of action), legal basis, call ID, topic ID(s), EuroSciVoc (Field of Science) classification, grant DOI, content update/signature dates.
- **Participant organisation-level** (one row per org per project in the organisations sub-dataset): project ID/acronym linkage, organisation ID, organisation name, role (coordinator vs. participant), country, city/NUTS region, activity type (e.g. HES/PRC/REC/PUB), SME flag, EC contribution to that org, total cost for that org, organisation URL, active/end-of-participation flag.
- Related sub-datasets also exist for deliverables, publications, IPR/patents, and report summaries — these are separate collections, not embedded in the project record.

Query filtering (the `query` string passed to `getExtraction`) mirrors the facets on the live search UI (`cordis.europa.eu/search`), which groups filters as:
- **Content**: Collection, Domain of Application, Language, Programme, Last updated
- **Project**: Acronym/ID, Field of Science (EuroSciVoc), Start/End date, Total cost, EU contribution, Call ID, Topic ID
- **Organisation**: Name, Country/Territory, Region
- Plus an "include archived content" toggle (CORDIS archives events >5 years old and content tied to programmes closed >10 years)

The exact query grammar (field names / operators, e.g. `contenttype='project' AND country='DE'`) isn't published in the OpenAPI spec itself — it needs to be reverse-engineered from the URL CORDIS generates when you apply filters in the web search UI, or obtained via the Help Desk.

## Freshness / cadence

- The parallel bulk-download datasets are stated to be **produced monthly**, and CORDIS explicitly warns that "inconsistencies may occur between what is presented on the CORDIS live website and the datasets" — i.e., the live site/API extraction is more current than the monthly bulk dumps, but neither is real-time relative to grant signature.
- Project data lags actual EU funding decisions by an unspecified administrative/publication delay (grant signature → CORDIS record creation is not instantaneous).

## Signal mapping (proposed Bronze fields)

| Bronze field | CORDIS source |
|---|---|
| `source_system` | `"cordis"` |
| `source_record_id` | project ID / RCN |
| `raw_payload` | full extracted record (JSON/XML/CSV row) as returned by `destinationFileUri` |
| `org_name` | organisation `name` |
| `org_country` | organisation `country` |
| `org_role` | `role` (coordinator/participant) — strong signal: coordinators are more likely decision-makers |
| `funding_amount` | project `total_cost` / `ec_max_contribution`, or org-level `ec_contribution` |
| `programme` | `framework_programme` (e.g. Horizon Europe) |
| `topic` | `topic_id` / EuroSciVoc classification |
| `milestone_date` | project `start_date` / `end_date` / signature date |
| `signal_type` | `"eu_research_grant"` |
| `ingested_at` | extraction job completion timestamp |

## Open questions / risks

- **No documented query grammar** — the free-text `query` param's exact syntax (operators, field names, boolean logic) isn't in the OpenAPI spec; needs empirical discovery once a key is obtained, or a support-desk request.
- **No numeric rate limit published** — can't size a polling/backoff strategy in advance; risk of silent throttling or account suspension under "sole discretion" language.
- **Job-based, not real-time** — this is unsuitable for low-latency "new milestone just happened" alerting; it's better suited to periodic (e.g. weekly/monthly) bulk sync jobs that then get diffed against prior Bronze snapshots.
- **EU Login onboarding friction** — requires a real personal/organisational EU Login account, not just an email+API-key signup; worth doing once, ahead of the later phase, rather than at ingestion time.
- **Field-level schema unconfirmed against the live API** — the record shape above is inferred from the adjacent bulk-dataset documentation and UI facets, not from an actual sample `getExtraction` response (which requires a key). Validate exact field names once a key is provisioned.
- **Coverage scope** — CORDIS covers EU Framework Programme–funded research (FP7/H2020/Horizon Europe) only; it will not surface non-EU-funded companies, national grants, or private funding rounds — treat as one signal among several, not a general company-discovery source.
