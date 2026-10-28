from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from huginn.management.presentation.api.responses.recommendation_item import (
    RecommendationItemResponse,
)


class RecommendationBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    strategy_id: UUID
    created_at: datetime
    algorithm_version: str
    assessment_method: str
    candidate_count: int
    retrieval_limit: int
    items: list[RecommendationItemResponse]
