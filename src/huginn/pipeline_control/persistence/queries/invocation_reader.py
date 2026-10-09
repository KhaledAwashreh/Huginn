from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from huginn.management.persistence.contracts.database import (
    ConnectionFactory,
)
from huginn.pipeline_control.application.constants.execution_policy import (
    STALE_AFTER_SECONDS,
)
from huginn.pipeline_control.application.read_models.event_entry import EventEntry
from huginn.pipeline_control.application.read_models.invocation_detail import (
    InvocationDetail,
)
from huginn.pipeline_control.application.read_models.invocation_summary import (
    InvocationSummary,
)
from huginn.pipeline_control.application.read_models.source_execution import (
    SourceExecution,
)
from huginn.pipeline_control.application.read_models.stage_execution import (
    StageExecution,
)
from huginn.pipeline_control.domain.value_objects.metric import Metric
from huginn.pipeline_control.domain.value_objects.stage_plan import StagePlan

_INVOCATION_FIELDS = (
    "id, requester_account_id, request_id, state, requested_at, started_at, finished_at, "
    "heartbeat_at, plan, safe_error_code, company_results_tracking_state"
)


class PostgresInvocationReader:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self, invocation_id: UUID) -> InvocationDetail | None:
        connection = self._connection_factory.connect()
        try:
            row = connection.execute(
                f"SELECT {_INVOCATION_FIELDS} FROM ops.pipeline_invocations WHERE id = %s",
                (invocation_id,),
            ).fetchone()
            if row is None:
                return None
            jobs = connection.execute(
                "SELECT id, source, started_at, finished_at, status, rows_written, error, parent_job_run_id, execution_kind "
                "FROM ops.job_runs WHERE invocation_id = %s ORDER BY started_at, id",
                (invocation_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT kind, stage_name, source_name, safe_code, safe_message "
                "FROM ops.pipeline_invocation_events WHERE invocation_id = %s ORDER BY sequence ASC",
                (invocation_id,),
            ).fetchall()
            return _detail(row, jobs, events, self._clock())
        finally:
            connection.close()

    def list(
        self, limit: int, offset: int, state: str | None
    ) -> tuple[InvocationSummary, ...]:
        connection = self._connection_factory.connect()
        try:
            params: tuple[Any, ...] = ()
            where = ""
            if state is not None:
                where = "WHERE state = %s"
                params = (state,)
            rows = connection.execute(
                f"SELECT id, requester_account_id, state, requested_at, started_at, finished_at, safe_error_code "
                f"FROM ops.pipeline_invocations {where} ORDER BY requested_at DESC, id DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            return tuple(InvocationSummary(*row) for row in rows)
        finally:
            connection.close()

    def events(
        self, invocation_id: UUID, after: int, limit: int
    ) -> tuple[EventEntry, ...]:
        connection = self._connection_factory.connect()
        try:
            rows = connection.execute(
                "SELECT id, sequence, occurred_at, kind, safe_code, safe_message, stage_name, source_name, metrics "
                "FROM ops.pipeline_invocation_events WHERE invocation_id = %s AND sequence > %s "
                "ORDER BY sequence ASC LIMIT %s",
                (invocation_id, after, limit),
            ).fetchall()
            return tuple(
                EventEntry(
                    id=row[0],
                    sequence=row[1],
                    occurred_at=row[2],
                    kind=row[3],
                    safe_code=row[4],
                    safe_message=row[5],
                    stage_name=row[6],
                    source_name=row[7],
                    metrics=_metrics(row[8]),
                )
                for row in rows
            )
        finally:
            connection.close()


def _detail(
    row: tuple[Any, ...],
    jobs: list[tuple[Any, ...]],
    events: list[tuple[Any, ...]],
    now: datetime,
) -> InvocationDetail:
    (
        invocation_id,
        requester,
        request_id,
        state,
        requested,
        started,
        finished,
        heartbeat,
        plan_json,
        safe_error,
        tracking,
    ) = row
    plan = StagePlan.from_json(plan_json)
    stages_by_name: dict[str, StageExecution] = {}
    sources: list[SourceExecution] = []
    stage_errors: dict[str, str] = {}
    stage_skips: dict[str, str] = {}
    source_errors: dict[str, str] = {}
    for kind, stage_name, source_name, safe_code, safe_message in events:
        if kind == "stage_failed" and stage_name is not None and safe_code:
            stage_errors[stage_name] = safe_code
        elif kind == "stage_skipped" and stage_name is not None and safe_message:
            stage_skips[stage_name] = safe_message
        elif kind == "source_failed" and source_name is not None and safe_code:
            source_errors[source_name] = safe_code
    for (
        job_id,
        name,
        job_started,
        job_finished,
        job_state,
        rows_written,
        _error,
        parent_id,
        kind,
    ) in jobs:
        metric = _job_metric(name, rows_written, job_state)
        if kind == "source":
            if parent_id is not None:
                if state == "interrupted" and job_state == "running":
                    job_state = "interrupted"
                sources.append(
                    SourceExecution(
                        name,
                        job_id,
                        parent_id,
                        job_state,
                        job_started,
                        job_finished,
                        (metric,),
                        source_errors.get(name),
                    )
                )
            continue
        stages_by_name[name] = StageExecution(
            name=name,
            order=-1,
            dependencies=(),
            state=job_state,
            job_run_id=job_id,
            started_at=job_started,
            finished_at=job_finished,
            metrics=(metric,),
            safe_error_code=stage_errors.get(name),
            skip_reason=stage_skips.get(name),
        )
    stages: list[StageExecution] = []
    for descriptor in plan.stages:
        execution = stages_by_name.get(descriptor.name)
        if execution is None:
            stage = StageExecution(
                descriptor.name,
                descriptor.order,
                descriptor.dependencies,
                "not_executed" if state == "interrupted" else "pending",
            )
        else:
            execution_state = execution.state
            if state == "interrupted" and execution_state == "running":
                execution_state = "interrupted"
            stage = StageExecution(
                execution.name,
                descriptor.order,
                descriptor.dependencies,
                execution_state,
                execution.job_run_id,
                execution.started_at,
                execution.finished_at,
                execution.metrics,
                execution.safe_error_code,
                execution.skip_reason,
            )
        stages.append(stage)
    freshness = (
        "stale"
        if state == "running"
        and (
            heartbeat is None
            or now - heartbeat > timedelta(seconds=STALE_AFTER_SECONDS)
        )
        else "fresh"
    )
    return InvocationDetail(
        invocation_id,
        requester,
        request_id,
        state,
        requested,
        started,
        finished,
        heartbeat,
        freshness,
        tuple(stages),
        tuple(sources),
        safe_error,
    )


def _job_metric(name: str, rows_written: int, status: str) -> Metric:
    value = rows_written if status == "succeeded" else None
    if name == "ingestion":
        return Metric("failed_sources", "sources", value)
    return Metric("rows_written", "rows", value)


def _metrics(raw: object) -> tuple[Metric, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        Metric(str(item["kind"]), str(item["unit"]), item.get("value"))
        for item in raw
        if isinstance(item, dict) and {"kind", "unit", "value"} <= item.keys()
    )
