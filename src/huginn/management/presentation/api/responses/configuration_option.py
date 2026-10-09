"""Collected criterion coverage HTTP shape."""

from pydantic import Field

from huginn.management.presentation.api.responses.common import ResponseModel


class ConfigurationOptionResponse(ResponseModel):
    value: str
    company_count: int = Field(ge=0)
