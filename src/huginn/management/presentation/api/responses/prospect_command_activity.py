"""The exact immutable activity appended by a command."""

from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject
from huginn.management.presentation.api.responses.common import ResponseModel


class ProspectCommandActivityResponse(ResponseModel):
    id: UUID
    business_id: UUID
    prospect_id: UUID
    actor_user_id: UUID
    kind: str
    occurred_at: datetime
    recorded_at: datetime
    payload: JsonObject
    correction_of_id: UUID | None
