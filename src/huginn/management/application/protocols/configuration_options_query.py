"""Read-only Gold choices consumed by definition forms."""

from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.company_option import CompanyOption
from huginn.management.application.read_models.configuration_options import (
    ConfigurationOptions,
)
from huginn.management.domain.value_objects.common import Page


class ConfigurationOptionsQuery(Protocol):
    def options(self) -> ConfigurationOptions: ...
    def companies(
        self, search: str, offset: int, limit: int
    ) -> Page[CompanyOption]: ...
    def company(self, company_id: UUID) -> CompanyOption | None: ...
