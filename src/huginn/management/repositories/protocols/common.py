"""Shared domain and application contracts used by repository protocols."""

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from huginn.management.domain.common import Page


class Clock(Protocol):
    def now(self) -> datetime: ...


class TokenGenerator(Protocol):
    def new_token(self) -> str: ...


class PageAssembler[T](Protocol):
    def page(self, items: Sequence[T], limit: int, offset: int) -> Page[T]: ...


class UnitOfWorkProtocol(Protocol):
    """Transaction boundary consumed by application services."""

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class ReadinessPort(Protocol):
    """Readiness boundary consumed by the HTTP composition layer."""

    def is_ready(self) -> bool: ...
