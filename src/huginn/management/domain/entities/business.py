"""Business ownership values; see docs/architecture.md section 9."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject


@dataclass(frozen=True)
class Business:
    id: UUID
    owner_user_id: UUID
    name: str | None
    tagline: str | None
    website: str | None
    location: str | None
    description: str | None
    capabilities: tuple[JsonObject, ...] | None
    created_at: datetime
    updated_at: datetime
