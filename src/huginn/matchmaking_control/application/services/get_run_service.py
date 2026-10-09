from collections.abc import Callable

from huginn.matchmaking_control.application.protocols.run_reader import RunReader
from huginn.matchmaking_control.application.requests.get_run_request import (
    GetRunRequest,
)
from huginn.matchmaking_control.application.responses.get_run_response import (
    GetRunResponse,
)


class GetRunService:
    def __init__(self, reader_factory: Callable[[], RunReader]) -> None:
        self._reader_factory = reader_factory

    def execute(self, request: GetRunRequest) -> GetRunResponse:
        return GetRunResponse(self._reader_factory().get_run(request.run_id))
