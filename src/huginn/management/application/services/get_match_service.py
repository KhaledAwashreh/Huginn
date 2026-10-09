"""Read one owned match or return the shared not-found result."""

from collections.abc import Callable

from huginn.management.application.protocols.matches_query import MatchesQuery
from huginn.management.application.requests.get_match_request import GetMatchRequest
from huginn.management.application.responses.get_match_response import GetMatchResponse
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class GetMatchService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], MatchesQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: GetMatchRequest) -> GetMatchResponse:
        with self._uow_factory() as uow:
            match = self._query_factory(uow).get_match(
                request.principal.user_id, request.match_id
            )
            if match is None:
                raise NotFoundError("Match not found")
            return GetMatchResponse(match)
