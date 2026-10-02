"""Authenticated self-service reads and updates for User and Profile."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from huginn.management.domain import (
    NotFoundError,
    Principal,
    ProfessionalProfileChanges,
    UserChanges,
)
from huginn.management.identity import (
    PostgresProfessionalProfileRepository,
    PostgresUserRepository,
)
from huginn.management.schemas import (
    ProfessionalProfilePatch,
    ProfessionalProfileRead,
    UserPatch,
    UserRead,
)


def _read_model(model: type[BaseModel], value: Any) -> dict[str, Any]:
    fields = {
        name: item
        for name, item in value.__dict__.items()
        if name in model.model_fields
    }
    for name in ("skills", "experience", "previous_projects"):
        if name in fields and isinstance(fields[name], tuple):
            fields[name] = list(fields[name])
    return model.model_validate(fields).model_dump(mode="json")


class UserProfileService:
    """Run each self-service operation on one caller-owned unit of work."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        users_factory: Callable[[Any], Any] | None = None,
        profiles_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._users_factory = users_factory or (
            lambda uow: PostgresUserRepository(uow.connection)
        )
        self._profiles_factory = profiles_factory or (
            lambda uow: PostgresProfessionalProfileRepository(uow.connection)
        )

    def get_user(self, principal: Principal) -> dict[str, Any]:
        with self._uow_factory() as uow:
            user = self._users_factory(uow).get_by_id(principal.user_id)
            if user is None:
                raise NotFoundError("User not found")
            return _read_model(UserRead, user)

    def update_user(self, principal: Principal, patch: UserPatch) -> dict[str, Any]:
        values = patch.model_dump(exclude_unset=True)
        with self._uow_factory() as uow:
            user = self._users_factory(uow).update(
                principal.user_id,
                UserChanges(values=values, supplied_fields=patch.supplied_fields),
            )
            if user is None:
                raise NotFoundError("User not found")
            response = _read_model(UserRead, user)
            uow.commit()
            return response

    def get_profile(self, principal: Principal) -> dict[str, Any]:
        with self._uow_factory() as uow:
            profile = self._profiles_factory(uow).get_owned(principal.user_id)
            if profile is None:
                raise NotFoundError("Professional profile not found")
            return _read_model(ProfessionalProfileRead, profile)

    def update_profile(
        self, principal: Principal, patch: ProfessionalProfilePatch
    ) -> dict[str, Any]:
        values = patch.model_dump(exclude_unset=True)
        for name in {
            "skills",
            "experience",
            "previous_projects",
        } & patch.supplied_fields:
            values[name] = tuple(
                item.model_dump(mode="json") for item in getattr(patch, name)
            )
        with self._uow_factory() as uow:
            profile = self._profiles_factory(uow).update_owned(
                principal.user_id,
                ProfessionalProfileChanges(
                    values=values, supplied_fields=patch.supplied_fields
                ),
            )
            if profile is None:
                raise NotFoundError("Professional profile not found")
            response = _read_model(ProfessionalProfileRead, profile)
            uow.commit()
            return response
