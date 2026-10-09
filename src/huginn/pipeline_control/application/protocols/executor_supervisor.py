from typing import Protocol

from huginn.pipeline_control.application.protocols.execution_guard import ExecutionGuard
from huginn.pipeline_control.application.read_models.executor_identity import (
    ExecutorIdentity,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner


class ExecutorSupervisor(Protocol):
    def run(self, owner: ExecutionOwner, guard: ExecutionGuard) -> int: ...

    def prove_stopped(
        self, owner: ExecutionOwner, executor: ExecutorIdentity | None
    ) -> bool: ...
