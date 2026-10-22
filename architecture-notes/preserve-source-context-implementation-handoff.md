# Source-context preservation implementation handoff

Status: implementation, source audits, disposable database verification, and
independent review complete. No shared persistent database migration or capture
has been performed.

## Working set and baseline

1. Branch: `feature/preserve-source-context` in
   `.worktrees/preserve-source-context`, based on
   `4cbabd8451940c3d10cc72fd2e48799c3851aff7`.
2. The primary checkout's pre-existing modified job-run writer, interview
   artifacts, architecture notes, and other untracked OpenSpec changes were
   left untouched. The completed `preserve-source-context` planning package is
   included on this branch, with its original copy in the primary checkout.
3. Baseline on the unchanged `weekly-digest-api` integration base: Ruff lint
   and format passed; full pytest passed with 1,496 tests and one upstream
   Starlette deprecation warning. The baseline full-suite command used
   `PYTHONPATH=src` and the populated `admin-discovery-workspace` virtualenv
   because this worktree has no local virtualenv.

## Read-only corpus evidence

The existing `huginn-verify-pg` container was restarted, then queried with
read-only, timeout-bound transactions. The final CLI audits wrote aggregate
summaries and detailed local artifacts under `/tmp`; no database writes were
made. Input fingerprints identify the exact selected current Bronze payloads.

| Source | Bronze | Captured | Excluded | Failed | Input SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| HN | 597 | 503 | 94 | 0 | `f17af7b45f44f3219119c274f276005ffbb02122a5aba253c4d75ad82dbb2b10` |
| YC | 6,287 | 6,287 | 0 | 0 | `a50dd61c93ce9b23529f8a32164b2cf36439fbb0d722cab95724bb4cbb067553` |
| EU-Startups | 236 | 236 | 0 | 0 | `b1d234be4cabd93826c5986bd465210b75033addd3dc720261a6831dd43b246d` |

1. HN: 496 captured comments have header/body spans; seven no-separator
   comments retain all visible text with unknown boundaries. Among the
   captured headers, 330 contain an explicit full-time phrase; 321 lack that
   phrase in the legacy staging description. All 597 stored source timestamps are valid and
   retained, including the 94 excluded rows. The independent source audit
   found no non-whitespace character loss and reviewed disjoint deterministic
   samples and holdouts across candidate-key and unresolved partitions.
2. YC: 5,763 payloads have both one-line and long descriptions; 4,792 state
   `isHiring=false`; 136 report team size zero; and 1,918 are currently
   `Inactive` or `Acquired`. These are source observations, not demand signals
   or known closure dates. All 6,287 source launch values remain separate from
   capture time. One source record reports a negative team size; the raw value
   is preserved and not interpreted as a valid company scale.
3. EU-Startups: all 236 listing pages yielded listing-scoped fields; 185 have
   a separate long description. All 25 short-description differences from
   legacy staging are whitespace/tag-boundary formatting; none loses a
   non-whitespace character. The source labels `category` and `based_in` are
   preserved verbatim. There is no distinct country selector in the stored
   pages; category values often happen to be country labels, which this phase
   does not map to canonical geography. All stored website fields are plain
   text, while a linked-website regression test covers future markup.

The aggregate CLI reports are `/tmp/huginn-context-hn-final-summary.json`,
`/tmp/huginn-context-yc-final-summary.json`, and
`/tmp/huginn-context-eu_startups-final-summary.json`. Detailed outputs remain
under `/tmp/huginn-context-*-final-detail.json` and must not be committed.
The separate ID-only, source-stratified audit reports are
`/tmp/huginn-source-context-hn-audit.json` and
`/tmp/huginn-source-context-eu-yc-review.json`.

## Defect and source-gap ledger

1. HN exclusions initially omitted their supplied event time. A failing
   regression was added, the normalizer was corrected, and the same stored
   corpus was re-audited with unchanged input fingerprint. Malformed supplied
   timestamps now produce explicit failed outcomes.
2. EU linked website markup initially retained only visible anchor text. A
   failing fixture led to separate safe `href` and visible-label preservation;
   off-domain listing URLs and unsafe website hrefs now fail. Stored EU website
   fields are all plain text, so the correction does not alter current output.
3. YC non-finite or out-of-range launch values initially passed type checks.
   They now fail safely while valid raw epochs remain unchanged.
4. Five current YC Silver rows and three Gold signals remain from a prior
   eligible status while current Bronze reports a disqualifying status. This
   is a legacy lifecycle reconciliation gap, not a source-normalizer defect.
   Thirty dead HN comments also remain in legacy staging; this phase records
   them as excluded and does not mutate prior projections.
5. Source context is not a purchase-request classifier. HN data is mostly
   employment advertising; YC and EU prose is largely company/product
   description. Ranking and lifecycle consumption need separate reviewed
   changes and outcome evidence.
6. Independent Sol review found three implementation issues: audit/capture
   identity classification differed for mismatched IDs; HN's full-time metric
   counted whole-header absence; and migration compatibility accepted
   same-named, incorrect constraints. Shared validation, phrase-specific
   reporting, and exact PostgreSQL-compiled CHECK-definition comparisons now
   address them. The reviewer rechecked the fixes and found no remaining
   concrete flaw. Disposable PostgreSQL regressions cover incorrect unique
   keys and the stricter `total_inputs >= 1` check.

## Verification and deployment boundary

The final full suite passed 1,550 tests with one existing upstream Starlette
deprecation warning (baseline: 1,496 passed). The targeted migration and
repository suite passed 15 tests, including disposable PostgreSQL regression
cases. Compileall, repository-wide Ruff lint/format,
`git diff --check`, and strict OpenSpec validation passed. Sol's initial and
targeted read-only reviews found and then verified corrections to all three
actionable issues. No persistent database migration/capture or Gold promotion
is authorized by this handoff. An operator should separately review an exact
target, dry-run counts, and rollback plan before shared-database deployment.
