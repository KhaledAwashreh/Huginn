"""Assessment-time strategy association and its immutable JSON snapshots."""

from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject
from huginn.management.presentation.api.responses.common import ResponseModel


class StrategyAssessmentResponse(ResponseModel):
    strategy_id: UUID
    offering_id: UUID
    ideal_client_profile_id: UUID
    strategy_snapshot: JsonObject
    offering_snapshot: JsonObject
    ideal_client_profile_snapshot: JsonObject
    assessment_snapshot: JsonObject
