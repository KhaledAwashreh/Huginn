## 1. Console contract and routes

- [x] 1.1 Apply after foundation and pipeline-control API/role contracts; regenerate foundation-owned offline typed schemas and pass api:check and verify current-session role, trigger 409/202, detail metrics and event cursors match server responses.
- [x] 1.2 Add separate pipeline pages/components/query modules and role-gated Data collection tab while retaining `/admin/pipeline`; verify direct-link reload, user forbidden state and immediate 403 demotion cache/control clearing.

## 2. Trigger, detail and history

- [x] 2.1 Add Pull data request-ID lifecycle and duplicate-submission prevention for the full HN/YC/EU-Startups pipeline; verify 202 navigation, 409 open-active action, uncertain response same-key explicit retry and no automatic new run.
- [x] 2.2 Add paginated history with deterministic state/offset navigation; verify empty/loading/error/long-ID rows and bounded pages.
- [x] 2.3 Add invocation summary and Source/Bronze, Silver, Gold stage tabs driven by server plan; verify exact source-parent grouping, dependency skip versus failure/interruption and manual-review queueing display without review actions.
- [x] 2.4 Add typed counters/timestamps/freshness and nine-stage progress view; verify “N of 9 stages finished” counts only succeeded/failed/skipped, failed/skipped distinction, running exclusion, interrupted/not-executed distinction, indeterminate active-source progress, unknown counters, no elapsed-time percentage and stale running guidance without unsupported cancel/reconcile controls.
- [x] 2.5 Add cursor-paginated chronological event log with safe text rendering; verify duplicates/gaps/older/newer pages and X-to-Y query isolation.
- [x] 2.6 Add invocation company summary and bounded paginated current-Gold-field results; verify exact invocation scope, processed/written wording, refetch on Gold stage/metric or terminal change, cancellation and cross-invocation isolation, loading/empty/error/retry, legacy unknown membership, and no claim of new/changed companies.

## 3. Live updates and validation

- [x] 3.1 Add visible-page active detail/history/event polling, bounded backoff and AbortController cancellation; verify hidden/navigation/terminal/401/403 transitions stop requests and transient failures retain aged last-known data.
- [x] 3.2 Verify grouped real API/browser scenarios using user/admin/disabled fixtures and harmless deterministic executors on disposable PostgreSQL 16; exercise queued/start/failed/skipped/succeeded/interrupted/stale states, Gold result paging, and competing shared-guard ownership without real source scraping or matcher execution through the pipeline.
- [x] 3.3 Inspect wide/narrow layouts, keyboard tabs/focus, long safe logs/IDs and non-color statuses; verify rendered usability and record evidence in the local implementation log.
- [x] 3.4 Document supported sources/queue waiting/history/recovery guidance, run the foundation named npm check/test:e2e gates (WCAG 2.2 AA axe plus manual checks), Python 3.14 compilation, Ruff check/format, full pytest with live PostgreSQL 16 regressions, strict OpenSpec validation and exact file/type inventory/dependency review against the chosen implementation base and fresh Sol high review; resolve findings before separately authorized commit/push.
