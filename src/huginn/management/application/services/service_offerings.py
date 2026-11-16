"""Owned ServiceOffering use cases."""

from collections.abc import Callable
from uuid import UUID

from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.service_offering import ServiceOffering
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import (
    Page,
    Principal,
)
from huginn.management.domain.value_objects.service_offering import (
    NewServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.persistence.contracts.postgresql import POSTGRES_BIGINT_MAX
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.repositories.service_offering import (
    ServiceOfferingRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class ServiceOfferingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
        offerings_factory: Callable[[UnitOfWorkProtocol], ServiceOfferingRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._businesses_factory = businesses_factory
        self._offerings_factory = offerings_factory

    def create(
        self, principal: Principal, *, name: str, description: str
    ) -> ServiceOffering:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._offerings_factory(uow).create(
                NewServiceOffering(business_id, name, description)
            )
            uow.commit()
            return value

    def list(
        self, principal: Principal, *, limit: int, offset: int
    ) -> Page[ServiceOffering]:
        if offset > POSTGRES_BIGINT_MAX:
            return Page((), offset, limit, False)
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            return self._offerings_factory(uow).list_owned(
                business_id, limit=limit, offset=offset
            )

    def get(self, principal: Principal, offering_id: UUID) -> ServiceOffering:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._offerings_factory(uow).get_owned(business_id, offering_id)
            if value is None:
                raise NotFoundError("Offering not found")
            return value

    def update(
        self, principal: Principal, offering_id: UUID, changes: ServiceOfferingChanges
    ) -> ServiceOffering:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._offerings_factory(uow).update_owned(
                business_id, offering_id, changes
            )
            if value is None:
                raise NotFoundError("Offering not found")
            if changes.supplied_fields:
                uow.commit()
            return value

    def delete(self, principal: Principal, offering_id: UUID) -> None:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            if not self._offerings_factory(uow).delete_owned(business_id, offering_id):
                raise NotFoundError("Offering not found")
            uow.commit()
