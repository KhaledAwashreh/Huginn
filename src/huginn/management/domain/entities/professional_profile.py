"""Professional profile aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject


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
