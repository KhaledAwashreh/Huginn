from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GeneratedRecommendationReference:
    recommendation_id: UUID
    revision_id: UUID
    recommendation_version: int
