"""CLI entrypoint: `python -m huginn.elt`. Runs the pipeline end to end:
Ingestion through Bronze, Silver staging and resolution, and Gold, in
dependency order. See architecture document section 5 (ingestion) and
section 4 (bronze/silver/gold), and
adr/0014-pipeline-entry-point-and-stage-failure-policy.md for the entry
point shape, the stage order and its dependency argument, and the
dependency-aware skip-on-failure policy this module implements.

Scoped to HN and YC today. OpenCorporates and EU-Startups are deferred
(user directive, not yet wired to Silver/Gold regardless): this module's
own ingestion stage constructs a narrower HN+YC-only `IngestionService`
rather than importing
`huginn.elt.ingestion.__main__.build_service`, so running this entrypoint
never needs `HUGINN_OPENCORPORATES_API_TOKEN` and never depends on Gold
already holding rows (which `build_service`'s OpenCorporates wiring does,
to pick candidate company names). `python -m huginn.elt.ingestion` keeps
working unchanged for ingestion-only, OpenCorporates included.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from huginn.config import Config, load_config
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.gold.company import CompanyWriter
from huginn.elt.gold.company_signal import CompanySignalWriter
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository
from huginn.elt.gold.repositories.company_signal_repository import (
    PostgresCompanySignalRepository,
)
from huginn.elt.ingestion.adapters import yc
from huginn.elt.ingestion.adapters.hn import HackerNewsAdapter
from huginn.elt.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector
from huginn.elt.ingestion.connectors.firebase import FirebaseConnector
from huginn.elt.ingestion.service import IngestionService
from huginn.elt.silver.hn_staging import HnStagingLoader
from huginn.elt.silver.manual_review import ManualReviewQueuer
from huginn.elt.silver.repositories.hn_staging_repository import (
    PostgresHnStagingRepository,
)
from huginn.elt.silver.repositories.manual_review_repository import (
    PostgresManualReviewRepository,
)
from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.repositories.yc_staging_repository import (
    PostgresYcStagingRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver
from huginn.elt.silver.yc_staging import YcStagingLoader
from huginn.ops.job_runs import (
    JobRun,
    JobRunStatus,
    JobRunWriterPort,
    finish_job_run,
    start_job_run,
)
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Stage:
    """One pipeline unit. `name` doubles as the `ops.job_runs.source`
    label, widened by adr/0014 from "ingestion source" to "pipeline
    stage" (see `huginn.ops.job_runs`'s own docstring for the same note).

    `depends_on` names the stages (by `name`) this stage requires to have
    `SUCCEEDED` before it runs at all. `run_stages` below skips a stage,
    rather than calling it, when any dependency did not succeed
    (adr/0014's dependency-aware skip-on-failure policy, the same default
    dbt's `dbt run`/`dbt build` and Airflow's `all_success` trigger rule
    use: a stage with no dependency on a failure is unaffected by it).
    """

    name: str
    run: Callable[[], int]
    depends_on: tuple[str, ...] = ()


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
        sources=[
            HackerNewsAdapter(firebase=FirebaseConnector()),
            YcDirectoryAdapter(
                algolia=AlgoliaConnector(
                    app_id=yc.YC_ALGOLIA_APP_ID,
                    index=yc.YC_ALGOLIA_INDEX,
                    api_key=config.yc_algolia_api_key,
                )
            ),
        ],
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
    signal_resolver = SignalResolver(
        PostgresSignalResolutionRepository(config.database_url)
    )
    manual_review_queuer = ManualReviewQueuer(
        PostgresManualReviewRepository(config.database_url)
    )
    company_writer = CompanyWriter(PostgresCompanyRepository(config.database_url))
    company_signal_writer = CompanySignalWriter(
        PostgresCompanySignalRepository(config.database_url)
    )

    return [
        Stage(name="ingestion", run=lambda: _run_ingestion(config)),
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
            name="silver.signal_resolution",
            run=signal_resolver.resolve_all,
            depends_on=("silver.hn_staging", "silver.yc_staging"),
        ),
        Stage(
            name="silver.manual_review",
            run=manual_review_queuer.queue_unmatched,
            depends_on=("silver.signal_resolution",),
        ),
        Stage(
            name="gold.company",
            run=company_writer.write_all,
            depends_on=("silver.signal_resolution",),
        ),
        Stage(
            name="gold.company_signal",
            run=company_signal_writer.write_all,
            depends_on=("silver.signal_resolution", "gold.company"),
        ),
    ]


def _safe_write_job_run(job_run_writer: JobRunWriterPort, job_run: JobRun) -> None:
    """Persist `job_run`, logging rather than raising on failure. Mirrors
    `IngestionService._safe_write_job_run`: a `job_run_writer` write is
    bookkeeping, not the stage's own work, and must never abort the stage
    loop the way a genuine stage failure does.
    """
    try:
        job_run_writer.write(job_run)
    except Exception:
        logger.exception(
            "stage %s: failed to persist job_run state (id=%s, status=%s)",
            job_run.source,
            job_run.id,
            job_run.status,
        )


def run_stages(stages: list[Stage], job_run_writer: JobRunWriterPort) -> dict[str, str]:
    """Run every stage in order, writing an `ops.job_runs` row per stage
    and returning each stage's final status keyed by `Stage.name`.

    Dependency-aware skip-on-failure (adr/0014): a stage runs only if
    every stage named in its `depends_on` reached `SUCCEEDED`. Otherwise
    it is recorded `SKIPPED` without being called at all, and a `SKIPPED`
    stage propagates to its own dependents the same way a `FAILED` one
    does, since neither is `SUCCEEDED`. A stage with no unmet dependency
    always runs, regardless of what any unrelated stage did; only a
    stage's own real dependency chain can skip it.

    A stage that raises is caught here, at the stage boundary, and
    recorded `FAILED` with the error text; the loop continues to the next
    stage rather than aborting the whole run, so an unrelated stage still
    gets its chance. Zero rows returned from a stage is `SUCCEEDED`, not
    a failure: only a raised exception marks a stage `FAILED`.
    """
    statuses: dict[str, str] = {}
    for stage in stages:
        unmet_dependencies = [
            dependency
            for dependency in stage.depends_on
            if statuses.get(dependency) != JobRunStatus.SUCCEEDED
        ]
        if unmet_dependencies:
            logger.warning(
                "stage %s: skipped, dependency not succeeded: %s",
                stage.name,
                ", ".join(unmet_dependencies),
            )
            job_run = start_job_run(stage.name)
            job_run = finish_job_run(
                job_run,
                JobRunStatus.SKIPPED,
                error=f"dependency not succeeded: {', '.join(unmet_dependencies)}",
            )
            _safe_write_job_run(job_run_writer, job_run)
            statuses[stage.name] = JobRunStatus.SKIPPED
            continue

        job_run = start_job_run(stage.name)
        _safe_write_job_run(job_run_writer, job_run)
        started_at = time.monotonic()
        try:
            rows_written = stage.run()
        except Exception as exc:
            elapsed_seconds = time.monotonic() - started_at
            logger.exception(
                "stage %s: failed after %.1fs", stage.name, elapsed_seconds
            )
            job_run = finish_job_run(
                job_run, JobRunStatus.FAILED, error=str(exc) or repr(exc)
            )
            _safe_write_job_run(job_run_writer, job_run)
            statuses[stage.name] = JobRunStatus.FAILED
            continue

        elapsed_seconds = time.monotonic() - started_at
        logger.info(
            "stage %s: succeeded in %.1fs, %d row(s)",
            stage.name,
            elapsed_seconds,
            rows_written,
        )
        job_run = finish_job_run(
            job_run, JobRunStatus.SUCCEEDED, rows_written=rows_written
        )
        _safe_write_job_run(job_run_writer, job_run)
        statuses[stage.name] = JobRunStatus.SUCCEEDED

    return statuses


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
