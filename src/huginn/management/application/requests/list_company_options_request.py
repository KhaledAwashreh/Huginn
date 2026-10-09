"""Authenticated collected-options query input."""

from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True)
class ListCompanyOptionsRequest:
    principal: Principal
    search: str = ""
    offset: int = 0
    limit: int = 50
