"""Selected collected company label."""

from dataclasses import dataclass

from huginn.management.application.read_models.company_option import CompanyOption


@dataclass(frozen=True)
class GetCompanyOptionResponse:
    company: CompanyOption
