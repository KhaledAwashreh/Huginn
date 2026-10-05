"""Owned ClientDiscoveryStrategy use cases."""

from collections.abc import Callable
from uuid import UUID

from huginn.management.domain.entities.client_discovery_strategy import (
    ClientDiscoveryStrategy,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.value_objects.common import (
    Page,
    Principal,
)
from huginn.management.persistence.contracts.postgresql import POSTGRES_BIGINT_MAX
from huginn.management.persistence.contracts.repositories.discovery_strategy import (
    ClientDiscoveryStrategyRepository,
)
from huginn.management.persistence.contracts.repositories.ideal_client_profile import (
    IdealClientProfileRepository,
)
from huginn.management.persistence.contracts.repositories.service_offering import (
    ServiceOfferingRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class ClientDiscoveryStrategyService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        strategies_factory: Callable[
            [UnitOfWorkProtocol], ClientDiscoveryStrategyRepository
        ],
        offerings_factory: Callable[[UnitOfWorkProtocol], ServiceOfferingRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], IdealClientProfileRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._strategies_factory = strategies_factory
        self._offerings_factory = offerings_factory
        self._profiles_factory = profiles_factory

    def _require_references(
        self,
        uow: UnitOfWorkProtocol,
        user_id: UUID,
        offering_id: UUID,
        profile_id: UUID,
    ) -> None:
        if self._offerings_factory(uow).get_owned(user_id, offering_id) is None:
            raise NotFoundError("Strategy reference not found")
        if self._profiles_factory(uow).get_owned(user_id, profile_id) is None:
            raise NotFoundError("Strategy reference not found")

    def create(
        self, principal: Principal, strategy: NewClientDiscoveryStrategy
    ) -> ClientDiscoveryStrategy:
        with self._uow_factory() as uow:
            self._require_references(
                uow,
                principal.user_id,
                strategy.service_offering_id,
                strategy.ideal_client_profile_id,
            )
            value = self._strategies_factory(uow).create(
                NewClientDiscoveryStrategy(
                    principal.user_id,
                    strategy.name,
                    strategy.service_offering_id,
                    strategy.ideal_client_profile_id,
                    strategy.is_active,
                )
            )
            uow.commit()
            return value

    def list(
        self, principal: Principal, *, limit: int, offset: int, active: bool | None
    ) -> Page[ClientDiscoveryStrategy]:
        if offset > POSTGRES_BIGINT_MAX:
            return Page((), offset, limit, False)
        with self._uow_factory() as uow:
            return self._strategies_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset, active=active
            )

    def get(self, principal: Principal, strategy_id: UUID) -> ClientDiscoveryStrategy:
        with self._uow_factory() as uow:
            value = self._strategies_factory(uow).get_owned(
                principal.user_id, strategy_id
            )
            if value is None:
                raise NotFoundError("Strategy not found")
            return value

    def update(
        self,
        principal: Principal,
        strategy_id: UUID,
        changes: ClientDiscoveryStrategyChanges,
    ) -> ClientDiscoveryStrategy:
        with self._uow_factory() as uow:
            strategies = self._strategies_factory(uow)
            current = strategies.get_owned(principal.user_id, strategy_id)
            if current is None:
                raise NotFoundError("Strategy not found")
            values = changes.values
            if {
                "service_offering_id",
                "ideal_client_profile_id",
            } & changes.supplied_fields:
                self._require_references(
                    uow,
                    principal.user_id,
                    values.get("service_offering_id", current.service_offering_id),
                    values.get(
                        "ideal_client_profile_id", current.ideal_client_profile_id
                    ),
                )
            value = strategies.update_owned(principal.user_id, strategy_id, changes)
            if value is None:
                raise NotFoundError("Strategy not found")
            if changes.supplied_fields:
                uow.commit()
            return value

    def delete(self, principal: Principal, strategy_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._strategies_factory(uow).delete_owned(
                principal.user_id, strategy_id
            ):
                raise NotFoundError("Strategy not found")
            uow.commit()
