from dataclasses import dataclass

from huginn.matchmaking.application.requests.research_ranking_request import (
    ResearchRankingRequest,
)
from huginn.matchmaking.domain.value_objects.ranking_score import RankingScore
from huginn.matchmaking.domain.value_objects.ranking_selection import RankingSelection


@dataclass(frozen=True)
class ResearchRankingResponse:
    ranking_id: str
    input_fingerprint: str
    request: ResearchRankingRequest
    scores: tuple[RankingScore, ...]
    selection: RankingSelection
