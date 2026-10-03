"""Owned ServiceOffering use cases."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from huginn.management.constants.pagination import POSTGRES_BIGINT_MAX
from huginn.management.domain.common import (
    Page,
    Principal,
)
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.errors.domain import NotFoundError
from huginn.management.repositories.protocols.service_offering import (
    ServiceOfferingRepository,
)


class ServiceOfferingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        offerings_factory: Callable[[Any], ServiceOfferingRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._offerings_factory = offerings_factory

    def create(
        self, principal: Principal, offering: NewServiceOffering
    ) -> ServiceOffering:
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).create(
                NewServiceOffering(
                    principal.user_id, offering.name, offering.description
                )
            )
            uow.commit()
            return value

    def list(
        self, principal: Principal, *, limit: int, offset: int
    ) -> Page[ServiceOffering]:
        if offset > POSTGRES_BIGINT_MAX:
            return Page((), offset, limit, False)
        with self._uow_factory() as uow:
            return self._offerings_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset
            )

    def get(self, principal: Principal, offering_id: UUID) -> ServiceOffering:
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).get_owned(
                principal.user_id, offering_id
            )
            if value is None:
                raise NotFoundError("Offering not found")
            return value

    def update(
        self, principal: Principal, offering_id: UUID, changes: ServiceOfferingChanges
    ) -> ServiceOffering:
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).update_owned(
                principal.user_id, offering_id, changes
            )
            if value is None:
                raise NotFoundError("Offering not found")
            if changes.supplied_fields:
                uow.commit()
            return value

    def delete(self, principal: Principal, offering_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._offerings_factory(uow).delete_owned(
                principal.user_id, offering_id
            ):
                raise NotFoundError("Offering not found")
            uow.commit()
