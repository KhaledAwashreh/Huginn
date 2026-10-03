"""Shared immutable domain values and JSON-compatible value types."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    account_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    offset: int
    limit: int
    has_more: bool


type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]
