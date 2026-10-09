"""List owner matches without mutating operational state."""

from collections.abc import Callable

from huginn.management.application.protocols.matches_query import MatchesQuery
from huginn.management.application.requests.list_matches_request import (
    ListMatchesRequest,
)
from huginn.management.application.responses.list_matches_response import (
    ListMatchesResponse,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class ListMatchesService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], MatchesQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: ListMatchesRequest) -> ListMatchesResponse:
        with self._uow_factory() as uow:
            page = self._query_factory(uow).list_matches(
                request.principal.user_id, request.status, request.offset, request.limit
            )
            return ListMatchesResponse(page)
