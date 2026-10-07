from collections.abc import Mapping
from types import MappingProxyType

from huginn.matchmaking.domain.types.json_value import RawJsonValue
from huginn.matchmaking.persistence.errors.database import DataIntegrityError


def freeze_json_value(value: object) -> RawJsonValue:
    if value is None or type(value) in (bool, int, float, str):
        return value  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(freeze_json_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_json_value(item) for item in value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise DataIntegrityError("JSON object keys must be strings")
        return MappingProxyType(
            {key: freeze_json_value(item) for key, item in value.items()}
        )
    raise DataIntegrityError("database value is not JSON")
