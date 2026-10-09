from dataclasses import dataclass

from huginn.pipeline_control.application.read_models.invocation_company_result import (
    InvocationCompanyResult,
)


@dataclass(frozen=True)
class ListInvocationCompaniesResponse:
    tracking_state: str
    items: tuple[InvocationCompanyResult, ...]
    total_count: int
    limit: int
    offset: int
    has_more: bool
