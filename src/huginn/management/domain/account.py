"""Account aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

AccountStatus = Literal["active", "disabled"]


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
