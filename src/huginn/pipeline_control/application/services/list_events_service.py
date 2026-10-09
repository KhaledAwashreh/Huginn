from huginn.pipeline_control.application.errors.invocation import (
    InvocationNotFoundError,
)
from huginn.pipeline_control.application.protocols.invocation_reader import (
    InvocationReader,
)
from huginn.pipeline_control.application.requests.list_events_request import (
    ListEventsRequest,
)
from huginn.pipeline_control.application.responses.list_events_response import (
    ListEventsResponse,
)


class ListEventsService:
    def __init__(self, reader: InvocationReader) -> None:
        self._reader = reader

    def execute(self, request: ListEventsRequest) -> ListEventsResponse:
        if request.after_sequence < 0 or not 1 <= request.limit <= 100:
            raise ValueError("invalid event pagination")
        if self._reader.get(request.invocation_id) is None:
            raise InvocationNotFoundError("invocation not found")
        rows = self._reader.events(
            request.invocation_id, request.after_sequence, request.limit + 1
        )
        items = rows[: request.limit]
        next_sequence = items[-1].sequence if items else request.after_sequence
        return ListEventsResponse(items, next_sequence, len(rows) > request.limit)
