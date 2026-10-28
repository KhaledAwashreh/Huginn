# Research recommendations

The authenticated `/recommendations` workspace generates a ranked research list
from an owned active discovery strategy and stores detailed feedback against the
exact assessment shown. It reuses the existing Vue/PrimeVue application, session
authentication, CSRF protection, guarded source evidence and built-in
`research-ranking-v1` scorer. FastEmbed is not enabled in this flow.

## Enable the storage

Apply the additive migration explicitly to the selected deployment database
after the existing operational and guarded evidence schemas:

```sh
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/schema/operational-recommendations.sql
```

Use the deployment's normal schema-owner and runtime-role permissions. Application
startup does not apply DDL. This change does not reset or backfill Matches. The
migration preserves existing recommendation history when reapplied. Do not apply
it to a shared database merely to run tests; tests use disposable PostgreSQL.

Build and serve the frontend using the existing
[web UI runtime](web-ui-foundation.md). Configure an offering with descriptive
topics, an ICP and an active discovery strategy in Business setup. In
Recommendations, select the strategy, generate a batch and expand a result to
review evidence and save feedback. Returning to the strategy resumes its latest
saved batch. Generation is explicit, with no scheduler, email or outreach.

## Retrieval and assessment

1. Generation snapshots the owned strategy, offering, ICP and professional
   profile. Retrieval terms come from distinct offering-name/description words
   of at least four characters, excluding common generic words. At most 24
   terms are retained in sorted order and recorded in the snapshot. This is
   `topic-overlap-v1`, an initial lexical baseline, not a contextual language
   model. Short abbreviations, synonyms and different wording can be missed.
2. Whole-word topic matching retrieves at most 200 companies from
   `gold.current_source_evidence`, ordered by distinct matching term count and
   Company UUID before the limit. Metadata preferences are not hard retrieval
   gates. The limit bounds the candidate pool, not the full database count.
3. Evidence uses the preceding 365 days through the generation timestamp.
   Undated events are retained, future event/observation dates are excluded,
   and the guarded view removes stale or withdrawn source observations.
   Complete eligible descriptions are saved, including companion observations
   that did not match a topic. Timing uses only a matching source's original
   event date. Observation time never refreshes the event's age.
4. Topic overlap supplies `adjacent` service fit (12/40), with an inferred basis.
   It does not establish an internal problem, direct service fit, buying role,
   budget or outsourcing demand. Business context remains `unknown` (0/30),
   with an unknown basis. The resulting evidence confidence is `low`.
   Repeated words or more excerpts do not raise the service-fit component.
5. Each known industry, size or country preference match adds 5 points.
   Unknown attributes and preferences do not exclude a company. Country names
   and ISO aliases use the installed `pycountry` reference, with UK mapped to
   GB. Region preferences have no inferred membership and remain unknown.
   Explicit company, matching industry and matching country exclusions apply.
   Undefined region or unrecognized country exclusions fail generation with
   HTTP 422 rather than silently ignoring the restriction; choose explicit
   recognized countries for this baseline.
6. The built-in ranker applies its existing timing, deduplication and seeded
   exploration policy. Generation returns up to 20 results, default 10. No
   minimum score is imposed. This baseline's maximum is 42/100 because it
   deliberately supplies no direct service-fit or business-context judgment.
   Low scores are research candidates, not rejection or buying probabilities.

The assessed-input [ranking operator](research-ranking.md) still supports richer
reviewed assessments and optional FastEmbed. It is separate from this initial
connected baseline. The original creation-only Matches workflow remains available
with its original state, notes and source evidence.

## API and stored feedback

All routes use the current session's User, never a submitted owner ID. Unsafe
requests require the existing session-bound `X-CSRF-Token`. Responses, including
errors, use private no-store caching. OpenAPI includes the request/response
schemas and the frontend consumes generated types.

| Route | Result |
| --- | --- |
| `POST /api/v1/recommendations` | Generate and save a batch from `strategy_id` and optional `limit`; HTTP 201 |
| `GET /api/v1/recommendations/latest?strategy_id=UUID` | Resume the owned strategy's latest saved batch |
| `GET /api/v1/recommendations/{batch_id}` | Read a saved owned batch |
| `GET /api/v1/recommendations/{batch_id}/feedback` | Read its feedback history |
| `POST /api/v1/recommendations/{batch_id}/feedback` | Append a judgment for a displayed `recommendation_id`; HTTP 201 |

Feedback records usefulness (`useful`, `not_useful`, `unsure`), reason codes,
corrected assumptions/missing context, next step, later outreach outcome and
notes. Reasons cover service/company fit, timing, geography, incorrect evidence,
customer-versus-buyer confusion, already-known information and other concerns.
Submitting another judgment adds history; it does not replace earlier feedback
or alter a score. Outcomes are user-reported and do not trigger contact.

Every generation has a separate batch UUID. The snapshot retains the exact
profile, company display data, source text/quotes/dates, supplied assessment,
algorithm version, scores and recommendation IDs. Feedback is scoped by both
batch and recommendation ID. Database constraints verify owner and occurrence;
history tables reject updates and deletes. Subsequent profile/source changes or
strategy deletion cannot rewrite the evaluated batch. This append-only history
also requires a separate future retention/erasure policy; no deletion UI is
included in this slice.

## Verification limits

Disposable-database HTTP verification used complete archived public source
descriptions, reconstructed test Bronze envelopes, new observation IDs and
synthetic users/offerings. Test feedback was explicitly simulated. Browser
layout checks used mocked API responses. These checks establish implementation
behavior and preservation, not customer usefulness, contact, demand or a fresh
upstream fetch. Customer feedback is now collectable; it is not yet training
data that changes the ranking automatically.
