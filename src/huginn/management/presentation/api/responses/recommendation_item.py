from typing import Literal

from pydantic import BaseModel, Field

from huginn.management.presentation.api.responses.recommendation_breakdown import (
    RecommendationBreakdownResponse,
)
from huginn.management.presentation.api.responses.recommendation_company import (
    RecommendationCompanyResponse,
)
from huginn.management.presentation.api.responses.recommendation_evidence import (
    RecommendationEvidenceResponse,
)
from huginn.management.presentation.api.responses.recommendation_strategy import (
    RecommendationStrategyResponse,
)


class RecommendationItemResponse(BaseModel):
    id: str
    company: RecommendationCompanyResponse
    score: int
    confidence: Literal["high", "medium", "low"]
    selection_type: Literal["exploration", "exploitation"]
    rationale: str
    unknowns: list[str]
    breakdown: RecommendationBreakdownResponse
    evidence: list[RecommendationEvidenceResponse]
    strategies: list[RecommendationStrategyResponse] = Field(default_factory=list)
    icp_fit: dict[str, Literal["match", "unknown", "mismatch"]] = Field(
        default_factory=dict
    )
