"""Private Match insertion row, design section 5."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.matchmaking.domain.entities.match import Match, MatchStatus
from huginn.matchmaking.persistence.errors.database import DataIntegrityError


@dataclass(frozen=True)
class MatchRow:
    id: UUID
    user_id: UUID
    company_id: UUID
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    def to_domain(self) -> Match:
        if not all(
            isinstance(value, UUID)
            for value in (self.id, self.user_id, self.company_id)
        ):
            raise DataIntegrityError("Invalid Match identifier")
        if type(self.status) is not str or self.status not in MatchStatus:
            raise DataIntegrityError("Invalid Match status")
        if self.notes is not None and type(self.notes) is not str:
            raise DataIntegrityError("Invalid Match notes")
        for value in (self.created_at, self.updated_at):
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise DataIntegrityError("Invalid Match timestamp")
        return Match(
            self.id,
            self.user_id,
            self.company_id,
            MatchStatus(self.status),
            self.notes,
            self.created_at,
            self.updated_at,
        )
