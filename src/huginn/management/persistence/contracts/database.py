"""The client contract for the selected PostgreSQL dialect.

SQL and mapping stay in repositories. This contract replaces the Python
driver, not PostgreSQL semantics.
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol, Self

type Row = tuple[Any, ...]
type Parameters = tuple[Any, ...]


@dataclass(frozen=True)
class JsonParameter:
    """A JSONB parameter whose driver adaptation belongs to the client."""

    value: Any


class DatabaseCursor(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...
    def execute(self, query: str, params: Parameters = ()) -> None: ...
    def fetchone(self) -> Row | None: ...
    def fetchall(self) -> list[Row]: ...


class DatabaseResult(Protocol):
    def fetchone(self) -> Row | None: ...
    def fetchall(self) -> list[Row]: ...


class DatabaseSession(Protocol):
    def cursor(self) -> DatabaseCursor: ...
    def execute(self, query: str, params: Parameters = ()) -> DatabaseResult: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class ConnectionFactory(Protocol):
    def connect(self) -> DatabaseSession: ...


class ReadinessPort(Protocol):
    def is_ready(self) -> bool: ...
