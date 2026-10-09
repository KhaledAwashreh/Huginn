from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.application.read_models.invocation_summary import (
    InvocationSummary,
)


class InvocationHistoryResponse(ResponseModel):
    items: list[InvocationSummary]
    limit: int
    offset: int
    has_more: bool
