"""Bounded collected company choices."""

from dataclasses import dataclass

from huginn.management.application.read_models.company_option import CompanyOption
from huginn.management.domain.value_objects.common import Page


@dataclass(frozen=True)
class ListCompanyOptionsResponse:
    page: Page[CompanyOption]
