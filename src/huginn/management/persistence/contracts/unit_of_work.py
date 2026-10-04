"""Transaction boundary consumed by management application services."""

from types import TracebackType
from typing import Protocol, Self

from huginn.management.persistence.contracts.database import DatabaseSession


class UnitOfWorkProtocol(Protocol):
    connection: DatabaseSession | None

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
