"""Canonical request intent fingerprint, independent of request-key lookup."""

import hashlib
import json
import math
from collections.abc import Mapping

from huginn.management.domain.errors.errors import ValidationDomainError


def fingerprint_command_payload(
    command_type: str, payload: Mapping[str, object]
) -> str:
    if (
        not isinstance(command_type, str)
        or not command_type.strip()
        or command_type != command_type.strip()
    ):
        raise ValidationDomainError("Command type is required")
    try:
        canonical = json.dumps(
            {"command_type": command_type, "payload": _canonical(payload)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationDomainError("Command payload must be finite JSON") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical(value: object):
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationDomainError("Command payload must be finite JSON")
        return value
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValidationDomainError("Command payload object keys must be strings")
        return {key: _canonical(item) for key, item in value.items()}
    raise ValidationDomainError("Command payload must be finite JSON")
