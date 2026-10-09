"""Read owner-wide state used to explain a genuinely empty match list."""

from collections.abc import Callable

from huginn.management.application.protocols.matches_query import MatchesQuery
from huginn.management.application.requests.get_matches_overview_request import (
    GetMatchesOverviewRequest,
)
from huginn.management.application.responses.get_matches_overview_response import (
    GetMatchesOverviewResponse,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class GetMatchesOverviewService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], MatchesQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: GetMatchesOverviewRequest) -> GetMatchesOverviewResponse:
        with self._uow_factory() as uow:
            return GetMatchesOverviewResponse(
                self._query_factory(uow).overview_for(request.principal.user_id)
            )
