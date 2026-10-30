from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)


@dataclass(frozen=True)
class RecommendationCompany:
    company_id: UUID
    name: str
    domain: str
    business_sector: tuple[str, ...] | None
    country: str | None
    company_scale: str | None
    observations: tuple[RankingObservation, ...]
    source_countries: tuple[tuple[UUID, str], ...] = ()
    country_evidence_id: UUID | None = None
