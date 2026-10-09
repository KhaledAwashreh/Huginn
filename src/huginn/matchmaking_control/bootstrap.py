"""Compose administrative services without startup database I/O."""

from datetime import UTC, datetime
from types import SimpleNamespace

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking_control.application.services.get_run_service import (
    GetRunService,
)
from huginn.matchmaking_control.application.services.list_runs_service import (
    ListRunsService,
)
from huginn.matchmaking_control.application.services.list_skipped_strategies_service import (
    ListSkippedStrategiesService,
)
from huginn.matchmaking_control.application.services.list_target_users_service import (
    ListTargetUsersService,
)
from huginn.matchmaking_control.application.services.list_user_results_service import (
    ListUserResultsService,
)
from huginn.matchmaking_control.application.services.trigger_run_service import (
    TriggerRunService,
)
from huginn.matchmaking_control.persistence.database.unit_of_work import (
    PostgresMatchmakingControlUnitOfWork,
)
from huginn.matchmaking_control.persistence.queries.run_reader import PostgresRunReader


class _Clock:
    def __init__(self, clock):
        self._clock = clock or (lambda: datetime.now(UTC))

    def now(self):
        return self._clock()


def create_matchmaking_control_services(database_url: str, *, clock=None):
    factory = ManagementConnectionFactory(database_url, statement_timeout_ms=2000)
    reader = PostgresRunReader(
        lambda: PostgresMatchmakingControlUnitOfWork(factory), clock=clock
    )
    return SimpleNamespace(
        trigger=TriggerRunService(
            lambda: PostgresMatchmakingControlUnitOfWork(factory), _Clock(clock)
        ),
        users=ListTargetUsersService(
            lambda: PostgresMatchmakingControlUnitOfWork(factory)
        ),
        history=ListRunsService(lambda: reader),
        get=GetRunService(lambda: reader),
        results=ListUserResultsService(lambda: reader),
        skipped=ListSkippedStrategiesService(lambda: reader),
    )
