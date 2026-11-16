"""Self-service Business profile operations."""

from collections.abc import Callable

from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.business import Business
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class BusinessProfileService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._businesses_factory = businesses_factory

    def get(self, principal: Principal) -> Business:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            business = self._businesses_factory(uow).get_by_id(business_id)
            if business is None:
                raise NotFoundError("Business not found")
            return business

    def update(self, principal: Principal, changes: BusinessChanges) -> Business:
        with self._uow_factory() as uow:
            repository = self._businesses_factory(uow)
            business_id = business_id_for_principal(principal, repository)
            business = repository.update(business_id, changes)
            if business is None:
                raise NotFoundError("Business not found")
            if changes.supplied_fields:
                uow.commit()
            return business
