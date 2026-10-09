"""Authenticated read-only collected configuration choices."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from huginn.management.application.requests.get_company_option_request import (
    GetCompanyOptionRequest,
)
from huginn.management.application.requests.get_configuration_options_request import (
    GetConfigurationOptionsRequest,
)
from huginn.management.application.requests.list_company_options_request import (
    ListCompanyOptionsRequest,
)
from huginn.management.presentation.api.dependencies.authentication import Authenticated
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.company_option import (
    CompanyOptionResponse,
)
from huginn.management.presentation.api.responses.configuration_option import (
    ConfigurationOptionResponse,
)
from huginn.management.presentation.api.responses.configuration_options import (
    ConfigurationOptionsResponse,
)

router = APIRouter(
    prefix="/api/v1/configuration-options", tags=["configuration options"]
)


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


@router.get(
    "", response_model=ConfigurationOptionsResponse, responses=error_responses(401)
)
def get_options(
    authenticated: Authenticated, response: Response, dependencies: Management
) -> ConfigurationOptionsResponse:
    result = dependencies.get_configuration_options_service.execute(
        GetConfigurationOptionsRequest(authenticated.principal)
    )
    _private(response)
    return ConfigurationOptionsResponse(
        **{
            field: [
                ConfigurationOptionResponse(
                    value=item.value, company_count=item.company_count
                )
                for item in getattr(result, field)
            ]
            for field in ("industries", "countries", "company_sizes")
        }
    )


@router.get(
    "/companies",
    response_model=PageResponse[CompanyOptionResponse],
    responses=error_responses(401, 422),
)
def list_companies(
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
    search: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PageResponse[CompanyOptionResponse]:
    page = dependencies.list_company_options_service.execute(
        ListCompanyOptionsRequest(authenticated.principal, search, offset, limit)
    ).page
    _private(response)
    return PageResponse[CompanyOptionResponse](
        items=[
            CompanyOptionResponse(id=item.id, name=item.name, domain=item.domain)
            for item in page.items
        ],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/companies/{company_id}",
    response_model=CompanyOptionResponse,
    responses=error_responses(401, 404, 422),
)
def get_company(
    company_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
) -> CompanyOptionResponse:
    item = dependencies.get_company_option_service.execute(
        GetCompanyOptionRequest(authenticated.principal, company_id)
    ).company
    _private(response)
    return CompanyOptionResponse(id=item.id, name=item.name, domain=item.domain)
