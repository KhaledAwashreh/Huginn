from uuid import UUID

from pydantic import BaseModel, Field

from huginn.management.presentation.api.responses.recommendation_evidence import (
    RecommendationEvidenceResponse,
)


class RecommendationStrategyResponse(BaseModel):
    id: UUID
    name: str
    offering: str
    score: int | None = None
    rationale: str | None = None
    evidence: list[RecommendationEvidenceResponse] = Field(default_factory=list)
