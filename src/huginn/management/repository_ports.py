"""Typed, resource-specific management repository and service ports."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain import (
    Account,
    AccountStatus,
    ClientDiscoveryStrategy,
    ClientDiscoveryStrategyChanges,
    IdealClientProfile,
    IdealClientProfileChanges,
    NewAccount,
    NewClientDiscoveryStrategy,
    NewIdealClientProfile,
    NewProfessionalProfile,
    NewServiceOffering,
    NewSession,
    NewUser,
    Page,
    Principal,
    ProfessionalProfile,
    ProfessionalProfileChanges,
    ServiceOffering,
    ServiceOfferingChanges,
    Session,
    User,
    UserChanges,
)


class AccountRepository(Protocol):
    def get_by_id(self, account_id: UUID) -> Account | None: ...
    def get_by_id_for_update(self, account_id: UUID) -> Account | None: ...
    def get_by_normalized_username(self, username: str) -> Account | None: ...
    def get_by_normalized_username_for_update(
        self, username: str
    ) -> Account | None: ...
    def create(self, account: NewAccount) -> Account: ...
    def set_status(self, account_id: UUID, status: AccountStatus) -> Account | None: ...
    def set_password_hash(
        self, account_id: UUID, password_hash: str
    ) -> Account | None: ...


class UserRepository(Protocol):
    def get_by_id(self, user_id: UUID) -> User | None: ...
    def get_by_account_id(self, account_id: UUID) -> User | None: ...
    def create(self, user: NewUser) -> User: ...
    def update(self, user_id: UUID, changes: UserChanges) -> User | None: ...


class ProfessionalProfileRepository(Protocol):
    def get_owned(self, user_id: UUID) -> ProfessionalProfile | None: ...
    def create(self, profile: NewProfessionalProfile) -> ProfessionalProfile: ...
    def update(
        self, user_id: UUID, changes: ProfessionalProfileChanges
    ) -> ProfessionalProfile | None: ...


class SessionRepository(Protocol):
    def create(self, session: NewSession) -> Session: ...
    def get_by_token_digest(self, token_digest: str) -> Session | None: ...
    def revoke_current(self, session_id: UUID, revoked_at: datetime) -> None: ...
    def revoke_for_account(self, account_id: UUID, revoked_at: datetime) -> None: ...


class ServiceOfferingRepository(Protocol):
    def create(self, offering: NewServiceOffering) -> ServiceOffering: ...
    def get_owned(self, user_id: UUID, offering_id: UUID) -> ServiceOffering | None: ...
    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[ServiceOffering]: ...
    def update_owned(
        self, user_id: UUID, offering_id: UUID, changes: ServiceOfferingChanges
    ) -> ServiceOffering | None: ...
    def delete_owned(self, user_id: UUID, offering_id: UUID) -> bool: ...


class IdealClientProfileRepository(Protocol):
    def create(self, profile: NewIdealClientProfile) -> IdealClientProfile: ...
    def get_owned(
        self, user_id: UUID, profile_id: UUID
    ) -> IdealClientProfile | None: ...
    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[IdealClientProfile]: ...
    def update_owned(
        self,
        user_id: UUID,
        profile_id: UUID,
        changes: IdealClientProfileChanges,
    ) -> IdealClientProfile | None: ...
    def delete_owned(self, user_id: UUID, profile_id: UUID) -> bool: ...


class ClientDiscoveryStrategyRepository(Protocol):
    def create(
        self, strategy: NewClientDiscoveryStrategy
    ) -> ClientDiscoveryStrategy: ...
    def get_owned(
        self, user_id: UUID, strategy_id: UUID
    ) -> ClientDiscoveryStrategy | None: ...
    def list_owned(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
        active: bool | None = None,
    ) -> Page[ClientDiscoveryStrategy]: ...
    def update_owned(
        self,
        user_id: UUID,
        strategy_id: UUID,
        changes: ClientDiscoveryStrategyChanges,
    ) -> ClientDiscoveryStrategy | None: ...
    def delete_owned(self, user_id: UUID, strategy_id: UUID) -> bool: ...


class OwnedResourceValidator(Protocol):
    def validate_strategy_references(
        self, principal: Principal, offering_id: UUID, profile_id: UUID
    ) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class TokenGenerator(Protocol):
    def new_token(self) -> str: ...


class PageAssembler[T](Protocol):
    def page(self, items: Sequence[T], limit: int, offset: int) -> Page[T]: ...
