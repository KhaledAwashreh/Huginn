from typing import Literal

from pydantic import BaseModel

from huginn.management.presentation.api.responses.recommendation_breakdown import (
    RecommendationBreakdownResponse,
)
from huginn.management.presentation.api.responses.recommendation_company import (
    RecommendationCompanyResponse,
)
from huginn.management.presentation.api.responses.recommendation_evidence import (
    RecommendationEvidenceResponse,
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
