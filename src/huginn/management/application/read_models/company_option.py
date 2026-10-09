"""Public collected company label for a configuration exclusion."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompanyOption:
    id: UUID
    name: str
    domain: str | None
