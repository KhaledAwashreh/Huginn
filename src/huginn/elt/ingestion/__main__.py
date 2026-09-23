"""CLI entrypoint: `python -m huginn.elt.ingestion`. See architecture
document section 5 (ingestion) and section 10 (orchestration: cron plus
job_runs, no framework at this scale; Jira KAN-9 tracks any future upgrade).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from huginn.config import Config, load_config
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    PostgresEuStartupsDiscoveryRepository,
)
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository
from huginn.elt.ingestion.adapters.eu_startups import EuStartupsDiscoveryAdapter
from huginn.elt.ingestion.adapters.hn import HackerNewsAdapter
from huginn.elt.ingestion.adapters.opencorporates import OpenCorporatesAdapter
from huginn.elt.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.elt.ingestion.eu_startups_discovery_runner import (
    EuStartupsDiscoveryRunner,
)
from huginn.elt.ingestion.service import IngestionService
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter

# OpenCorporates' free tier caps at 50 requests/day (docs/sources/
# opencorporates-api.md, Access); this is a simple per-run call budget, not
# the stateful cross-run quota tracker architecture-notes/
# opencorporates-fetch-plan.md section 7 explicitly defers.
OPENCORPORATES_MAX_CALLS = 50
EU_STARTUPS_DISCOVERY_COMMAND = "eu-startups-discovery"


def build_service(config: Config) -> IngestionService:
    """Construct IngestionService with the real adapters and Postgres-backed
    ports. Separated from `main()` so the wiring is testable without a live
    database or network call (CLAUDE.md code standard 4).

    The `bronze.api_ingest` repository is built once here and injected, so
    every consumer of that table shares one implementation of its queries.
    `StatePort`/`PostgresApiIngestState` still has no caller (Jira KAN-46).

    Unlike `HackerNewsAdapter`/`YcDirectoryAdapter`, `OpenCorporatesAdapter`
    is not stateless: it needs a Gold read to learn which company names this
    run should search for (architecture-notes/opencorporates-fetch-plan.md
    section 5). The adapter invokes this composition-root loader lazily from
    `fetch()`, keeping service construction free of database I/O without
    leaking the cross-layer read into `IngestionService`.
    """
    api_ingest_repository = PostgresApiIngestRepository(config.database_url)

    def load_opencorporates_companies() -> list[str]:
        """Load the bounded Gold candidate set described in the fetch plan.

        See architecture-notes/opencorporates-fetch-plan.md section 5.
        """
        with PostgresCompanyRepository(config.database_url) as company_repository:
            return company_repository.read_unenriched_company_names(
                OPENCORPORATES_MAX_CALLS
            )

    return IngestionService(
        sources=[
            HackerNewsAdapter(),
            YcDirectoryAdapter(),
            OpenCorporatesAdapter(
                company_loader=load_opencorporates_companies,
                max_calls=OPENCORPORATES_MAX_CALLS,
            ),
        ],
        raw_store=PostgresApiIngestStore(
            api_ingest_repository,
            stable_fields_by_source={
                "opencorporates": OpenCorporatesAdapter.stable_fields
            },
        ),
        job_run_writer=PostgresJobRunWriter(config.database_url),
    )


def build_eu_startups_discovery_runner(config: Config) -> EuStartupsDiscoveryRunner:
    """Construct the source-specific transactional EU discovery pipeline."""
    return EuStartupsDiscoveryRunner(
        adapter=EuStartupsDiscoveryAdapter(),
        repository=PostgresEuStartupsDiscoveryRepository(config.database_url),
    )


def main(argv: Sequence[str] = ()) -> None:
    """Run the selected ingestion path. The application entrypoint, not library
    code, so it owns logging configuration (adr/0005-logging-required-from-day-one.md).

    With no command, preserve the shared HN/YC/OpenCorporates ingestion pass.
    The explicit ``eu-startups-discovery`` command invokes its dedicated
    transactional runner instead of changing ``IngestionService``.
    """
    parser = argparse.ArgumentParser(description="Run Huginn ingestion")
    parser.add_argument(
        "command",
        nargs="?",
        choices=(EU_STARTUPS_DISCOVERY_COMMAND,),
        help="optional source-specific ingestion command",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    config = load_config()
    if args.command == EU_STARTUPS_DISCOVERY_COMMAND:
        build_eu_startups_discovery_runner(config).run()
        return

    failed_count = build_service(config).run_once()
    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
