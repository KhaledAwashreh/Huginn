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
    observation_ids: list[UUID]

    def __post_init__(self) -> None:
        if not isinstance(self.company_id, UUID):
            raise DataIntegrityError("Invalid Company identifier")
        if (
            not isinstance(self.observation_ids, list)
            or not self.observation_ids
            or any(not isinstance(item, UUID) for item in self.observation_ids)
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise DataIntegrityError("Invalid candidate evidence identifiers")

    def to_read_model(self) -> CompanyCandidate:
        return CompanyCandidate(self.company_id, tuple(self.observation_ids))
