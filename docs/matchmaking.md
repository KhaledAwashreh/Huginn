# Matchmaking assessment and retired writer

Discovery now uses the Business-owned recommendation/prospect workflow. The
creation-only Match writer, direct batch CLI, queued execution and administrator
admission are retired. They cannot create new `operational.match` rows. The old
CLI/bootstrap/worker entry points fail closed with retirement diagnostics, and
authenticated administrator POST admission returns private HTTP 410.

Use [recommendations and prospects](research-recommendations.md) for current API
and workspace behavior, [weekly delivery](weekly-digest.md) for scheduled selection,
and [the cutover guide](recommendation-prospect-cutover.md) for explicit setup,
obsolete-row cleanup, quiescence and rollback. No old Match is automatically
converted into a prospect.

## Shared assessment

The matchmaking package still owns reusable fit, eligibility, lexical research,
ranking and strongest-company selection policies. On-demand and weekly management
services consume those policies through the same guarded evidence source. Known
mismatches and explicit exclusions are removed; missing attributes remain
unverified. Profile completion does not automatically create or activate strategies.

The standalone research-ranking CLI writes explicit ranking artifacts and does
not create canonical discovery records or send email. Its replay and scoring
contract remains in [research-ranking.md](research-ranking.md).

## Retained execution history and recovery

Administrator GET run history and exact stopped-executor reconciliation remain
available. The shared pipeline execution guard still calls the retained run
repository's finish/reconcile methods. Their presence does not enable new Match
execution or queue admission.

```sh
rtk proxy uv run python -m huginn.matchmaking_control reconcile --help
```

Recovery requires the exact run/execution identity and proof that its process
stopped. A live or counterpart-owned executor must not be released. Queued legacy
runs and unresolved executors are failed cutover preflight conditions; do not
execute or erase them as part of the new workflow.

`HUGINN_MATCHMAKING_DATABASE_URL` remains the explicit recovery command's database
setting. It must identify the same intended database as management and collection.
Source reconciliation remains an explicit pipeline/operator operation described
in [source-currentness.md](source-currentness.md), never an application read.
