from typing import Protocol
from uuid import UUID

from huginn.matchmaking.domain.entities.match import Match


class MatchRepository(Protocol):
    def insert_if_absent(self, user_id: UUID, company_id: UUID) -> Match | None: ...
