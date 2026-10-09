"""Read current signals after verifying ownership of their Match."""

from collections.abc import Callable

from huginn.management.application.protocols.matches_query import MatchesQuery
from huginn.management.application.requests.list_match_signals_request import (
    ListMatchSignalsRequest,
)
from huginn.management.application.responses.list_match_signals_response import (
    ListMatchSignalsResponse,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class ListMatchSignalsService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], MatchesQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: ListMatchSignalsRequest) -> ListMatchSignalsResponse:
        with self._uow_factory() as uow:
            query = self._query_factory(uow)
            if query.get_match(request.principal.user_id, request.match_id) is None:
                raise NotFoundError("Match not found")
            return ListMatchSignalsResponse(
                query.list_match_signals(
                    request.principal.user_id,
                    request.match_id,
                    request.offset,
                    request.limit,
                )
            )
