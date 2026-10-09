from huginn.pipeline_control.application.errors.invocation import (
    InvocationNotFoundError,
)
from huginn.pipeline_control.application.protocols.invocation_company_reader import (
    InvocationCompanyReader,
)
from huginn.pipeline_control.application.requests.list_invocation_companies_request import (
    ListInvocationCompaniesRequest,
)
from huginn.pipeline_control.application.responses.list_invocation_companies_response import (
    ListInvocationCompaniesResponse,
)


class ListInvocationCompaniesService:
    def __init__(self, reader: InvocationCompanyReader) -> None:
        self._reader = reader

    def execute(
        self, request: ListInvocationCompaniesRequest
    ) -> ListInvocationCompaniesResponse:
        if not 1 <= request.limit <= 100 or request.offset < 0:
            raise ValueError("invalid company results pagination")
        state, items, total = self._reader.read(
            request.invocation_id, request.limit, request.offset
        )
        if state == "not_found":
            raise InvocationNotFoundError("invocation not found")
        if state not in {"tracked", "unknown_legacy"}:
            raise ValueError("invalid company tracking state")
        return ListInvocationCompaniesResponse(
            state,
            items,
            total,
            request.limit,
            request.offset,
            request.offset + len(items) < total,
        )
