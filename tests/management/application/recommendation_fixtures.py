from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)


def recommendation_company() -> RecommendationCompany:
    now = datetime(2026, 10, 28, tzinfo=UTC)
    observation = RankingObservation(
        uuid4(),
        "Our onboarding software serves customers.",
        now - timedelta(days=1),
        now,
        "hn",
        "https://example.test",
    )
    return RecommendationCompany(
        uuid4(), "Source company", "example.test", None, None, None, (observation,)
    )
