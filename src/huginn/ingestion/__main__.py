"""CLI entrypoint: `python -m huginn.ingestion`. See architecture document
section 5 (ingestion) and section 10 (orchestration: cron plus job_runs,
no framework at this scale; Jira KAN-9 tracks any future upgrade).
"""

from __future__ import annotations

import logging

from huginn.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.config import Config, load_config
from huginn.ingestion.adapters.hn import HackerNewsAdapter
from huginn.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.ingestion.service import IngestionService
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter


def build_service(config: Config) -> IngestionService:
    """Construct IngestionService with the real adapters and Postgres-backed
    ports. Separated from `main()` so the wiring is testable without a live
    database or network call (CLAUDE.md code standard 4).
    """
    return IngestionService(
        sources=[HackerNewsAdapter(), YcDirectoryAdapter()],
        raw_store=PostgresApiIngestStore(config.database_url),
        job_run_writer=PostgresJobRunWriter(config.database_url),
    )


def main() -> None:
    """Run one ingestion pass. The application entrypoint, not library
    code, so it owns logging configuration (adr/0005-logging-required-from-day-one.md).
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    build_service(load_config()).run_once()


if __name__ == "__main__":
    main()
