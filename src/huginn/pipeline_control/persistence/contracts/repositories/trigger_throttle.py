from datetime import datetime
from typing import Protocol
from uuid import UUID


class TriggerThrottleRepository(Protocol):
    def reserve(
        self, requester_account_id: UUID, request_id: UUID, now: datetime, limit: int
    ) -> int | None: ...
