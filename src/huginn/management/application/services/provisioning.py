"""Owner-controlled identity provisioning use case."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.domain.errors.errors import (
    ConflictError,
    ValidationDomainError,
)
from huginn.management.domain.services.identity_validation import (
    validated_identity_fields,
)
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.professional_profile import (
    NewProfessionalProfile,
)
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.contracts.repositories.account import (
    AccountRepository,
)
from huginn.management.persistence.contracts.repositories.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.persistence.contracts.repositories.user import UserRepository
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.passwords import Password, hash_password


@dataclass(frozen=True)
class ProvisionedIdentity:
    account_id: UUID
    user_id: UUID
    profile_id: UUID
    username: str
    status: str


class IdentityProvisioningService:
    """Create Account, User, and ProfessionalProfile atomically."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        accounts_factory: Callable[[UnitOfWorkProtocol], AccountRepository],
        users_factory: Callable[[UnitOfWorkProtocol], UserRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], ProfessionalProfileRepository],
        hash_password_fn: Callable[[Password], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._accounts_factory = accounts_factory
        self._users_factory = users_factory
        self._profiles_factory = profiles_factory
        self._hash_password = hash_password_fn or hash_password

    def provision(
        self,
        identity: ProvisionIdentity,
    ) -> ProvisionedIdentity:
        (
            username,
            first_name,
            last_name,
            email,
            phone_number,
            country,
            timezone,
        ) = validated_identity_fields(
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
            email=identity.email,
            phone_number=identity.phone_number,
            country_of_residence=identity.country_of_residence,
            timezone=identity.timezone,
        )
        try:
            secret = Password(identity.password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid identity field: password") from exc

        with self._uow_factory() as uow:
            accounts = self._accounts_factory(uow)
            users = self._users_factory(uow)
            profiles = self._profiles_factory(uow)
            if accounts.get_by_normalized_username(username):
                raise ConflictError("username is already in use")
            account = accounts.create(NewAccount(username, self._hash_password(secret)))
            user = users.create(
                NewUser(
                    account.id,
                    first_name,
                    last_name,
                    email,
                    phone_number,
                    country,
                    timezone,
                )
            )
            profile = profiles.create(NewProfessionalProfile(user.id))
            uow.commit()
            return ProvisionedIdentity(
                account.id, user.id, profile.id, account.username, account.status
            )
