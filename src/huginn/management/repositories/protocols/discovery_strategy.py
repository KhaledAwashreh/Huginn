"""Discovery strategy persistence and reference validation contracts."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.client_discovery_strategy import (
    ClientDiscoveryStrategy,
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.common import Page, Principal


class ClientDiscoveryStrategyRepository(Protocol):
    def create(
        self, strategy: NewClientDiscoveryStrategy
    ) -> ClientDiscoveryStrategy: ...
    def get_owned(
        self, user_id: UUID, strategy_id: UUID
    ) -> ClientDiscoveryStrategy | None: ...
    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int, active: bool | None = None
    ) -> Page[ClientDiscoveryStrategy]: ...
    def update_owned(
        self, user_id: UUID, strategy_id: UUID, changes: ClientDiscoveryStrategyChanges
    ) -> ClientDiscoveryStrategy | None: ...
    def delete_owned(self, user_id: UUID, strategy_id: UUID) -> bool: ...


class OwnedResourceValidator(Protocol):
    def validate_strategy_references(
        self, principal: Principal, offering_id: UUID, profile_id: UUID
    ) -> None: ...
