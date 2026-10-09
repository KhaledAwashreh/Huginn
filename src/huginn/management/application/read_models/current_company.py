"""Current Gold company fields shown as present-day context."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CurrentCompany:
    id: UUID
    name: str
    domain: str
    business_sector: tuple[str, ...] | None
    country: str | None
    company_scale: str | None
    company_status: str | None
