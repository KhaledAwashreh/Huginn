# Read-only company attribute assessment

The assessment identifies missing company attributes supported by current source
evidence and measures their effect on synthetic matching criteria. It produces
proposals, abstentions and conflicts. It does not update company attributes or
create Matches.

## Prerequisites

Use a target where the source-currentness and current-source-evidence schemas
have already been deployed and sources reconciled. The command fails when its
guarded view or required tables are unavailable. It never deploys schemas or
reconciles inputs automatically. See [source currentness](source-currentness.md)
for those separate operations. For a pre-deployment assessment, clone stored
inputs into an owned disposable database and reconcile that clone.

Set `HUGINN_DATABASE_URL` using the existing environment mechanism. The reader
needs `USAGE` on `gold` and `silver`, and `SELECT` on these columns:

| Relation | Columns |
| --- | --- |
| `gold.company` | `id`, `business_sector`, `company_scale`, `country` |
| `gold.current_source_evidence` | `company_id`, `source`, `source_stable_id`, `observation_id`, `occurred_at` |
| `silver.source_lifecycle_observation` | `id`, `company_id`, `source`, `stable_id`, `snapshot_id`, `raw_token`, `resolution_token`, `context_version`, `policy_version` |
| `silver.source_context_snapshot` | `id`, `source`, `stable_id`, `parser_version`, `source_fields` |

It requires no write privileges, operational user data, or direct Bronze access.
Each connection uses repeatable-read, read-only transactions with a bounded
statement timeout (30 seconds by default). The initial company and evidence reads
share one transaction. Counterfactual queries use only the captured inputs, so
later source or company changes cannot alter a report midway through evaluation.

## Run an assessment

Supply explicit timezone-aware inclusive window endpoints:

```bash
uv run python -m huginn.elt.gold.presentation.cli.attribute_assessment \
  --cutoff 2026-09-01T00:00:00Z \
  --as-of 2026-10-01T00:00:00Z \
  --summary .local-runtime/assessment/report.json \
  --receipts .local-runtime/assessment/receipts.json
```

The default synthetic criterion is B2B, size `0-10`, country `USA`. It is a
mechanical comparison, not a recommendation for a service offering. Use
`--criteria PATH` to provide a JSON object of named synthetic criteria:

```json
{
  "small_german_b2b": {
    "industries": ["B2B"],
    "company_sizes": ["0-10"],
    "countries": ["Germany"],
    "excluded_industries": [],
    "excluded_countries": [],
    "excluded_company_ids": []
  }
}
```

Required positive arrays must be nonempty. Company sizes use the existing four
bands: `0-10`, `11-100`, `101-1000`, `1001+`. Excluded company IDs are UUID strings.
Use synthetic inputs: criterion names and taxonomy strings appear in the summary.
The programmatic `run_assessment` API accepts several named windows and criteria
and captures the source input once for all comparisons.

`--limit N` selects the first N companies in UUID order, including companies with
no current evidence. Its report is explicitly a sample; it cannot establish
whole-corpus coverage. Without a limit, all Gold companies are in the denominator.

Summary output contains aggregate counts, criteria, window endpoints, mapping
versions and a fingerprint of the captured company and evidence inputs. Without
`--summary`, it goes to stdout. Optional receipts include company/source IDs,
original and proposed values, source fields, snapshot and observation IDs, and
source input versions. File outputs are written atomically with permissions
`0600`. Keep receipts and raw-data replay artifacts under ignored local storage.
Do not commit them. Command errors expose only the error type, not the database
URL or source text.

## Mapping rules

- YC headcount uses the existing size bands. Zero is valid; negative, boolean,
  string and fractional headcounts are invalid. Missing or null stays unknown.
- YC industries use the explicit industry array, removing empty and
  `Unspecified` labels. Tags and descriptions do not create sectors.
- Country rules use reviewed literal country labels. They preserve source text;
  country aliases are a separate counterfactual. YC multi-location and remote
  entries abstain. EU category alone cannot establish country: the place must
  explicitly corroborate it. A city alone does not establish a country.
- HN employment text supplies no automatic company country, sector or headcount.
  EU tags and descriptions supply no automatic sector or size.

Only missing fields can receive proposals. Meaningful existing values are
preserved. Disagreements between current sources, invalid supported evidence,
and disagreements with existing Gold values are reported for review. There is
no last-row or source-order precedence. Every proposal has source lineage and
a company input token. These are assessment receipts, not durable write or
rollback records.

## Interpret the result

`before` and `after` compare candidate company sets with the production matcher
predicate: guarded current evidence, original source event time, industry, size,
country and exclusions. Country matching remains trimmed, case-insensitive exact
text. The comparison uses PostgreSQL over captured inputs and is checked against
the production candidate repository in disposable integration tests.

The alias counterfactual is reported separately after fills. It normalizes US/USA/
United States and UK/United Kingdom variants on companies, positive countries
and excluded countries together. It can remove candidates when an exclusion
starts matching. It does not change the production matcher.

Gate failure counts overlap; they are diagnostic counts, not a funnel. Missing
attribute coverage, companies, and source observations have separate denominators.
Per-source field outcomes describe the companies covered by each source; a company
with several sources may appear in more than one cohort. The adapter reads only
guarded facts; a separate source audit must distinguish upstream absence from
fields dropped during staging or resolution. Unguarded inputs are not silently
treated as trustworthy facts.

An additional eligible company is not proof of consulting demand or a probability
of success. A country fill may leave sector or size unknown and therefore add no
matches. Zero additional candidates is a valid result. Before any write-capable
promotion, review actual source examples and benefit, and design durable
provenance, input-version checks, rollback and regular-writer interaction.
