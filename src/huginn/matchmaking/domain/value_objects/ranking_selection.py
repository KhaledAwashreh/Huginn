from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.constants.research_ranking import (
    RESEARCH_RANKING_VERSION,
)
from huginn.matchmaking.domain.value_objects._ranking_validation import require, text
from huginn.matchmaking.domain.value_objects.ranked_candidate import RankedCandidate


@dataclass(frozen=True)
class RankingSelection:
    version: str
    seed: str
    limit: int
    candidates: tuple[RankedCandidate, ...]
    excluded_company_ids: tuple[UUID, ...]
    requested_exploration_slots: int
    actual_exploration_slots: int

    def __post_init__(self) -> None:
        require(
            self.version == RESEARCH_RANKING_VERSION, "Unsupported selection version"
        )
        text(self.seed, "Selection seed")
        require(
            type(self.limit) is int and 1 <= self.limit <= 100,
            "Limit must be between 1 and 100",
        )
        require(
            type(self.candidates) is tuple
            and all(isinstance(c, RankedCandidate) for c in self.candidates),
            "Selected candidates must be an immutable typed tuple",
        )
        require(len(self.candidates) <= self.limit, "Selection exceeds requested limit")
        identities = tuple(c.score.assessment.company_id for c in self.candidates)
        require(len(set(identities)) == len(identities), "Duplicate selected company")
        require(
            type(self.excluded_company_ids) is tuple
            and all(isinstance(i, UUID) for i in self.excluded_company_ids),
            "Excluded companies must be immutable identifiers",
        )
        require(
            len(set(self.excluded_company_ids)) == len(self.excluded_company_ids)
            and not set(identities).intersection(self.excluded_company_ids),
            "Excluded company identities overlap or repeat",
        )
        require(
            type(self.requested_exploration_slots) is int
            and self.requested_exploration_slots == self.limit // 5,
            "Invalid requested exploration budget",
        )
        require(
            type(self.actual_exploration_slots) is int
            and self.actual_exploration_slots
            == sum(c.selection_type == "exploration" for c in self.candidates),
            "Invalid actual exploration count",
        )
        require(
            self.actual_exploration_slots <= len(self.candidates) // 5,
            "Exploration exceeds one fifth of displayed candidates",
        )
