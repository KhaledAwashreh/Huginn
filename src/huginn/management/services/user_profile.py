"""Self-service User and ProfessionalProfile use cases."""

from collections.abc import Callable
from typing import Any

from huginn.management.domain.common import Principal
from huginn.management.domain.professional_profile import (
    ProfessionalProfile,
    ProfessionalProfileChanges,
)
from huginn.management.domain.user import (
    User,
    UserChanges,
)
from huginn.management.errors.domain import NotFoundError
from huginn.management.repositories.protocols.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.repositories.protocols.user import UserRepository


class UserProfileService:
    """Run each self-service operation in a caller-owned unit of work."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        users_factory: Callable[[Any], UserRepository],
        profiles_factory: Callable[[Any], ProfessionalProfileRepository],
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
