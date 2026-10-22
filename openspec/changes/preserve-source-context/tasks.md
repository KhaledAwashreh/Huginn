## 1. Baseline and safe working set

- [x] 1.1 Create an isolated implementation worktree from `4cbabd8` or a verified successor; record base SHA, branch, dirty files to preserve, and confirm the primary checkout and existing worktrees are unchanged.
- [x] 1.2 Run baseline Ruff and full pytest including disposable PostgreSQL tests; record actual commands/results and existing failures without claiming they were caused by this change.
- [x] 1.3 Record read-only source census and source payload fingerprints, including resolved/unresolved partitions; verify credentials/contact text are absent from the aggregate report.
- [x] 1.4 Create sanitized regression fixtures for HN full-time headers/no-separator posts, EU omitted fields/boilerplate, and YC dual descriptions/false/unknown/zero/inactive values; confirm each fixture preserves the observed failure semantics.

## 2. Context contracts and persistence

- [x] 2.1 Add typed source-context, outcome, observation, and run values with parser version and deterministic payload digest; watch tests fail first, then verify stable hashing and Unicode header/body spans.
- [x] 2.2 Add canonical Silver sidecar/run schema and idempotent additive migration; verify fresh bootstrap, repeat migration, incompatible shape rejection, and transactional rollback on disposable PostgreSQL.
- [x] 2.3 Implement context persistence through repository contracts; verify duplicate input reuses snapshots, changed content/version preserves old snapshots, and snapshot/outcome writes are atomic.
- [x] 2.4 Implement observation/run bookkeeping with explicit excluded/failed/interrupted outcomes; verify latest-check metadata does not change content identity or overwrite historical observation semantics.

## 3. HN preservation

- [x] 3.1 Implement full normalized header/body text and outgoing link context; verify full-time/location restrictions survive and missing paragraph separators retain all visible text.
- [x] 3.2 Implement root/dead/deleted/empty exclusion and malformed-input outcomes; verify explicit precedence and no company-resolution or network calls.
- [x] 3.3 Audit every available HN Bronze item read-only and review deterministic examples across resolved/unresolved partitions; account for every input and demonstrate recovery of omitted headers.
- [x] 3.4 Turn each HN output defect into a failing regression fixture, fix the parser, and repeat the same-input audit plus held-out review; record unresolved source gaps separately from implementation defects.

## 4. EU listing preservation

- [x] 4.1 Reuse listing-specific selectors to preserve separate descriptions, raw country/category, place, tags, founding/funding/status; verify optional values remain unknown and no taxonomy mapping is invented.
- [x] 4.2 Test pages with missing/reordered fields, repeated navigation labels, HTML markup, and absent listing structure; verify boilerplate cannot become listing evidence.
- [x] 4.3 Audit all currently stored EU pages, replacing the prior ten-page coverage assumption with a census; report field coverage and deterministic full-context review results.
- [x] 4.4 Reproduce EU discrepancies as sanitized fixtures, correct selectors/normalization, and repeat the fingerprinted audit; accept only accounted outcomes with no unexplained loss of supported listing fields.

## 5. YC context preservation

- [x] 5.1 Preserve separate summaries/descriptions, taxonomy, exact size, locations, batch, source status, launch time, and nullable hiring flag; verify distinct false/unknown/zero semantics and malformed-type rejection.
- [x] 5.2 Capture valid disqualified source status observations independently of descriptive staging; verify inactive/acquired data creates no new eligible company or changes to existing staging behavior.
- [x] 5.3 Audit all current YC records with status/identity partitions; report paired-description retention and source-field coverage without presenting marketing text as demand.
- [x] 5.4 Add regression fixtures for discrepancies, correct normalizers, and rerun the same-input and held-out audits; preserve legacy parser outputs in regression comparisons.

## 6. Explicit audit and capture commands

- [x] 6.1 Add the explicit audit/capture CLI with source selection, positive optional limit, deterministic ordering, and local report paths; verify invalid arguments fail before DB access and no DSN CLI argument exists.
- [x] 6.2 Enforce read-only/time-limited audit connections and no collection/model/network activity; verify with integration tests and a mutation-attempt rejection test.
- [x] 6.3 Implement safe aggregate and opt-in detailed local output with counts, fingerprints, versions, and failures; verify input accounting and absence of secrets/contact text from routine summaries.
- [x] 6.4 Exercise explicit capture twice on a disposable copy of representative input; verify idempotence, interruption/rollback behavior, and zero changes to legacy Bronze/Silver/Gold/operational data.

## 7. Output acceptance and independent review

- [x] 7.1 Complete `validation-plan.md` against all available stored input with read-only live access and disposable output; attach per-source before/after metrics, exceptions, and held-out review evidence.
- [x] 7.2 Resolve every implementation defect with regression tests and rerun affected audits; document source gaps without silently loosening requirements or claiming improved service-demand yield.
- [x] 7.3 Verify Python compile, Ruff lint/format, full pytest, live disposable PostgreSQL integration, and strict OpenSpec validation; record exact results and confirm meaningful integration tests actually ran.
- [x] 7.4 Obtain an independent Sol review of code, migrations, tests, and real-data output artifacts; resolve findings and rerun affected checks before declaring the change complete.
- [x] 7.5 Update architecture/runbooks with the narrowly scoped versioned Silver sidecar and explicit commands; verify examples against tests and document that shared-DB migration/capture and Gold promotion have not been performed.
- [x] 7.6 Write implementation handoff with completed tasks, report locations, input fingerprints, known gaps, and lifecycle-spec prerequisites; leave persistent-data deployment as a concrete separately reviewed operation.
