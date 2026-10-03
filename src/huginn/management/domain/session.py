"""Server-side session values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
