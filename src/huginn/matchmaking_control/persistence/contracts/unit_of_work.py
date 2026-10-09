from types import TracebackType
from typing import Protocol, Self

from huginn.matchmaking_control.application.protocols.target_user_query import (
    TargetUserQuery,
)
from huginn.matchmaking_control.persistence.contracts.repositories.run import (
    RunRepository,
)


class MatchmakingControlUnitOfWork(Protocol):
    runs: RunRepository
    target_users: TargetUserQuery

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
