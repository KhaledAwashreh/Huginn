"""Ideal client profile aggregate values."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject


@dataclass(frozen=True)
class NewIdealClientProfile:
    user_id: UUID
    name: str
    industries: tuple[JsonObject, ...]
    company_sizes: tuple[JsonObject, ...]
    geographies: tuple[JsonObject, ...]
    exclusions: tuple[JsonObject, ...]


@dataclass(frozen=True)
class IdealClientProfileChanges:
    values: Mapping[str, str | tuple[JsonObject, ...]]
    supplied_fields: frozenset[str]
