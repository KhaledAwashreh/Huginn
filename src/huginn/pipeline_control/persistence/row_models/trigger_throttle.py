from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TriggerThrottleRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    requester_account_id: UUID
    request_id: UUID
    requested_at: datetime
