from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompanyAttributes:
    company_id: UUID
    business_sector: tuple[str | None, ...] | None
    company_scale: str | None
    country: str | None
