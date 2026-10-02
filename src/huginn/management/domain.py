"""Management domain values and errors, independent of Flask and storage."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    account_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    offset: int
    limit: int
    has_more: bool


AccountStatus = Literal["active", "disabled"]
type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class Account:
    id: UUID
    username: str
    password_hash: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewAccount:
    username: str
    password_hash: str
    status: AccountStatus = "active"


@dataclass(frozen=True)
class User:
    id: UUID
    account_id: UUID
    first_name: str
    last_name: str
    email: str
    phone_number: str
    country_of_residence: str
    timezone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewUser:
    account_id: UUID
    first_name: str
    last_name: str
    email: str
    phone_number: str
    country_of_residence: str
    timezone: str | None = None


@dataclass(frozen=True)
class UserChanges:
    values: Mapping[str, str | None]
    supplied_fields: frozenset[str]


@dataclass(frozen=True)
class ProfessionalProfile:
    id: UUID
    user_id: UUID
    headline: str | None
    professional_summary: str | None
    skills: tuple[JsonObject, ...]
    experience: tuple[JsonObject, ...]
    previous_projects: tuple[JsonObject, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewProfessionalProfile:
    user_id: UUID


@dataclass(frozen=True)
class ProfessionalProfileChanges:
    values: Mapping[str, str | None | tuple[JsonObject, ...]]
    supplied_fields: frozenset[str]


@dataclass(frozen=True)
class Session:
    id: UUID
    account_id: UUID
    token_digest: str
    csrf_digest: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class NewSession:
    account_id: UUID
    token_digest: str
    csrf_digest: str
    expires_at: datetime


@dataclass(frozen=True)
class ServiceOffering:
    id: UUID
    user_id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewServiceOffering:
    user_id: UUID
    name: str
    description: str


@dataclass(frozen=True)
class ServiceOfferingChanges:
    values: Mapping[str, str]
    supplied_fields: frozenset[str]


@dataclass(frozen=True)
class IdealClientProfile:
    id: UUID
    user_id: UUID
    name: str
    industries: tuple[JsonObject, ...]
    company_sizes: tuple[JsonObject, ...]
    geographies: tuple[JsonObject, ...]
    exclusions: tuple[JsonObject, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewIdealClientProfile:
    user_id: UUID
    name: str
    industries: tuple[JsonObject, ...]
    company_sizes: tuple[JsonObject, ...]
    geographies: tuple[JsonObject, ...]
    exclusions: tuple[JsonObject, ...]


@dataclass(frozen=True)
class IdealClientProfileChanges:
    values: Mapping[str, str | tuple[JsonObject, ...]]
    supplied_fields: frozenset[str]


@dataclass(frozen=True)
class ClientDiscoveryStrategy:
    id: UUID
    user_id: UUID
    name: str
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewClientDiscoveryStrategy:
    user_id: UUID
    name: str
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool = False


@dataclass(frozen=True)
class ClientDiscoveryStrategyChanges:
    values: Mapping[str, str | UUID | bool]
    supplied_fields: frozenset[str]


class ManagementDomainError(Exception):
    """Base class for expected management use-case failures."""


class ValidationDomainError(ManagementDomainError):
    pass


class AuthenticationError(ManagementDomainError):
    pass


class AuthorizationError(ManagementDomainError):
    pass


class NotFoundError(ManagementDomainError):
    pass


class ConflictError(ManagementDomainError):
    pass


class RateLimitError(ManagementDomainError):
    pass
