from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompanyCandidate:
    company_id: UUID
