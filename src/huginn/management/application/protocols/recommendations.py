from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)


class RecommendationRepository(Protocol):
    def generation_retry_after(self, user_id: UUID, now: datetime) -> int: ...
    def active_strategy_ids(self, user_id: UUID) -> tuple[UUID, ...]: ...
    def weekly_batches(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[str, ...]: ...
    def profile(
        self, user_id: UUID, strategy_id: UUID
    ) -> RecommendationProfile | None: ...
    def candidates(
        self,
        terms: tuple[str, ...],
        cutoff: datetime,
        as_of: datetime,
        limit: int = 200,
        *,
        exclude_company_ids: frozenset[UUID] = frozenset(),
        offset: int = 0,
    ) -> tuple[RecommendationCompany, ...]: ...
    def save_batch(
        self,
        user_id: UUID,
        batch_id: UUID,
        strategy_id: UUID,
        created_at: datetime,
        snapshot_json: str,
    ) -> None: ...
    def get_batch(self, user_id: UUID, batch_id: UUID) -> str | None: ...
    def latest_batch(self, user_id: UUID, strategy_id: UUID) -> str | None: ...
    def append_feedback(
        self,
        user_id: UUID,
        batch_id: UUID,
        feedback_id: UUID,
        recommendation_id: str,
        created_at: datetime,
        payload_json: str,
    ) -> None: ...
    def feedback(self, user_id: UUID, batch_id: UUID) -> tuple[str, ...]: ...
