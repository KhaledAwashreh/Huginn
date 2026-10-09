"""Current company fields presented as context for an existing Match."""

from huginn.management.presentation.api.responses.common import ResponseModel


class CurrentCompanyResponse(ResponseModel):
    name: str
    domain: str
    business_sector: list[str] | None
    country: str | None
    company_scale: str | None
    company_status: str | None
