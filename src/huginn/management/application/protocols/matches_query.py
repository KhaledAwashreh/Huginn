"""Read query boundary; architecture.md sections 4.4 and 9."""

from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)
from huginn.management.application.read_models.matches_overview import MatchesOverview
from huginn.management.application.read_models.user_match import UserMatch
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.match_status import MatchStatus


class MatchesQuery(Protocol):
    def list_matches(
        self, user_id: UUID, status: MatchStatus | None, offset: int, limit: int
    ) -> Page[UserMatch]: ...

    def get_match(self, user_id: UUID, match_id: UUID) -> UserMatch | None: ...

    def list_match_signals(
        self, user_id: UUID, match_id: UUID, offset: int, limit: int
    ) -> Page[CurrentCompanySignal]: ...

    def overview_for(self, user_id: UUID) -> MatchesOverview: ...
