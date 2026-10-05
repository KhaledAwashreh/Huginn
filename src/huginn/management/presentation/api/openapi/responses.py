"""Reusable error response declarations for generated management OpenAPI."""

from typing import Any

_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message", "details"],
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {}},
            },
        }
    },
}
_VALIDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["detail"],
    "properties": {
        "detail": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["loc", "type", "msg"],
                "properties": {
                    "loc": {"type": "array", "items": {}},
                    "type": {"type": "string"},
                    "msg": {"type": "string"},
                },
            },
        }
    },
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Describe project error envelopes and sanitized native validation errors."""
    responses: dict[int | str, dict[str, Any]] = {
        code: {
            "description": "Request failed",
            "content": {"application/json": {"schema": _ERROR_SCHEMA}},
        }
        for code in codes
        if code != 422
    }
    if 422 in codes:
        responses[422] = {
            "description": "Request or domain validation failed",
            "content": {
                "application/json": {
                    "schema": {"oneOf": [_VALIDATION_SCHEMA, _ERROR_SCHEMA]}
                }
            },
        }
    responses["default"] = {
        "description": "Unexpected application error",
        "content": {"application/json": {"schema": _ERROR_SCHEMA}},
    }
    return responses
