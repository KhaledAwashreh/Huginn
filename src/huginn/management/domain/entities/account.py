"""Account aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.account import AccountStatus


@dataclass(frozen=True)
class Account:
    id: UUID
    username: str
    password_hash: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime
