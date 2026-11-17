"""Discovery strategy persistence and reference validation contracts."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.client_discovery_strategy import (
    ClientDiscoveryStrategy,
)
from huginn.management.domain.value_objects.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.value_objects.common import Page, Principal


class ClientDiscoveryStrategyRepository(Protocol):
    def set_single_configuration(
        self, business_id: UUID, offering_id: UUID, profile_id: UUID
    ) -> ClientDiscoveryStrategy: ...

    def create(
        self, strategy: NewClientDiscoveryStrategy
    ) -> ClientDiscoveryStrategy: ...
    def get_owned(
        self, business_id: UUID, strategy_id: UUID
    ) -> ClientDiscoveryStrategy | None: ...
    def list_owned(
        self, business_id: UUID, *, limit: int, offset: int, active: bool | None = None
    ) -> Page[ClientDiscoveryStrategy]: ...
    def update_owned(
        self,
        business_id: UUID,
        strategy_id: UUID,
        changes: ClientDiscoveryStrategyChanges,
    ) -> ClientDiscoveryStrategy | None: ...
    def delete_owned(self, business_id: UUID, strategy_id: UUID) -> bool: ...


class OwnedResourceValidator(Protocol):
    def validate_strategy_references(
        self, principal: Principal, offering_id: UUID, profile_id: UUID
    ) -> None: ...
