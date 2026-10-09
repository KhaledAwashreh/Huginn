from dataclasses import dataclass

from huginn.pipeline_control.domain.entities.pipeline_invocation import (
    PipelineInvocation,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner


@dataclass(frozen=True)
class WorkerClaim:
    invocation: PipelineInvocation
    owner: ExecutionOwner
