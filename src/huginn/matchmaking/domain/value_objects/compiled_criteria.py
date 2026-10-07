from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompiledCriteria:
    industries: tuple[str, ...]
    company_sizes: tuple[str, ...]
    countries: tuple[str, ...]
    excluded_company_ids: tuple[UUID, ...]
    excluded_industries: tuple[str, ...]
    excluded_countries: tuple[str, ...]
