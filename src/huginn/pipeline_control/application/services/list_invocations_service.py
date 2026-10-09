from huginn.pipeline_control.application.protocols.invocation_reader import (
    InvocationReader,
)
from huginn.pipeline_control.application.requests.list_invocations_request import (
    ListInvocationsRequest,
)
from huginn.pipeline_control.application.responses.list_invocations_response import (
    ListInvocationsResponse,
)


class ListInvocationsService:
    def __init__(self, reader: InvocationReader) -> None:
        self._reader = reader

    def execute(self, request: ListInvocationsRequest) -> ListInvocationsResponse:
        if not 1 <= request.limit <= 100 or request.offset < 0:
            raise ValueError("invalid invocation pagination")
        if request.state is not None and request.state not in {
            "queued",
            "running",
            "succeeded",
            "failed",
            "interrupted",
        }:
            raise ValueError("invalid invocation state")
        rows = self._reader.list(request.limit + 1, request.offset, request.state)
        return ListInvocationsResponse(
            rows[: request.limit],
            request.limit,
            request.offset,
            len(rows) > request.limit,
        )
