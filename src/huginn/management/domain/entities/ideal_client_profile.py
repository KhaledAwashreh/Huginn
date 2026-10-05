"""Ideal client profile aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject


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
