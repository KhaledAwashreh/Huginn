"""Owner-controlled identity provisioning use case."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from huginn.management.domain.account import NewAccount
from huginn.management.domain.professional_profile import NewProfessionalProfile
from huginn.management.domain.provisioning import ProvisionIdentity
from huginn.management.domain.user import NewUser
from huginn.management.errors.domain import (
    ConflictError,
    ValidationDomainError,
)
from huginn.management.repositories.protocols.account import AccountRepository
from huginn.management.repositories.protocols.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.repositories.protocols.user import UserRepository
from huginn.management.security.passwords import Password, hash_password

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")
_E164_PATTERN = re.compile(r"^\+[1-9][0-9]{1,14}$")


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValidationDomainError(f"invalid identity field: {field}")
    normalized = value.strip()
    if not normalized:
        raise ValidationDomainError(f"invalid identity field: {field}")
    return normalized


def _validated_identity_fields(
    identity: ProvisionIdentity,
) -> tuple[str, str, str, str, str, str, str | None]:
    """Validate and normalize identity fields without a transport framework."""
    username = _required_text("username", identity.username)
    first_name = _required_text("first_name", identity.first_name)
    last_name = _required_text("last_name", identity.last_name)
    email = _required_text("email", identity.email)
    if not 3 <= len(email) <= 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValidationDomainError("invalid identity field: email")

    phone_number = identity.phone_number
    if not isinstance(phone_number, str) or not _E164_PATTERN.fullmatch(phone_number):
        raise ValidationDomainError("invalid identity field: phone_number")

    country = _required_text("country_of_residence", identity.country_of_residence)
    timezone = identity.timezone
    if timezone is not None:
        if not isinstance(timezone, str) or len(timezone) < 1:
            raise ValidationDomainError("invalid identity field: timezone")
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValidationDomainError("invalid identity field: timezone") from exc

    return (
        username,
        first_name,
        last_name,
        email,
        phone_number,
        country,
        timezone,
    )


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
        unit_of_work_factory: Callable[[], Any],
        *,
        accounts_factory: Callable[[Any], AccountRepository],
        users_factory: Callable[[Any], UserRepository],
        profiles_factory: Callable[[Any], ProfessionalProfileRepository],
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
        ) = _validated_identity_fields(identity)
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
