from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class RecoveredWeeklyDigestResponse(ResponseModel):
    id: UUID
    state: Literal["sent", "failed"]
    version: int
    accepted_at: datetime | None
    settled_at: datetime
