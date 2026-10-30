from dataclasses import dataclass

from huginn.matchmaking.domain.value_objects._ranking_validation import require
from huginn.matchmaking.domain.value_objects.ranking_score import RankingScore


@dataclass(frozen=True)
class RankedCandidate:
    score: RankingScore
    selection_type: str

    def __post_init__(self) -> None:
        require(
            isinstance(self.score, RankingScore) and not self.score.excluded,
            "Only eligible scores may be selected",
        )
        require(
            self.selection_type in ("exploitation", "exploration"),
            "Invalid selection type",
        )
