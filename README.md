# Huginn

Client-discovery tool for independent service providers. Ingests public startup signals (hiring, funding) and scores them against a user's ICP to produce a weekly lead digest.

Architecture: `docs/architecture.md`. Decision records: `adr/`. Research backing the design: `architecture-notes/`. Domain schema: `docs/entities.md` and `db/schema/`. Tracked tech debt and research debt, plus the ELT build epic: Jira project KAN (epics KAN-16 and KAN-21).

## Status

Ingestion (HN, YC) and the Bronze write path are implemented and live-verified end to end. Silver, Gold, and the scoring/digest layers are not yet built.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env  # set HUGINN_DATABASE_URL and HUGINN_YC_ALGOLIA_API_KEY
psql "$HUGINN_DATABASE_URL" -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
uv run pytest
```

## Running ingestion

```
uv run python -m huginn.ingestion
```

Fetches HN and YC once and writes to Bronze, recording a row per source per run in `ops.job_runs`. One source failing does not abort the other (`IngestionService`, architecture document section 5).

No orchestration framework at this scale (Jira KAN-9 tracks any future upgrade past cron): schedule it with a plain crontab entry, redirecting output since library code does not configure logging itself (`adr/0005-logging-required-from-day-one.md`, the entrypoint owns that via `logging.basicConfig`):

```
0 9 * * * cd /path/to/Huginn && /path/to/uv run python -m huginn.ingestion >> /var/log/huginn-ingestion.log 2>&1
```

## Layout

```
src/huginn/
    ingestion/       ports (ApiSourcePort, RawStorePort, StatePort), IngestionService,
                     per-source adapters, __main__.py (CLI entrypoint)
    bronze/           content-hash watermarking, Postgres-backed RawStorePort/StatePort
    silver/           entity resolution
    gold/             Company/CompanyHistory current-plus-history update logic
    ops/              job_runs domain model, Postgres-backed JobRunWriterPort
    config.py         environment-based configuration
db/schema/            hand-written DDL, one file per layer
tests/                mirrors src/huginn/
```
