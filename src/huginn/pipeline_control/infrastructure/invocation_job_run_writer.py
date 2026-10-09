"""Explicit source and stage lineage. See pipeline control design section 7."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from huginn.ops.job_runs import JobRun, JobRunWriterPort
from huginn.pipeline_control.application.errors.execution import TrackingUncertainError
from huginn.pipeline_control.application.read_models.tracking_context import (
    TrackingContext,
)
from huginn.pipeline_control.domain.value_objects.metric import Metric
from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.persistence.contracts.unit_of_work import (
    PipelineUnitOfWork,
)


class InvocationJobRunWriter:
    strict_tracking = True

    def __init__(
        self,
        writer: JobRunWriterPort,
        context: TrackingContext,
        *,
        source: bool = False,
        event_uow_factory: Callable[[], PipelineUnitOfWork] | None = None,
    ) -> None:
        self._writer = writer
        self._context = context
        self._source = source
        self._event_uow_factory = event_uow_factory

    def write(self, job_run: JobRun) -> None:
        linked = replace(
            job_run,
            invocation_id=str(self._context.invocation_id),
            parent_job_run_id=str(self._context.stage_job_run_id)
            if self._source
            else None,
            execution_kind="source" if self._source else "stage",
        )
        try:
            self._writer.write(linked)
            if self._event_uow_factory is not None:
                prefix = "source" if self._source else "stage"
                suffix = "started" if linked.status == "running" else linked.status
                kind = (
                    "failed_sources" if linked.source == "ingestion" else "rows_written"
                )
                unit = "sources" if kind == "failed_sources" else "rows"
                value = linked.rows_written if linked.status == "succeeded" else None
                message = f"{prefix.capitalize()} {suffix}."
                if linked.status == "skipped":
                    dependencies = (
                        (linked.error or "")
                        .removeprefix("dependency not succeeded: ")
                        .split(", ")
                    )
                    allowed_names = {
                        stage.name for stage in SUPPORTED_STAGE_PLAN.stages
                    }
                    if dependencies and all(
                        name in allowed_names for name in dependencies
                    ):
                        message = "Dependency not succeeded: " + ", ".join(dependencies)
                event = PipelineEvent(
                    self._context.invocation_id,
                    f"{prefix}_{suffix}",
                    datetime.now(UTC),
                    safe_code=f"{prefix}_{suffix}"
                    if linked.status in ("failed", "skipped")
                    else None,
                    safe_message=message,
                    stage_name=self._context.stage_name
                    if self._source
                    else linked.source,
                    source_name=linked.source if self._source else None,
                    metrics=(Metric(kind, unit, value),),
                )
                with self._event_uow_factory() as uow:
                    uow.events.append(event, f"{linked.id}:{linked.status}")
                    uow.commit()
        except Exception:
            raise TrackingUncertainError("tracking_unavailable") from None
