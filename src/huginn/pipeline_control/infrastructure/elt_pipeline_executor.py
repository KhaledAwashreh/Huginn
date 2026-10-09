"""Compose the existing full ELT graph, never replay pipeline policy."""

from uuid import UUID

from huginn.config import Config
from huginn.elt.__main__ import build_stages
from huginn.elt.stage_runner import run_stages
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.ops.job_runs import JobRunStatus
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter
from huginn.pipeline_control.application.read_models.tracking_context import (
    TrackingContext,
)
from huginn.pipeline_control.infrastructure.invocation_job_run_writer import (
    InvocationJobRunWriter,
)
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)


class EltPipelineExecutor:
    def __init__(self, config: Config) -> None:
        self._config = config

    def run(self, invocation_id: UUID | None) -> int:
        writer = PostgresJobRunWriter(self._config.database_url)
        if invocation_id is not None:
            factory = ManagementConnectionFactory(
                self._config.database_url, statement_timeout_ms=2000
            )
            writer = InvocationJobRunWriter(
                writer,
                TrackingContext(invocation_id, UUID(int=0), ""),
                event_uow_factory=lambda: PostgresPipelineUnitOfWork(factory),
            )
        statuses = run_stages(
            build_stages(self._config),
            writer,
            invocation_id=invocation_id,
            strict_tracking=invocation_id is not None,
        )
        return int(
            any(status != JobRunStatus.SUCCEEDED for status in statuses.values())
        )
