from collections.abc import Callable

from huginn.matchmaking_control.application.protocols.run_reader import RunReader
from huginn.matchmaking_control.application.requests.list_user_results_request import (
    ListUserResultsRequest,
)
from huginn.matchmaking_control.application.responses.list_user_results_response import (
    ListUserResultsResponse,
)
from huginn.matchmaking_control.application.services.list_target_users_service import (
    _validate_page,
)


class ListUserResultsService:
    def __init__(self, reader_factory: Callable[[], RunReader]) -> None:
        self._reader_factory = reader_factory

    def execute(self, request: ListUserResultsRequest) -> ListUserResultsResponse:
        _validate_page(request.offset, request.limit)
        return ListUserResultsResponse(
            self._reader_factory().list_user_results(
                request.run_id, request.limit, request.offset, request.state
            )
        )
