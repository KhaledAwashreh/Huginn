from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.value_objects._ranking_validation import require, text


@dataclass(frozen=True)
class RankingEvidence:
    observation_id: UUID
    quote: str

    def __post_init__(self) -> None:
        require(isinstance(self.observation_id, UUID), "Invalid evidence identifier")
        text(self.quote, "Evidence quote")
        require(len(self.quote.split()) <= 25, "Evidence quote exceeds 25 words")
