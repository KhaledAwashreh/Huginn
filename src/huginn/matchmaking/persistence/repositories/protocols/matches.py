from typing import Protocol
from uuid import UUID

from huginn.matchmaking.domain.entities.match import Match
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


class MatchRepository(Protocol):
    def insert_if_absent(
        self,
        user_id: UUID,
        company_id: UUID,
        *,
        observation_ids: tuple[UUID, ...],
        window: SignalWindow,
    ) -> Match | None: ...
