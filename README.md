# Huginn

Client-discovery tool for independent service providers. Ingests public startup signals (hiring, funding) and scores them against a user's ICP to produce a weekly lead digest.

Architecture: `docs/architecture.md`. Decision records: `adr/`. Research backing the design: `architecture-notes/`. Domain schema: `docs/entities.md` and `db/schema/`. See the [management foundation runbook](docs/management-foundation.md) for local bootstrap. Tracked tech debt and research debt, plus the ELT build epic: Jira project KAN (epics KAN-16 and KAN-21).

## Status

Ingestion (HN, YC) and the Bronze write path are implemented and live-verified end to end. Silver, Gold, and the scoring/digest layers are not yet built.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env  # set HUGINN_DATABASE_URL and HUGINN_YC_ALGOLIA_API_KEY
psql "$HUGINN_DATABASE_URL" -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
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

## Running the management foundation

The management module currently exposes only health and database-readiness
probes. Bootstrap a dedicated development database and run the local server
through the [module entrypoint](src/huginn/management/__main__.py) with
`python -m huginn.management`. The management foundation runbook has the
complete schema order, environment, probe commands, implemented contract, and
KAN-72 handoff.

## Layout

```
src/huginn/
    ingestion/       ports (ApiSourcePort, RawStorePort, StatePort), IngestionService,
                     per-source adapters, __main__.py (CLI entrypoint)
    bronze/           content-hash watermarking, Postgres-backed RawStorePort/StatePort
    silver/           entity resolution
    gold/             Company/CompanyHistory current-plus-history update logic
    ops/              job_runs domain model, Postgres-backed JobRunWriterPort
    management/       config, professional collection schemas, readiness, Flask app,
                      __main__.py (local development server entrypoint)
    config.py         environment-based configuration
db/schema/            hand-written DDL, one file per layer
tests/                mirrors src/huginn/
```
