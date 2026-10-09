"""Authenticated collected-options query input."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True)
class GetCompanyOptionRequest:
    principal: Principal
    company_id: UUID
