"""Shared JSON parsing and response helpers for the management HTTP boundary."""

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from flask import Response, jsonify, request
from pydantic import BaseModel
from werkzeug.exceptions import BadRequest

from huginn.management.domain import Page

_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token_digest",
        "csrf_digest",
    }
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def parse_json[ModelT: BaseModel](model: type[ModelT]) -> ModelT:
    """Parse one JSON request body and validate it with the supplied strict model."""
    if not request.is_json:
        raise BadRequest()
    try:
        value = json.loads(
            request.get_data(cache=True),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise BadRequest() from exc
    # Re-validate in JSON mode so strict semantic JSON types such as UUIDs can
    # accept their JSON string representation without enabling Python coercion.
    return model.model_validate_json(json.dumps(value))


def _serialize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _serialize(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        if any(str(key).casefold() in _SENSITIVE_FIELDS for key in value):
            raise ValueError("Sensitive field cannot be serialized")
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, Enum):
        return _serialize(value.value)
    return value


def json_response(value: Any, status: int = 200) -> tuple[Response, int]:
    """Serialize supported domain and Pydantic values as a JSON response."""
    return jsonify(_serialize(value)), status


def page_response(page: Page[Any], status: int = 200) -> tuple[Response, int]:
    """Serialize a page using the shared deterministic collection contract."""
    return json_response(
        {
            "items": page.items,
            "offset": page.offset,
            "limit": page.limit,
            "has_more": page.has_more,
        },
        status,
    )


def error_response(
    status: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> tuple[Response, int]:
    return json_response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else [],
            }
        },
        status,
    )
