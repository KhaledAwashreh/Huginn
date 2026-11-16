"""Deeply immutable JSON context retained for historical decisions."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.common import JsonObject, JsonValue


@dataclass(frozen=True)
class JsonSnapshot:
    value: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        frozen = _freeze(self.value)
        if not isinstance(frozen, Mapping):
            raise ValidationDomainError("Snapshot must be a JSON object")
        object.__setattr__(self, "value", frozen)

    def to_json_object(self) -> JsonObject:
        """Return a detached, mutable JSON-compatible copy of the snapshot."""
        return _thaw(self.value)


def _freeze(value: object):
    if value is None or type(value) in (bool, int, float, str):
        if type(value) is float and not math.isfinite(value):
            raise ValidationDomainError("Snapshot numbers must be finite")
        return value
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValidationDomainError("Snapshot keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    raise ValidationDomainError("Snapshot must contain JSON values")


def _thaw(value: object):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
