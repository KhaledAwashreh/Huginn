from dataclasses import dataclass

from huginn.pipeline_control.application.read_models.invocation_detail import (
    InvocationDetail,
)


@dataclass(frozen=True)
class GetInvocationResponse:
    invocation: InvocationDetail
