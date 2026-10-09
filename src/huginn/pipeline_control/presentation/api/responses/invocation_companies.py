from typing import Literal

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.invocation_company_result import (
    InvocationCompanyResultResponse,
)


class InvocationCompaniesResponse(ResponseModel):
    tracking_state: Literal["tracked", "unknown_legacy"]
    items: list[InvocationCompanyResultResponse]
    total_count: int
    limit: int
    offset: int
    has_more: bool
