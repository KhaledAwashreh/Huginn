"""Collected company name and identity used by exclusions."""

from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class CompanyOptionResponse(ResponseModel):
    id: UUID
    name: str
    domain: str | None
