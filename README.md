# Huginn

Client-discovery tool for independent service providers. Ingests public startup signals (hiring, funding) and scores them against a user's ICP to produce a weekly lead digest.

Architecture: `Huginn Arch Dcument.md`. Decision records: `adr/`. Research backing the design: `architecture-notes/`. Domain schema: `Entites.md` and `db/schema/`. Tracked tech debt and research debt, plus the ELT build epic: Jira project KAN (epics KAN-16 and KAN-21).

## Status

Scaffolding only. No adapter, ingestion, or scoring logic is implemented yet beyond the pieces simple and well-specified enough to write without further design: content-hash watermarking (`src/huginn/bronze/watermark.py`), domain normalization (`src/huginn/silver/resolution.py`), and the Gold current-plus-history update rule (`src/huginn/gold/dimensional.py`).

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env  # set HUGINN_DATABASE_URL
psql "$HUGINN_DATABASE_URL" -f db/schema/00_extensions.sql -f db/schema/bronze.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
uv run pytest
```

## Layout

```
src/huginn/
    ingestion/       ports (SourcePort, RawStorePort, StatePort), IngestionService, per-source adapters
    bronze/           content-hash watermarking
    silver/           entity resolution
    gold/             Company/CompanyHistory current-plus-history update logic
    config.py         environment-based configuration
db/schema/            hand-written DDL, one file per layer
tests/                mirrors src/huginn/
```
