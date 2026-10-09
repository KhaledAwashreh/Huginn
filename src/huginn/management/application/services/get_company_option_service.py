"""Read collected Gold options without mutating pipeline or user definitions."""

from collections.abc import Callable

from huginn.management.application.protocols.configuration_options_query import (
    ConfigurationOptionsQuery,
)
from huginn.management.application.requests.get_company_option_request import (
    GetCompanyOptionRequest,
)
from huginn.management.application.responses.get_company_option_response import (
    GetCompanyOptionResponse,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class GetCompanyOptionService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], ConfigurationOptionsQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(self, request: GetCompanyOptionRequest) -> GetCompanyOptionResponse:
        with self._uow_factory() as uow:
            query = self._query_factory(uow)
            company = query.company(request.company_id)
            if company is None:
                raise NotFoundError("Company option not found")
            return GetCompanyOptionResponse(company)
