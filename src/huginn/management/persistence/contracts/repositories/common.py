"""Shared domain and application contracts used by repository protocols."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from huginn.management.domain.value_objects.common import Page


class Clock(Protocol):
    def now(self) -> datetime: ...


class TokenGenerator(Protocol):
    def new_token(self) -> str: ...


class PageAssembler[T](Protocol):
    def page(self, items: Sequence[T], limit: int, offset: int) -> Page[T]: ...
