"""Client discovery strategy aggregate values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ClientDiscoveryStrategy:
    id: UUID
    user_id: UUID
    name: str
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
