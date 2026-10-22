# Source context preservation

The source-context sidecar keeps complete HN, YC, and EU-Startups evidence under
`silver.source_context_snapshot`, keyed by source, stable ID, full raw payload
digest, and parser version. It records run outcomes and observation metadata in
separate Silver tables. This is an explicit offline workflow. The ordinary ELT
pipeline, Gold projections, matchmaking, and ranking do not read the sidecar.

## Audit stored input

1. Configure `HUGINN_DATABASE_URL` in the local environment. The CLI has no
   connection-string argument.
2. Run a read-only census for each source. Each command selects all stored rows
   unless `--limit` is given. A positive limit samples in stable MD5 ID order.

   ```bash
   rtk proxy uv run python -m huginn.elt.silver.context audit --source hn --summary .local-runtime/source-context/hn-summary.json
   rtk proxy uv run python -m huginn.elt.silver.context audit --source yc --summary .local-runtime/source-context/yc-summary.json
   rtk proxy uv run python -m huginn.elt.silver.context audit --source eu_startups --summary .local-runtime/source-context/eu-summary.json
   ```

3. Pass `--details` only when source text is needed for local review. Its default
   destination is `.local-runtime/source-context/audit-details.json`, which Git
   ignores. Use a distinct path for each source if retaining several reports.

Audit uses a repeatable-read, read-only transaction with a statement timeout for
Bronze and downstream comparisons. The summary contains counts, parser and
input fingerprints, selected stable IDs, and no source text. A changed input
fingerprint means two reports do not describe the same stored payload set.
Field coverage shows retained source facts; it is not a buyer-intent or ranking
quality measure. EU's raw `category` currently contains country labels, while
`based_in` provides place names. The sidecar preserves the labels without
assigning a canonical geography.

## Capture into a disposable database

Apply `db/schema/silver-source-context.sql` on an existing disposable database,
or use `db/schema/silver.sql` when bootstrapping a fresh one. The standalone
migration is additive and idempotent; it refuses incompatible table shapes.
The application does not apply migrations at startup.

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/silver-source-context.sql
rtk proxy uv run python -m huginn.elt.silver.context capture --source hn --summary .local-runtime/source-context/hn-capture.json
```

`capture` is explicit and writes only the new Silver snapshot, run, and outcome
tables. A repeated payload/parser pair reuses its snapshot. Latest check time
is an observation, not the first-seen time of a payload version. Run status and
per-record outcomes distinguish complete, partial, excluded, failed, and
interrupted processing. Re-run the read-only audit after a parser change and
compare fingerprints before attributing any difference to the parser.

Shared persistent-database migration and capture have not been performed as
part of this implementation. They require a separate operation with a target,
dry-run counts, and rollback plan. Gold promotion and lifecycle reconciliation
remain follow-on changes.
