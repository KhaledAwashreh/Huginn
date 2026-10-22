# Source-context output validation

Status: The source census, correction loop, disposable-PostgreSQL checks,
full test suite, and independent review are complete. The implementation handoff in
`architecture-notes/preserve-source-context-implementation-handoff.md`
records exact commands, report paths, fingerprints, and remaining gaps.

## Measured corpus and retention

| Source | Current Bronze | Captured | Excluded | Failed | Selected-input fingerprint |
| --- | ---: | ---: | ---: | ---: | --- |
| HN | 597 | 503 | 94 | 0 | `f17af7b45f44f3219119c274f276005ffbb02122a5aba253c4d75ad82dbb2b10` |
| YC | 6,287 | 6,287 | 0 | 0 | `a50dd61c93ce9b23529f8a32164b2cf36439fbb0d722cab95724bb4cbb067553` |
| EU-Startups | 236 | 236 | 0 | 0 | `b1d234be4cabd93826c5986bd465210b75033addd3dc720261a6831dd43b246d` |

The final CLI reports are local under `/tmp/huginn-context-*-final-summary.json`;
the detailed full-text artifacts are separate files under `/tmp` and are not
committed. The ID-only manual review evidence is under
`/tmp/huginn-source-context-hn-audit.json` and
`/tmp/huginn-source-context-eu-yc-review.json`. All database source audits
used read-only, timeout-bound access. Their field-retention counts do not
measure lead relevance, purchase intent, or ranking success.

HN retained header/body text on all 503 captured comments, with 496 known
boundaries and seven honest unknown boundaries. All 597 source timestamps
survive, including on excluded outcomes. EU retained separate short and long
descriptions on all 236 supported listings, with 185 long descriptions; its
25 short-description differences against staging are whitespace only. YC
retained both descriptions for 5,763 records, `isHiring=false` for 4,792,
team size zero for 136, and 1,918 inactive/acquired source observations.
The 5 stale YC Silver rows and 3 Gold signals are a future lifecycle
reconciliation issue, not a parser defect. Thirty dead HN comments remain in
legacy staging and are excluded by this new context workflow.

## Ground truth and selection

1. Read the existing database using read-only, timeout-bound access. Use a consistent
   read snapshot per census and record payload fingerprints and selection order.
2. Run a parser census over all available stored HN/YC/EU input. Record raw input,
   accepted context, excluded, failed, staged, resolved, and Gold counts separately.
3. Review full normalized text against raw source for deterministic examples per
   source and every new error category. Include resolved and unresolved records.
4. Keep keyword-selected challenge cases separate from the source-stratified sample.
   Split by repeated company/post text to avoid training and testing on duplicates.
5. Store detailed reports locally outside tracked artifacts. Keep credentials and
   irrelevant contact details out of committed fixtures and handoffs.

## Before/after checks

| Area | Output evidence | Acceptance |
|---|---|---|
| HN | Raw header/body versus context and existing description | Every supported visible segment retained; all reviewed explicit employment restrictions survive |
| HN exclusions | Root/deleted/dead/empty/malformed outcomes | No silent omissions; exclusions explained |
| EU | Listing containers versus short/long text and attributes | Supported fields retained; no navigation/scripts treated as listing context |
| EU geography | Raw category/place versus sidecar | Original meaning retained; no automatic city/country/sector inference |
| YC | Raw short/long description and typed context versus sidecar | Both preserved; false/unknown/zero distinct |
| Time | Source dates/check metadata versus captured_at | No fabricated event/first-observed date or freshness reset |
| Identity | Valid context with unresolved company | Context retained without unsafe link or Gold promotion |
| Persistence | First run, repeat, changed content, changed parser version | Expected unique snapshots, immutable prior content, accounted outcomes |
| Compatibility | Legacy table contents before/after disposable capture | No changes outside new sidecar/run tables |

The earlier audit counts (597 HN raw, 6,287 YC raw, 236 EU pages) are reference
observations, not constants to force future reports to match. Explain drift from
input fingerprints. Full-census metrics describe field retention, not buyer intent.

## Correction loop

For every discrepancy, record source/stable ID, input fingerprint, expected field,
actual output, classification, and disposition. Categories: implementation defect,
malformed input, intentional exclusion, or source fact unavailable.

For defects: add a failing sanitized test, fix, rerun focused tests, repeat the
same corpus comparison, and inspect a fresh holdout. A passing unit test alone is
not sufficient when the live-data discrepancy remains. Re-audit other sources if
a shared helper changes. Do not change test expectations merely to bless loss.

## Completion evidence

Required artifacts: baseline summary; per-source census; field-retention results;
local before/after examples; defect ledger; correction/retest history; legacy-data
invariance check; independent review disposition; actual test command results.
No unresolved correctness defect is accepted as a source gap. Any explicit
exception that changes required behavior requires revising the spec before closure.

A separate later evaluation assesses explicit project demand and offering relevance.
It must not reuse retention percentages as evidence that ranking is effective.
