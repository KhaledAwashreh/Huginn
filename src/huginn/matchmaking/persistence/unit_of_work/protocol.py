from types import TracebackType
from typing import Protocol, Self

from huginn.matchmaking.persistence.repositories.protocols.candidates import (
    CandidateRepository,
)
from huginn.matchmaking.persistence.repositories.protocols.configuration import (
    ConfigurationRepository,
)
from huginn.matchmaking.persistence.repositories.protocols.matches import (
    MatchRepository,
)


class MatchmakingUnitOfWork(Protocol):
    configuration: ConfigurationRepository
    candidates: CandidateRepository
    matches: MatchRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
