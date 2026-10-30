# Research ranking operator

Run explicit source-linked batches with `python -m huginn.matchmaking.presentation.ranking_cli`.
This research capability ranks operator-supplied assessments without connecting
to a database. It does not update Matches, integrate with the live matcher,
automatically assess business context, compose digests, send email or persist
feedback. Source selection and assessment remain operator work for this JSON command.
The connected browser/API path is documented in
[Research recommendations](research-recommendations.md).

`research-ranking-v1` produces relevance heuristics, not buying probabilities,
verified consulting demand or validated recommendation quality. The optional adapter has passed an actual CPU inference smoke check.
Recommendation quality has not been established by that check. Its weights, model and
transform are research decision candidates pending evaluation.

## Prepare input

Save this complete synthetic example in ignored local storage. Replace its
profile and source material with the actual reviewed snapshots for research.

```json
{
  "schema_version": 1,
  "profile_reference": "operator-profile-v1",
  "profile_snapshot": {
    "offering": "API integration consulting",
    "preferences": {"industry": "software", "size": "small"}
  },
  "assessment_method": "operator-reviewed-v1",
  "as_of": "2026-10-28T12:00:00Z",
  "limit": 5,
  "seed": "research-2026-10-28",
  "assessments": [
    {
      "company_id": "11111111-1111-4111-8111-111111111111",
      "assessment_id": "22222222-2222-4222-8222-222222222222",
      "service_fit": "plausible",
      "business_context": "specific_context",
      "service_basis": "inferred",
      "context_basis": "observed",
      "industry_match": "match",
      "size_match": "unknown",
      "country_match": "unknown",
      "observations": [
        {
          "observation_id": "33333333-3333-4333-8333-333333333333",
          "description": "We build software for small teams. We are expanding our public API and hiring an integration engineer.",
          "occurred_at": "2026-10-20T12:00:00Z",
          "observed_at": "2026-10-21T12:00:00Z",
          "source": "synthetic-company-page",
          "source_url": "https://example.com/company"
        }
      ],
      "evidence": [
        {
          "observation_id": "33333333-3333-4333-8333-333333333333",
          "quote": "We are expanding our public API"
        }
      ],
      "relevant_observation_ids": ["33333333-3333-4333-8333-333333333333"],
      "timing_observation_id": "33333333-3333-4333-8333-333333333333",
      "unknowns": ["Whether external consulting is wanted"],
      "rationale": "API expansion makes integration consulting plausible; hiring does not establish consulting demand.",
      "restrictions": []
    }
  ]
}
```

1. `profile_snapshot` must be a nonempty JSON object. Preserve the offering and
   preferences actually used; `profile_reference` alone cannot reproduce them.
   `assessment_method` records the supplied assessment procedure. Neither is
   automatically checked against stored user settings.
2. Include complete original source descriptions in `observations`, with UUID,
   source name, source URL and nullable timezone-aware `occurred_at` and
   `observed_at`. Preserve original text, not just keywords or quoted excerpts.
   Completeness and provenance are operator responsibilities: validation checks
   structure and links, not source truth or URL reachability.
3. Evidence quotes must be nonempty exact substrings of their source description
   and at most 25 whitespace-separated words. Each relevant observation needs
   quoted evidence. All evidence and restriction references must resolve within
   the assessment. Observation IDs and evidence entries cannot repeat within it.
4. `relevant_observation_ids` is nonempty. `timing_observation_id` is `null` or
   one of those IDs. Timing uses its event time, not an unrelated source's date
   or observation time.
5. `as_of` requires a timezone. Both supplied dates of every evidence-linked
   source, including restriction evidence, must be at or before `as_of`.
   Unknown dates may be `null`. Future unreferenced observations remain in the
   snapshot but are omitted from semantic text.
6. Supply all example fields, even empty arrays and nullable timing. UUID fields
   are UUID strings. Unknown fields, duplicate JSON keys and nonfinite numbers
   are rejected. Input is bounded to 16 MiB and 5,000 assessments; integer
   `limit` is 1 through 100. Assessment IDs must be unique. A company can have
   several assessments.

## Run the CLI

Assessed mode needs no model. Use input and output paths in an existing ignored
local directory:

```sh
rtk uv run python -m huginn.matchmaking.presentation.ranking_cli \
  --input /tmp/ranking-input.json --output /tmp/ranking-output.json
```

Omit `--output` to write JSON to stdout. Output files are created exclusively;
existing snapshots are never overwritten. Exit codes are 0 for success, 2 for
invalid input or unavailable files, and 1 for other ranking/model failures.
Sanitized JSON errors on stdout use `invalid_ranking_input`,
`ranking_file_unavailable` or `ranking_unavailable`.

Optional semantic mode replaces only service-fit points. Add a nonempty
top-level `semantic_query`, for example `"API integration consulting for small
software teams"`, then install the optional CPU dependency and run:

```sh
rtk uv sync --extra ranking
rtk uv run python -m huginn.matchmaking.presentation.ranking_cli \
  --input /tmp/ranking-semantic-input.json \
  --output /tmp/ranking-semantic-output.json \
  --reranker fastembed --model-cache /tmp/huginn-ranking-model-cache
```

Model loading may download assets. The adapter uses FastEmbed 0.9.1 with
`Xenova/ms-marco-MiniLM-L-6-v2`, CPU execution and two threads. It scores all
as-of-eligible source descriptions ordered by observation UUID, without a
keyword prefilter. Text exceeding the model context is split into complete
character passages fitting alongside the query; the maximum passage logit is
the document logit. It does not assess business context or consulting demand.

The CLI accepts queries up to 10,000 characters, subject also to model context.
The adapter rejects more than 200 documents, 200,000 characters per document,
2,000,000 total characters or 1,024 passages instead of silently dropping text.
Input/evidence/as-of validation precedes optional model loading.

## Interpret scores

Total relevance is the sum of these four components, from 0 through 100.
There are no qualitative total-score tiers.

| Component | Input label or band | Points |
|---|---|---:|
| Service fit, maximum 40 | `direct` | 40 |
| | `plausible` | 28 |
| | `adjacent` | 12 |
| | `unknown`, `unrelated` | 0 |
| Business context, maximum 30 | `explicit_change` | 30 |
| | `specific_context` | 20 |
| | `general_context` | 10 |
| | `unknown` | 0 |
| Company preferences, maximum 15 | Each industry, size, country `match` | 5 each |
| | Each `mismatch` or `unknown` | 0 |
| Timing, maximum 15 | Relevant event age at most 30 days | 15 |
| | More than 30, at most 90 days | 12 |
| | More than 90, at most 180 days | 9 |
| | More than 180, at most 365 days | 6 |
| | More than 365 days | 3 |
| | No timing source or unknown event time | 0 |

Semantic mode replaces service-label points with `round(40 * sigmoid(logit))`,
recorded as `sigmoid-to-40-v1`. This heuristic scaling is not a calibrated
probability. Other components and evidence bases still come from the assessment.

Confidence is distinct from score. Both `service_basis` and `context_basis`
accept `observed`, `inferred` and `unknown`. Confidence is `low` when either is
`unknown`, otherwise `medium` when either is `inferred`, otherwise `high`.
It describes evidence basis for relevance, not source-truth verification or
buying probability. Semantic points do not upgrade confidence.

## Restrictions and selection

Each restriction supplies `scope`, `status`, boolean `applies_to_hypothesis`,
nonempty `reason`, and `evidence` using the same exact-quote and source-ID rules.

1. Scopes are `proposed_engagement`, `advertised_job`, `contact_route` and
   `unknown`. Statuses are `conflict`, `compatible` and `unknown`.
2. Only a `proposed_engagement` restriction with `status: "conflict"` and
   `applies_to_hypothesis: true` excludes that assessment. Job-only and
   contact-route restrictions do not automatically exclude consulting work.
3. Unknown scope/status, or a proposed-engagement conflict whose applicability
   is false, yields `unresolved` unless exclusion takes precedence. Other
   restrictions yield `not_applicable`; an empty list yields `none`.
   Unresolved restrictions do not deduct points or exclude the candidate.
4. Eligible assessments sort by descending total, then confidence (`high`,
   `medium`, `low`), Company UUID and assessment UUID. The best eligible
   assessment represents each company. A company is in `excluded_company_ids`
   only when all its assessments are excluded.
5. Exploration can fill every fifth displayed slot. With capacity
   `min(limit, eligible company count)`, reserve `floor(capacity / 5)` slots.
   The tail starts after the first `capacity - reserved` ranked companies.
   Tail candidates qualify with medium/low confidence and service label
   `direct`, `plausible` or `adjacent`. A hash of algorithm version, seed and
   assessment ID chooses them deterministically for positions 5, 10 and so on.
   Unfilled exploration slots return to ordinary ranking. Exploration therefore
   may surface lower-scoring companies but never exceeds 20% of the display.

## Preserve and replay

Output includes the complete `input_snapshot`, all `scored_candidates`, selected
`recommendations`, breakdowns, confidence, unknowns, rationale and source-linked
evidence. Restrictions and complete source descriptions remain in the input
snapshot. Recommendations have position, `selection_type` (`exploitation` or
`exploration`) and stable `recommendation_id`. `ranking_id`, `input_fingerprint`,
algorithm version, seed and `as_of` identify a run. Requested exploration slots
are `floor(limit / 5)`; actual slots can be lower because of available capacity
or eligible tail candidates.

Extract `input_snapshot` into a new input file to replay through the assessed
CLI. Semantic snapshots already contain paired `semantic_service_logit` and
`semantic_model_reference`, so replay requires no model download. These fields
must appear together; logits must be finite, and the original nonempty
`semantic_query` is required whenever a precomputed score is present. Preserve the recorded reference:
it includes FastEmbed version, model name, weights hash, tokenizer hash and
passage aggregation version. With a `semantic_query` and no reranker, each
nonexcluded assessment needs a precomputed pair. A configured reranker rejects
eligible precomputed scores rather than silently replacing them.

Canonical assessment order, UTC timestamps, profile JSON and hashes make the
same input reproducible under the same algorithm version. Fresh model execution
can depend on assets/runtime; retain logits for exact replay. Keep snapshots
and research artifacts in ignored local storage. The separate connected workspace persists recommendation occurrences and
feedback against these identities. This JSON command performs no database
writes; recommendation quality still needs actual customer feedback.
