from collections.abc import Callable

from huginn.matchmaking_control.application.protocols.run_reader import RunReader
from huginn.matchmaking_control.application.requests.list_skipped_strategies_request import (
    ListSkippedStrategiesRequest,
)
from huginn.matchmaking_control.application.responses.list_skipped_strategies_response import (
    ListSkippedStrategiesResponse,
)
from huginn.matchmaking_control.application.services.list_target_users_service import (
    _validate_page,
)


class ListSkippedStrategiesService:
    def __init__(self, reader_factory: Callable[[], RunReader]) -> None:
        self._reader_factory = reader_factory

    def execute(
        self, request: ListSkippedStrategiesRequest
    ) -> ListSkippedStrategiesResponse:
        _validate_page(request.offset, request.limit)
        return ListSkippedStrategiesResponse(
            self._reader_factory().list_skipped_strategies(
                request.run_id, request.user_id, request.limit, request.offset
            )
        )
