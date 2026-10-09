"""Explicit, inert composition, matchmaking design section 9."""

from datetime import UTC, datetime

from huginn.matchmaking.application.services.batch_matchmaking_service import (
    MatchmakingBatchService,
)
from huginn.matchmaking.application.services.matchmaking_service import (
    MatchmakingService,
)
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.persistence.unit_of_work.sql import (
    SqlMatchmakingUnitOfWork,
    check_readiness,
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def build_service(config: MatchmakingConfig) -> MatchmakingService:
    return MatchmakingService(
        lambda: SqlMatchmakingUnitOfWork(config.database_url), SystemClock()
    )


def build_batch_service(config: MatchmakingConfig) -> MatchmakingBatchService:
    clock = SystemClock()
    service = build_service(config)
    return MatchmakingBatchService(
        service, clock, lambda: check_readiness(config.database_url)
    )
