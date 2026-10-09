from types import TracebackType
from typing import Self

from huginn.management.persistence.contracts.database import (
    ConnectionFactory,
    DatabaseSession,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.pipeline_control.persistence.contracts.unit_of_work import (
    PipelineUnitOfWork,
)
from huginn.pipeline_control.persistence.repositories.execution_guard import (
    PostgresExecutionGuardRepository,
)
from huginn.pipeline_control.persistence.repositories.invocation import (
    PostgresInvocationRepository,
)
from huginn.pipeline_control.persistence.repositories.invocation_company_result import (
    PostgresInvocationCompanyResultRepository,
)
from huginn.pipeline_control.persistence.repositories.invocation_event import (
    PostgresInvocationEventRepository,
)
from huginn.pipeline_control.persistence.repositories.job_linkage import (
    PostgresJobLinkageRepository,
)
from huginn.pipeline_control.persistence.repositories.trigger_throttle import (
    PostgresTriggerThrottleRepository,
)


class PostgresPipelineUnitOfWork(PipelineUnitOfWork):
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._base = UnitOfWork(connection_factory)
        self.connection: DatabaseSession | None = None
        self.invocations: PostgresInvocationRepository
        self.events: PostgresInvocationEventRepository
        self.throttle: PostgresTriggerThrottleRepository
        self.job_linkage: PostgresJobLinkageRepository
        self.company_results: PostgresInvocationCompanyResultRepository
        self.execution_guard: PostgresExecutionGuardRepository

    def __enter__(self) -> Self:
        self._base.__enter__()
        self.connection = self._base.connection
        connection = self._require_connection()
        self.invocations = PostgresInvocationRepository(connection)
        self.events = PostgresInvocationEventRepository(connection)
        self.throttle = PostgresTriggerThrottleRepository(connection)
        self.job_linkage = PostgresJobLinkageRepository(connection)
        self.company_results = PostgresInvocationCompanyResultRepository(connection)
        self.execution_guard = PostgresExecutionGuardRepository(connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        result = self._base.__exit__(exc_type, exc_value, traceback)
        self.connection = None
        return result

    def commit(self) -> None:
        self._base.commit()

    def rollback(self) -> None:
        self._base.rollback()

    def _require_connection(self) -> DatabaseSession:
        if self.connection is None:
            raise RuntimeError("unit of work is not active")
        return self.connection
