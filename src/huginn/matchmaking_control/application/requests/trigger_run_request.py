from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.matchmaking_control.domain.value_objects.requester import Requester


@dataclass(frozen=True)
class TriggerRunRequest:
    requester: Requester
    request_id: UUID
    target_kind: str
    cutoff: datetime
    as_of: datetime | None = None
    user_id: UUID | None = None
