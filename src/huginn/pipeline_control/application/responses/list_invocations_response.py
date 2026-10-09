from dataclasses import dataclass

from huginn.pipeline_control.application.read_models.invocation_summary import (
    InvocationSummary,
)


@dataclass(frozen=True)
class ListInvocationsResponse:
    items: tuple[InvocationSummary, ...]
    limit: int
    offset: int
    has_more: bool
