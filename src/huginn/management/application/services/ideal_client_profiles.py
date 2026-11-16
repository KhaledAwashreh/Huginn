"""Owned IdealClientProfile CRUD use cases."""

from collections.abc import Callable
from uuid import UUID

from huginn.management.application.policies.icp_selection import validate_icp_selection
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import (
    JsonObject,
    Page,
    Principal,
)
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.persistence.contracts.postgresql import POSTGRES_BIGINT_MAX
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.repositories.ideal_client_profile import (
    IdealClientProfileRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class IdealClientProfileService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], IdealClientProfileRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._businesses_factory = businesses_factory
        self._profiles_factory = profiles_factory

    def create(
        self,
        principal: Principal,
        *,
        name: str,
        industries: tuple[JsonObject, ...],
        company_sizes: tuple[JsonObject, ...],
        geographies: tuple[JsonObject, ...],
        exclusions: tuple[JsonObject, ...],
    ) -> IdealClientProfile:
        validate_icp_selection(industries, geographies, exclusions)
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._profiles_factory(uow).create(
                NewIdealClientProfile(
                    business_id,
                    name,
                    industries,
                    company_sizes,
                    geographies,
                    exclusions,
                )
            )
            uow.commit()
            return value

    def list(
        self, principal: Principal, *, limit: int, offset: int
    ) -> Page[IdealClientProfile]:
        if offset > POSTGRES_BIGINT_MAX:
            return Page((), offset, limit, False)
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            return self._profiles_factory(uow).list_owned(
                business_id, limit=limit, offset=offset
            )

    def get(self, principal: Principal, profile_id: UUID) -> IdealClientProfile:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._profiles_factory(uow).get_owned(business_id, profile_id)
            if value is None:
                raise NotFoundError("ICP not found")
            return value

    def update(
        self,
        principal: Principal,
        profile_id: UUID,
        changes: IdealClientProfileChanges,
    ) -> IdealClientProfile:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            value = self._profiles_factory(uow).update_owned(
                business_id, profile_id, changes
            )
            if value is None:
                raise NotFoundError("ICP not found")
            if changes.supplied_fields:
                # Validate the merged row while UPDATE holds its lock. A failed
                # validation rolls back, including competing partial patches.
                validate_icp_selection(
                    value.industries, value.geographies, value.exclusions
                )
                uow.commit()
            return value

    def delete(self, principal: Principal, profile_id: UUID) -> None:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            if not self._profiles_factory(uow).delete_owned(business_id, profile_id):
                raise NotFoundError("ICP not found")
            uow.commit()
