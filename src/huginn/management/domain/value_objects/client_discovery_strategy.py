"""Client discovery strategy aggregate values."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class NewClientDiscoveryStrategy:
    user_id: UUID
    name: str
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool = False


@dataclass(frozen=True)
class ClientDiscoveryStrategyChanges:
    values: Mapping[str, str | UUID | bool]
    supplied_fields: frozenset[str]
