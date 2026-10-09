"""Read collected Gold options without mutating pipeline or user definitions."""

from collections.abc import Callable

from huginn.management.application.protocols.configuration_options_query import (
    ConfigurationOptionsQuery,
)
from huginn.management.application.requests.get_configuration_options_request import (
    GetConfigurationOptionsRequest,
)
from huginn.management.application.responses.get_configuration_options_response import (
    GetConfigurationOptionsResponse,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class GetConfigurationOptionsService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        query_factory: Callable[[UnitOfWorkProtocol], ConfigurationOptionsQuery],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._query_factory = query_factory

    def execute(
        self, request: GetConfigurationOptionsRequest
    ) -> GetConfigurationOptionsResponse:
        with self._uow_factory() as uow:
            query = self._query_factory(uow)
            options = query.options()
            return GetConfigurationOptionsResponse(
                options.industries, options.countries, options.company_sizes
            )
