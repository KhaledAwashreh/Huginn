"""Live ICP criterion choices."""

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.configuration_option import (
    ConfigurationOptionResponse,
)


class ConfigurationOptionsResponse(ResponseModel):
    industries: list[ConfigurationOptionResponse]
    countries: list[ConfigurationOptionResponse]
    company_sizes: list[ConfigurationOptionResponse]
