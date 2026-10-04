"""Owned IdealClientProfile use cases and framework-independent evaluation."""

from collections.abc import Callable
from uuid import UUID

from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import (
    Page,
    Principal,
)
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.persistence.contracts.postgresql import POSTGRES_BIGINT_MAX
from huginn.management.persistence.contracts.repositories.ideal_client_profile import (
    IdealClientProfileRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class IdealClientProfileService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        profiles_factory: Callable[[UnitOfWorkProtocol], IdealClientProfileRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._profiles_factory = profiles_factory

    def create(
        self, principal: Principal, profile: NewIdealClientProfile
    ) -> IdealClientProfile:
        with self._uow_factory() as uow:
            value = self._profiles_factory(uow).create(
                NewIdealClientProfile(
                    principal.user_id,
                    profile.name,
                    profile.industries,
                    profile.company_sizes,
                    profile.geographies,
                    profile.exclusions,
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
            return self._profiles_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset
            )

    def get(self, principal: Principal, profile_id: UUID) -> IdealClientProfile:
        with self._uow_factory() as uow:
            value = self._profiles_factory(uow).get_owned(principal.user_id, profile_id)
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
            value = self._profiles_factory(uow).update_owned(
                principal.user_id, profile_id, changes
            )
            if value is None:
                raise NotFoundError("ICP not found")
            if changes.supplied_fields:
                uow.commit()
            return value

    def delete(self, principal: Principal, profile_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._profiles_factory(uow).delete_owned(
                principal.user_id, profile_id
            ):
                raise NotFoundError("ICP not found")
            uow.commit()
