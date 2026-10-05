"""User aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
