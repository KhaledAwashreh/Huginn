"""Private candidate query row, design section 5."""

from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.persistence.errors.database import DataIntegrityError


@dataclass(frozen=True)
class CompanyCandidateRow:
    company_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.company_id, UUID):
            raise DataIntegrityError("Invalid Company identifier")

    def to_read_model(self) -> CompanyCandidate:
        return CompanyCandidate(self.company_id)
