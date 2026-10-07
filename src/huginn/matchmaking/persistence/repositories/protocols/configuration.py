from typing import Protocol
from uuid import UUID

from huginn.matchmaking.application.read_models.strategy_configuration import (
    StrategyConfiguration,
)
from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)


class ConfigurationRepository(Protocol):
    def user_availability(self, user_id: UUID) -> UserAvailability: ...

    def list_active_strategies(
        self, user_id: UUID
    ) -> tuple[StrategyConfiguration, ...]: ...
