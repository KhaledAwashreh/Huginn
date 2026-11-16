"""Business creation intent; architecture section 9."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class NewBusiness:
    owner_user_id: UUID
