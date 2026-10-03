"""Service offering aggregate values."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ServiceOffering:
    id: UUID
    user_id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NewServiceOffering:
    user_id: UUID
    name: str
    description: str


@dataclass(frozen=True)
class ServiceOfferingChanges:
    values: Mapping[str, str]
    supplied_fields: frozenset[str]
