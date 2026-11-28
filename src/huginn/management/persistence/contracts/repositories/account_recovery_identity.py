"""Recovery identity persistence contract; lifecycle design section 1."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.account_recovery_identity import (
    AccountRecoveryIdentity,
)


class AccountRecoveryIdentityRepository(Protocol):
    def get_by_account_id(self, account_id: UUID) -> AccountRecoveryIdentity | None: ...
    def get_by_email(self, email: str) -> AccountRecoveryIdentity | None: ...
    def get_by_pending_email(self, email: str) -> AccountRecoveryIdentity | None: ...
    def get_by_verified_email(self, email: str) -> AccountRecoveryIdentity | None: ...
    def create(
        self,
        account_id: UUID,
        *,
        verification_required: bool,
        pending_email: str | None = None,
    ) -> AccountRecoveryIdentity: ...
    def set_pending_email(
        self, account_id: UUID, email: str
    ) -> AccountRecoveryIdentity | None: ...
    def cancel_pending_replacement(self, account_id: UUID) -> bool: ...
    def verify_email(
        self, account_id: UUID, destination: str, now: datetime
    ) -> AccountRecoveryIdentity | None: ...
