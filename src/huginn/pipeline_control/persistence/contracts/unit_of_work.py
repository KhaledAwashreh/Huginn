from types import TracebackType
from typing import Protocol, Self

from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.pipeline_control.persistence.contracts.repositories.execution_guard import (
    ExecutionGuardRepository,
)
from huginn.pipeline_control.persistence.contracts.repositories.invocation import (
    InvocationRepository,
)
from huginn.pipeline_control.persistence.contracts.repositories.invocation_company_result import (
    InvocationCompanyResultRepository,
)
from huginn.pipeline_control.persistence.contracts.repositories.invocation_event import (
    InvocationEventRepository,
)
from huginn.pipeline_control.persistence.contracts.repositories.job_linkage import (
    JobLinkageRepository,
)
from huginn.pipeline_control.persistence.contracts.repositories.trigger_throttle import (
    TriggerThrottleRepository,
)


class PipelineUnitOfWork(Protocol):
    connection: DatabaseSession | None
    invocations: InvocationRepository
    events: InvocationEventRepository
    throttle: TriggerThrottleRepository
    execution_guard: ExecutionGuardRepository
    company_results: InvocationCompanyResultRepository
    job_linkage: JobLinkageRepository

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
