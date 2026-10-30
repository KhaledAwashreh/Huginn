from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RecommendationProfile:
    strategy_id: UUID
    snapshot_json: str
    offering_text: str
