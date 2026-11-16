# Research recommendations and prospects

Huginn keeps at most one open Business-owned recommendation for a Business and
Company. Closed recommendations and their assessment revisions remain in
history. An assessment revision records what the system knew and evaluated at a
particular time. In-app recommendations, weekly email, feedback, and saved
prospects refer to that shared history. A later assessment adds a revision; it
does not replace the evidence shown earlier.

Before enabling this workflow in a deployment, follow the
[recommendation and prospect cutover guide](recommendation-prospect-cutover.md).
That guide owns schema ordering and cutover checks. Application startup does
not apply schema changes, and this guide does not claim a deployment has been
upgraded.

## Set up Business research

Configure Business offerings in Profile. Create and edit ideal client profiles
from Settings; Profile's ICP tiles open the selected profile there. Create or
edit discovery strategies in the strategy configuration flow outside the
primary navigation. Strategies are configured manually and are not paired
automatically with offerings or ICPs.
The personal profile remains separate from Business details.

Open Recommendations to search and review the Business's shared recommendation
list. Generation is an explicit action; ordinary reads do not generate
recommendations or send email. Generation uses the current Business strategies
and guarded source evidence, then records assessment revisions and their source
lineage. The current lexical retrieval examines evidence from the preceding 365
days and collects at most 200 eligible companies. Generation returns at most 20
companies, with a default of 10. These are research candidates, not evidence of
buying intent. Missing source facts remain unverified rather than being
invented.

Profile setup and strategy changes affect future assessments. They do not
rewrite earlier assessment snapshots. The weekly digest uses the same shared
recommendations and assessment history; it is not a separate recommendation
batch or a separate company history.

## Review and act on a recommendation

Open a recommendation to inspect its current context, assessment revision, and
source evidence. Email links include both the recommendation ID and the exact
assessment revision ID. Following a link reads that historical revision; it
does not generate a new assessment or mutate workflow state.

Available actions have distinct effects:

- **Save** links the recommendation and shown revision to the Business's
  prospect for that Company. It creates a prospect in Saved when none exists; if
  one already exists, it reuses that prospect and preserves its current stage.
- **Not relevant** records a Business-owned rejection and its reason. It does
  not create a prospect or rewrite the assessment.
- **Later** adds a Business-and-Company pause for a selected duration, or
  indefinitely. It blocks presentation across in-app and weekly channels.
  Durations x1 through x4 multiply the Business's accepted repeat interval
  (default 30 days). Accepting a replacement pause starts its duration then,
  keeps the prior pause in history, and leaves independent blocks in place.
- **Quality feedback** records a report against the exact displayed revision.
  Feedback is report-only: it does not change ranking, assessment, suppression,
  prospect state, or contact behavior.

Prospects are managed in the Prospects workspace. Stage changes are explicit
and require a reason when moving backward. Closing and reopening are explicit
actions. Notes are one editable memo, reminders can be set or cleared, proposal
drafts are records only, and activity-time corrections append to the audit
history. None of these actions sends outreach or advances a prospect
automatically.

## API reference

All public reads and commands derive the acting User and Business from the
authenticated session. Clients do not choose an owner ID. Unsafe requests use
the session CSRF token. Responses are private and non-cacheable. See the
generated OpenAPI document for complete schemas and concurrency fields.

| Purpose | Route |
| --- | --- |
| List or filter shared recommendations | `GET /api/v1/recommendations` |
| Generate recommendations explicitly | `POST /api/v1/recommendations` |
| Read a recommendation or exact historical revision | `GET /api/v1/recommendations/{recommendation_id}` |
| List its assessment history | `GET /api/v1/recommendations/{recommendation_id}/assessments` |
| Save as a prospect | `POST /api/v1/recommendations/{recommendation_id}/save` |
| Record not relevant | `POST /api/v1/recommendations/{recommendation_id}/not-relevant` |
| Set or replace a Later pause | `POST /api/v1/recommendations/{recommendation_id}/later` |
| Record report-only quality feedback | `POST /api/v1/recommendations/{recommendation_id}/feedback` |
| List or read prospects | `GET /api/v1/prospects`, `GET /api/v1/prospects/{prospect_id}` |

Prospect commands use the corresponding routes under
`/api/v1/prospects/{prospect_id}` for stage, close, reopen, notes, reminders,
proposal drafts, and activity-time corrections. Read the exact route schemas in
OpenAPI before building an API client; commands carry expected versions and
idempotency data to protect against stale edits and retries.

Retrying a prospect command with the same request key and payload returns its
original activity together with the prospect's current state. It does not repeat
the action or append history. A changed payload using the same key conflicts;
a new command with a stale expected version also conflicts.

## Assessment limits

The built-in ranker is a lexical research baseline, not a language model or a
buying-intent predictor. Whole-word topic retrieval, known ICP mismatches,
source freshness, and explicit exclusions affect eligibility. The source
retrieval window is 365 days and the eligible candidate collection is bounded
at 200 companies. Weekly selection chooses up to seven distinct companies; it
does not add scores across strategies or force a quota per offering. Re-check
the saved source lineage when a decision depends on a particular claim.

Existing Match history is not converted into this workflow. The new shared
recommendation history starts without importing or backfilling old Matches.
