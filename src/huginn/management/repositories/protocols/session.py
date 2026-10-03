"""Session persistence contract."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain.common import Principal
from huginn.management.domain.session import NewSession, Session


class SessionRepository(Protocol):
    def create(self, session: NewSession) -> Session: ...
    def get_by_token_digest(self, token_digest: str) -> Session | None: ...
    def get_active_principal_by_token_digest(
        self, token_digest: str, now: datetime
    ) -> Principal | None: ...
    def revoke_current(self, session_id: UUID, revoked_at: datetime) -> None: ...
    def revoke_for_account(self, account_id: UUID, revoked_at: datetime) -> None: ...
