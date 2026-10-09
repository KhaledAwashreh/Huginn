from collections.abc import Callable

from huginn.matchmaking_control.application.protocols.run_reader import RunReader
from huginn.matchmaking_control.application.requests.list_runs_request import (
    ListRunsRequest,
)
from huginn.matchmaking_control.application.responses.list_runs_response import (
    ListRunsResponse,
)
from huginn.matchmaking_control.application.services.list_target_users_service import (
    _validate_page,
)


class ListRunsService:
    def __init__(self, reader_factory: Callable[[], RunReader]) -> None:
        self._reader_factory = reader_factory

    def execute(self, request: ListRunsRequest) -> ListRunsResponse:
        _validate_page(request.offset, request.limit)
        return ListRunsResponse(
            self._reader_factory().list_runs(
                request.limit, request.offset, request.state
            )
        )
