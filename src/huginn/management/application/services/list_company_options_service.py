"""Read collected Gold options without mutating pipeline or user definitions."""

from collections.abc import Callable

from huginn.management.application.protocols.configuration_options_query import (
    ConfigurationOptionsQuery,
)
from huginn.management.application.requests.list_company_options_request import (
    ListCompanyOptionsRequest,
)
from huginn.management.application.responses.list_company_options_response import (
    ListCompanyOptionsResponse,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class ListCompanyOptionsService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], ConfigurationOptionsQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: ListCompanyOptionsRequest) -> ListCompanyOptionsResponse:
        with self._uow_factory() as uow:
            query = self._query_factory(uow)
            return ListCompanyOptionsResponse(
                query.companies(request.search, request.offset, request.limit)
            )
