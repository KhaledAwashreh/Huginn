"""Assessment revision API response preserving its immutable snapshots."""

from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.common import JsonObject
from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.prospecting_strategy_assessment import (
    StrategyAssessmentResponse,
)


class AssessmentRevisionResponse(ResponseModel):
    id: UUID
    recommendation_id: UUID
    business_id: UUID
    company_id: UUID
    revision_number: int
    assessed_at: datetime
    assessed_by_user_id: UUID | None
    strategy_assessments: list[StrategyAssessmentResponse]
    professional_profile_snapshot: JsonObject
    evidence_snapshots: list[JsonObject]
    evidence_observation_ids: list[UUID]
    policy_versions: list[str]
    evaluation_seed: str | None
