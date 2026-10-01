"""CLI entrypoint: `python -m huginn.elt`. Runs the pipeline end to end:
Ingestion through Bronze, Silver staging and resolution, and Gold, in
dependency order. See architecture document section 5 (ingestion) and
section 4 (bronze/silver/gold), and
adr/0014-pipeline-entry-point-and-stage-failure-policy.md for the entry
point shape, the stage order and its dependency argument, and the
dependency-aware skip-on-failure policy this module implements.

Scoped to HN, YC, and EU-Startups today. OpenCorporates remains deferred:
this module's API ingestion stage builds its `IngestionService` from
`huginn.elt.ingestion.__main__.build_hn_yc_sources`, the HN+YC-only
subset `build_service` also uses, rather than `build_service` itself, so
running this entrypoint never needs `HUGINN_OPENCORPORATES_API_TOKEN` and
never depends on Gold already holding rows (which `build_service`'s
OpenCorporates wiring does, to pick candidate company names).
`python -m huginn.elt.ingestion` keeps working unchanged for
ingestion-only, OpenCorporates included.
"""

from __future__ import annotations

import logging
import sys

from huginn.config import Config, load_config
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.ingestion.__main__ import (
    build_eu_startups_discovery_runner,
    build_hn_yc_sources,
)
from huginn.elt.ingestion.service import IngestionService
from huginn.elt.materialization import build_eu_startups_materialization_stages
from huginn.elt.silver.hn_staging import HnStagingLoader
from huginn.elt.silver.repositories.hn_staging_repository import (
    PostgresHnStagingRepository,
)
from huginn.elt.silver.repositories.yc_staging_repository import (
    PostgresYcStagingRepository,
)
from huginn.elt.silver.yc_staging import YcStagingLoader
from huginn.elt.stage_runner import Stage, run_stages
from huginn.ops.job_runs import JobRunStatus
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter

logger = logging.getLogger(__name__)


def _run_ingestion(config: Config) -> int:
    """Fetch HN and YC once and write to Bronze.

    `IngestionService.run_once()` already isolates HN's and YC's failures
    from each other, writing its own per-source `ops.job_runs` row for
    each (`huginn.elt.ingestion.service`'s own docstring) and returning
    the count that failed. That per-source detail already lives in its
    own rows, so this function's return value, and therefore this
    stage's own `rows_written`, is that same failed-source count, always
    0 when this function returns at all: a nonzero count raises instead,
    so `run_stages` records this stage `FAILED` and every stage
    depending on it (`silver.hn_staging`, `silver.yc_staging`) is
    skipped rather than running against a run that did not complete.
    """
    service = IngestionService(
        sources=build_hn_yc_sources(config),
        raw_store=PostgresApiIngestStore(
            PostgresApiIngestRepository(config.database_url)
        ),
        job_run_writer=PostgresJobRunWriter(config.database_url),
    )
    failed_count = service.run_once()
    if failed_count:
        raise RuntimeError(
            f"{failed_count} ingestion source(s) failed this run; see the "
            "per-source rows this call already wrote to ops.job_runs for detail"
        )
    return failed_count


def build_stages(config: Config) -> list[Stage]:
    """Construct every stage with its real, Postgres-backed dependencies,
    in the order adr/0014 fixes. DB-free: every repository connects in
    `__enter__`, not `__init__`
    (`silver/repositories/postgres_repository.py:21`), so building this
    list makes no database or network call (CLAUDE.md code standard 4).
    """
    hn_staging_loader = HnStagingLoader(
        PostgresHnStagingRepository(config.database_url)
    )
    yc_staging_loader = YcStagingLoader(
        PostgresYcStagingRepository(config.database_url)
    )
    eu_startups_discovery_runner = build_eu_startups_discovery_runner(config)
    eu_stages = build_eu_startups_materialization_stages(
        config,
        resolution_dependencies=(
            "silver.hn_staging",
            "silver.yc_staging",
            "silver.eu_startups_staging",
        ),
    )

    return [
        Stage(name="ingestion", run=lambda: _run_ingestion(config)),
        Stage(
            name="ingestion.eu_startups",
            # The runner records the source transaction as `eu_startups`;
            # run_stages records this orchestration boundary separately as
            # `ingestion.eu_startups`, matching the aggregate `ingestion`
            # stage plus its per-source HN/YC records.
            run=eu_startups_discovery_runner.run,
        ),
        Stage(
            name="silver.hn_staging",
            run=hn_staging_loader.load,
            depends_on=("ingestion",),
        ),
        Stage(
            name="silver.yc_staging",
            run=yc_staging_loader.load,
            depends_on=("ingestion",),
        ),
        Stage(
            name="silver.eu_startups_staging",
            run=eu_stages[0].run,
            depends_on=("ingestion.eu_startups",),
        ),
        Stage(
            name="silver.signal_resolution",
            run=eu_stages[1].run,
            # resolve_all reads all three staging tables in one batch. Until
            # resolution is split into per-source stages, each loader is a
            # direct dependency; running after one fails would consume that
            # source's stale Silver rows.
            depends_on=eu_stages[1].depends_on,
        ),
        *eu_stages[2:],
    ]


def main() -> None:
    """Run one pipeline pass. The application entrypoint, not library
    code, so it owns logging configuration
    (adr/0005-logging-required-from-day-one.md).

    Exits non-zero if any stage did not reach `SUCCEEDED` (`FAILED` or
    `SKIPPED`): the exit code is the only signal cron-based alerting can
    act on, matching `huginn.elt.ingestion.__main__.main`'s own reasoning.

    A missing required config variable is logged and exits 1 the same
    way as the ingestion entrypoint, before any stage or job_run exists.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    try:
        config = load_config()
    except RuntimeError as error:
        logger.error("%s", error)
        sys.exit(1)

    stages = build_stages(config)
    job_run_writer = PostgresJobRunWriter(config.database_url)
    statuses = run_stages(stages, job_run_writer)
    if any(status != JobRunStatus.SUCCEEDED for status in statuses.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
