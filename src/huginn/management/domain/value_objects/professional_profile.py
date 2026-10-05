"""Professional profile aggregate values."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject


@dataclass(frozen=True)
class NewProfessionalProfile:
    user_id: UUID


@dataclass(frozen=True)
class ProfessionalProfileChanges:
    values: Mapping[str, str | None | tuple[JsonObject, ...]]
    supplied_fields: frozenset[str]
