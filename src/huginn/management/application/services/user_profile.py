"""Self-service User and ProfessionalProfile use cases."""

from collections.abc import Callable

from huginn.management.domain.entities.professional_profile import ProfessionalProfile
from huginn.management.domain.entities.user import User
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.professional_profile import (
    ProfessionalProfileChanges,
)
from huginn.management.domain.value_objects.user import UserChanges
from huginn.management.persistence.contracts.repositories.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.persistence.contracts.repositories.user import UserRepository
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class UserProfileService:
    """Run each self-service operation in a caller-owned unit of work."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        users_factory: Callable[[UnitOfWorkProtocol], UserRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], ProfessionalProfileRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._users_factory = users_factory
        self._profiles_factory = profiles_factory

    def get_user(self, principal: Principal) -> User:
        with self._uow_factory() as uow:
            user = self._users_factory(uow).get_by_id(principal.user_id)
            if user is None:
                raise NotFoundError("User not found")
            return user

    def update_user(self, principal: Principal, changes: UserChanges) -> User:
        with self._uow_factory() as uow:
            user = self._users_factory(uow).update(principal.user_id, changes)
            if user is None:
                raise NotFoundError("User not found")
            uow.commit()
            return user

    def get_profile(self, principal: Principal) -> ProfessionalProfile:
        with self._uow_factory() as uow:
            profile = self._profiles_factory(uow).get_owned(principal.user_id)
            if profile is None:
                raise NotFoundError("Professional profile not found")
            return profile

    def update_profile(
        self, principal: Principal, changes: ProfessionalProfileChanges
    ) -> ProfessionalProfile:
        with self._uow_factory() as uow:
            profile = self._profiles_factory(uow).update(principal.user_id, changes)
            if profile is None:
                raise NotFoundError("Professional profile not found")
            uow.commit()
            return profile
