"""Immutable Prospect activity plus effective occurrence projection."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject
from huginn.management.presentation.api.responses.common import ResponseModel


class ProspectActivityResponse(ResponseModel):
    id: UUID
    business_id: UUID
    prospect_id: UUID
    actor_user_id: UUID
    kind: Literal[
        "prospect_saved",
        "stage_changed",
        "closed",
        "reopened",
        "note_added",
        "follow_up_set",
        "follow_up_cleared",
        "proposal_drafted",
        "proposal_sent",
        "correction",
    ]
    occurred_at: datetime
    recorded_at: datetime
    payload: JsonObject
    correction_of_id: UUID | None
    effective_occurred_at: datetime
    correction_head_id: UUID | None
    correction_sequence: int
