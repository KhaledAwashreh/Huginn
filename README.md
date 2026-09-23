# Huginn

Client-discovery tool for independent service providers. Ingests public startup signals (hiring, funding) and scores them against a user's ICP to produce a weekly lead digest.

Architecture: `docs/architecture.md`. Decision records: `adr/`. Research backing the design: `architecture-notes/`. Domain schema: `docs/entities.md` and `db/schema/`. See the [management foundation runbook](docs/management-foundation.md) for local bootstrap. Tracked tech debt and research debt, plus the ELT build epic: Jira project KAN (epics KAN-16 and KAN-21).

## Status

Ingestion (HN, YC) and the Bronze write path are implemented and live-verified end to end. Silver (per-source staging plus cross-source resolution) and Gold (the `Company` dimension and `CompanySignal` fact) are implemented, covered by unit and integration tests, and live-verified end to end for HN and YC via the pipeline entrypoint below. OpenCorporates and EU-Startups are ingested into Bronze but not yet wired into Silver/Gold through that entrypoint. The scoring and digest layers are not built.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env  # set HUGINN_DATABASE_URL and HUGINN_YC_ALGOLIA_API_KEY
psql "$HUGINN_DATABASE_URL" -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
uv run pytest
```

## Running the pipeline

```
uv run python -m huginn.elt
```

Runs the full pipeline once: Ingestion (HN + YC) through Bronze, Silver staging and resolution, and Gold, in dependency order, recording one row per stage per run in `ops.job_runs` (`adr/0014-pipeline-entry-point-and-stage-failure-policy.md`). A stage runs only if every stage it depends on succeeded; an unrelated stage's failure does not block it (dependency-aware skip-on-failure, same default as dbt's `dbt run`/`dbt build` and Airflow's `all_success` trigger rule). OpenCorporates and EU-Startups are not included in this entrypoint's ingestion stage yet.

No orchestration framework at this scale (Jira KAN-9 tracks any future upgrade past cron): schedule it with a plain crontab entry, redirecting output since library code does not configure logging itself (`adr/0005-logging-required-from-day-one.md`, the entrypoint owns that via `logging.basicConfig`):

```
0 9 * * * cd /path/to/Huginn && /path/to/uv run python -m huginn.elt >> /var/log/huginn-pipeline.log 2>&1
```

## Running ingestion only

```
uv run python -m huginn.elt.ingestion
```

Fetches HN, YC, and OpenCorporates once and writes to Bronze only, recording a row per source per run in `ops.job_runs`. One source failing does not abort the others (`IngestionService`, architecture document section 5). Use this instead of the full pipeline above when only a fresh Bronze fetch is wanted, for example while OpenCorporates/EU-Startups are not yet wired into Silver/Gold.

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
    elt/
        __main__.py   CLI entrypoint for the full pipeline (`python -m huginn.elt`)
        ingestion/   ports (ApiSourcePort, RawStorePort, StatePort), IngestionService,
                     per-source adapters, __main__.py (ingestion-only CLI entrypoint)
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
